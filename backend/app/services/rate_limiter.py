"""
Rate limiting for the whole API: sliding windows in Redis.

RateLimitMiddleware checks every /api request against the rules below that
match it. One Redis script checks all of a request's limits and records the
request in all of them in a single atomic step, so a request refused by one
limit counts against none, and concurrent requests can't slip past a full
window. A refused request gets HTTP 429 with a Retry-After header.

Limits come from settings as "count/seconds", comma-separated for several
windows: "5/60,60/3600" allows 5 requests a minute and 60 an hour. An empty
value turns that rule off; RATE_LIMIT_ENABLED=false turns them all off.

    setting                      requests                                 counted per
    RATE_LIMIT_API_IP            every /api request                       client IP
    RATE_LIMIT_AUTH_IP           login, register (password guessing)      client IP
    RATE_LIMIT_GUEST_LOGIN_IP    guest login                              client IP
    RATE_LIMIT_CHAT_USER         chat questions                           user
    RATE_LIMIT_CHAT_IP           chat questions                           client IP
    RATE_LIMIT_SUGGESTIONS_USER  question suggestions (LLM calls)         user
    RATE_LIMIT_HEAVY_USER        add / test a connection (connects to     user
                                 outside hosts), re-profile a schema

"user" is the id in the request's bearer token (checked without a database
query); requests without a valid token, and guests (who all share one
account), are counted per IP instead. The client IP is the TCP peer: behind
a reverse proxy, run uvicorn with --proxy-headers and --forwarded-allow-ips
set to the proxy, or every user shares its IP.

If Redis can't be reached, requests are let through (and an error is logged):
an outage of the limiter must not take the API down. Redis is then left alone
for _REDIS_RETRY_AFTER_S, so requests don't each wait for its timeout.
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from dataclasses import dataclass

import anyio
import redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from jose import JWTError, jwt
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings

logger = logging.getLogger(__name__)

_IP, _USER = "ip", "user"
_REDIS_ERROR_LOG_INTERVAL_S = 60
_REDIS_RETRY_AFTER_S = 30

# Checks every key's window, then records the request in all of them only if
# all have room. KEYS: one per window. ARGV: member, then limit and window
# (ms) for each key. Returns 0 when allowed, else the ms until a slot frees.
_SLIDING_WINDOWS = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local wait = 0
for i, key in ipairs(KEYS) do
  local limit = tonumber(ARGV[2 * i])
  local window = tonumber(ARGV[2 * i + 1])
  redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
  if redis.call('ZCARD', key) >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local free_in = window - (now - tonumber(oldest[2]))
    if free_in > wait then wait = free_in end
  end
end
if wait > 0 then return wait end
for i, key in ipairs(KEYS) do
  redis.call('ZADD', key, now, ARGV[1])
  redis.call('PEXPIRE', key, tonumber(ARGV[2 * i + 1]))
end
return 0
"""


@dataclass(frozen=True)
class Window:
    limit: int
    seconds: int


@dataclass(frozen=True)
class Rule:
    name: str
    methods: frozenset[str]     # empty: any method
    path: re.Pattern
    per: str                    # _IP or _USER
    windows: tuple[Window, ...]

    def matches(self, method: str, path: str) -> bool:
        return (not self.methods or method in self.methods) and bool(self.path.fullmatch(path))


def parse_windows(spec: str, setting: str) -> tuple[Window, ...]:
    """'5/60,60/3600' -> (Window(5, 60), Window(60, 3600)). Raises on a bad value."""
    windows = []
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        match = re.fullmatch(r"(\d+)\s*/\s*(\d+)", part)
        if not match or int(match[1]) < 1 or int(match[2]) < 1:
            raise ValueError(f"{setting}: '{part}' is not 'count/seconds' (e.g. '5/60')")
        windows.append(Window(int(match[1]), int(match[2])))
    return tuple(windows)


def build_rules(settings) -> list[Rule]:
    table = [
        # name, setting, methods, path, counted per
        ("api", "RATE_LIMIT_API_IP", (), r"/api/.*", _IP),
        ("auth", "RATE_LIMIT_AUTH_IP", ("POST",), r"/api/auth/(login|register)", _IP),
        ("guest", "RATE_LIMIT_GUEST_LOGIN_IP", ("POST",), r"/api/auth/(guest|guest-login)", _IP),
        ("chat-user", "RATE_LIMIT_CHAT_USER", ("POST",), r"/api/query/chat", _USER),
        ("chat-ip", "RATE_LIMIT_CHAT_IP", ("POST",), r"/api/query/chat", _IP),
        ("suggestions", "RATE_LIMIT_SUGGESTIONS_USER", ("POST",), r"/api/suggestions/.*", _USER),
        ("heavy", "RATE_LIMIT_HEAVY_USER", ("POST",),
         r"/api/connections(/test)?|/api/schema/[^/]+/profile/refresh", _USER),
    ]
    rules = []
    for name, setting, methods, path, per in table:
        windows = parse_windows(getattr(settings, setting), setting)
        if windows:
            rules.append(Rule(name, frozenset(methods), re.compile(path), per, windows))
    return rules


def _user_id(request: Request, secret: str, algorithm: str) -> str | None:
    """The user id in a valid bearer token, else None. No database query:
    the token's signature and expiry are enough to count by user. Guest
    tokens give None: all guests share one account, so they count per IP."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        claims = jwt.decode(header[7:].strip(), secret, algorithms=[algorithm])
    except JWTError:
        return None
    sub = claims.get("sub")
    return str(sub) if sub is not None and not claims.get("guest") else None


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app
        settings = get_settings()
        self.enabled = settings.RATE_LIMIT_ENABLED
        self.rules = build_rules(settings) if self.enabled else []
        self.secret, self.algorithm = settings.SECRET_KEY, settings.ALGORITHM
        self._redis = None
        self._script = None
        self._last_redis_error = 0.0
        self._redis_down_until = 0.0

    def _get_script(self):
        # The sync client is thread-safe and not tied to an event loop (an
        # asyncio client breaks when used from a different loop than the one
        # it connected on); the call runs in a worker thread.
        if self._script is None:
            self._redis = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"),
                                      port=int(os.getenv("REDIS_PORT", "6379")), db=0,
                                      socket_timeout=1, socket_connect_timeout=1,
                                      retry=Retry(NoBackoff(), 0))
            self._script = self._redis.register_script(_SLIDING_WINDOWS)
        return self._script

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.rules:
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        method, path = request.method, request.url.path
        matching = [r for r in self.rules if r.matches(method, path)] if method != "OPTIONS" else []
        if matching:
            wait_ms = await self._check(request, matching)
            if wait_ms:
                retry_after = max(1, -(-wait_ms // 1000))
                # X-Rate-Limit marks our own limit (the frontend signs the user
                # out), unlike a 429 passed on from the LLM provider.
                response = JSONResponse(
                    {"detail": f"Too many requests. Try again in {retry_after} seconds."},
                    status_code=429,
                    headers={"Retry-After": str(retry_after), "X-Rate-Limit": "api"})
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

    async def _check(self, request: Request, rules: list[Rule]) -> int:
        ip = request.client.host if request.client else "unknown"
        user = None
        if any(r.per == _USER for r in rules):
            user = _user_id(request, self.secret, self.algorithm)
        keys, args = [], [uuid.uuid4().hex]
        for rule in rules:
            who = f"user:{user}" if rule.per == _USER and user else f"ip:{ip}"
            for w in rule.windows:
                keys.append(f"rl:{rule.name}:{w.limit}/{w.seconds}:{who}")
                args += [w.limit, w.seconds * 1000]
        if time.monotonic() < self._redis_down_until:
            return 0
        try:
            script = self._get_script()
            return int(await anyio.to_thread.run_sync(lambda: script(keys=keys, args=args)))
        except Exception as exc:
            now = time.monotonic()
            self._redis_down_until = now + _REDIS_RETRY_AFTER_S
            if now - self._last_redis_error > _REDIS_ERROR_LOG_INTERVAL_S:
                self._last_redis_error = now
                logger.error("Rate limiting skipped, Redis unavailable: %s", exc)
            return 0
