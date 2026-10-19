"""Caching and connection handling: engine cache disposal, Redis outages,
SQL execution round trips and the keyword-search token cache."""
import socket
import time
from contextlib import contextmanager
from types import SimpleNamespace

import anyio
import pytest

from app.services import rate_limiter
from app.services.redis_client import RedisClient
from app.services.schema_index.retriever import tokens
from app.services.validate_sql import SafeSqlExecutor
from app.utils import db_manager


class _Engine:
    def __init__(self):
        self.disposed = 0

    def dispose(self):
        self.disposed += 1


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


# ── Engine cache ─────────────────────────────────────────────────────────────

def test_engines_are_disposed_once_on_expiry_eviction_and_removal():
    clock = _Clock()
    cache = db_manager._DisposingEngineCache(maxsize=2, ttl=60, timer=clock)
    expired, evicted, removed, kept = _Engine(), _Engine(), _Engine(), _Engine()
    cache["expired"] = expired
    clock.now = 61
    cache["evicted"] = evicted          # expires "expired"
    cache["removed"] = removed
    cache["kept"] = kept                # maxsize 2: evicts "evicted"
    del cache["removed"]
    assert (expired.disposed, evicted.disposed, removed.disposed, kept.disposed) == (1, 1, 1, 0)
    assert list(cache) == ["kept"]


def test_deleting_an_expired_engine_still_disposes_it():
    clock = _Clock()
    cache = db_manager._DisposingEngineCache(maxsize=10, ttl=60, timer=clock)
    engine = cache["a"] = _Engine()
    clock.now = 100
    with pytest.raises(KeyError):       # TTLCache reports expired items as missing
        del cache["a"]
    assert engine.disposed == 1


def test_using_an_engine_restarts_its_ttl(monkeypatch):
    clock = _Clock()
    cache = db_manager._DisposingEngineCache(maxsize=10, ttl=60, timer=clock)
    monkeypatch.setattr(db_manager, "_engine_cache", cache)
    engine = cache[(1, 7)] = _Engine()
    conn = SimpleNamespace(user_id=1, id=7)
    for now in (50, 100, 150):          # used every 50 s: never idle for 60 s
        clock.now = now
        assert db_manager.get_user_engine(conn) is engine
    clock.now = 211                     # idle for 61 s
    cache.expire()
    assert (1, 7) not in cache and engine.disposed == 1


def test_remove_engine_disposes_every_engine_of_the_connection(monkeypatch):
    cache = db_manager._DisposingEngineCache(maxsize=10, ttl=60)
    monkeypatch.setattr(db_manager, "_engine_cache", cache)
    a, b, other = _Engine(), _Engine(), _Engine()
    cache[(1, 7)], cache[(2, 7)], cache[(1, 8)] = a, b, other
    db_manager.remove_engine(7)
    assert (a.disposed, b.disposed, other.disposed) == (1, 1, 0)


# ── Redis outages ────────────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def _silent_server():
    """Accepts connections and never answers (a hung Redis)."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(50)
    try:
        yield server.getsockname()[1]
    finally:
        server.close()


def _client(monkeypatch, port: int) -> RedisClient:
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", str(port))
    return RedisClient()


@pytest.mark.parametrize("hung", [False, True])
def test_unreachable_redis_is_a_cache_miss_and_is_then_skipped(monkeypatch, hung):
    def check(port):
        client = _client(monkeypatch, port)
        start = time.perf_counter()
        assert client.get("k") is None
        first = time.perf_counter() - start
        start = time.perf_counter()
        assert client.set("k", [1]) is None and client.get("k") is None
        assert client.delete("k") == 0 and not client.exists("k")
        rest = time.perf_counter() - start
        assert first < 3.0                # one timeout, no retries
        assert rest < 0.05                # skipped while down

    if hung:
        with _silent_server() as port:
            check(port)
    else:
        check(_free_port())


def test_redis_is_tried_again_after_the_skip_window(monkeypatch):
    client = _client(monkeypatch, _free_port())
    calls = []
    monkeypatch.setattr(client.client, "get", lambda key: calls.append(key) or '{"a": 1}')
    client._down_until = time.monotonic() + 30
    assert client.get("k") is None and calls == []
    client._down_until = time.monotonic() - 1
    assert client.get("k") == {"a": 1} and calls == ["k"]


def test_rate_limiter_lets_requests_through_and_skips_redis_while_down(monkeypatch):
    middleware = rate_limiter.RateLimitMiddleware(app=None)
    attempts = []

    def broken_script():
        attempts.append(1)
        raise ConnectionError("down")

    monkeypatch.setattr(middleware, "_get_script", broken_script)
    request = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"), headers={})
    rule = rate_limiter.Rule("api", frozenset(), None, rate_limiter._IP,
                             (rate_limiter.Window(10, 60),))

    async def two_requests():
        return [await middleware._check(request, [rule]) for _ in range(2)]

    assert anyio.run(two_requests) == [0, 0]
    assert len(attempts) == 1


# ── SQL execution ────────────────────────────────────────────────────────────

class _Result:
    def keys(self):
        return ["n"]

    def fetchmany(self, size):
        return [(1,), (2,)]


class _RecordingEngine:
    def __init__(self):
        self.transactions: list[list[str]] = []

    @contextmanager
    def begin(self):
        statements: list[str] = []
        self.transactions.append(statements)
        yield SimpleNamespace(execute=lambda stmt: statements.append(str(stmt)) or _Result())


def test_run_executes_in_one_transaction_without_explain():
    engine = _RecordingEngine()
    result = SafeSqlExecutor(engine, max_rows=10, timeout_ms=1234).run("```sql\nSELECT n FROM t;\n```")
    assert result.success and result.rows == [{"n": 1}, {"n": 2}] and result.sql == "SELECT n FROM t"
    assert len(engine.transactions) == 1
    settings, query = engine.transactions[0]
    assert "READ ONLY" in settings and "statement_timeout = 1234" in settings
    assert query == "SELECT n FROM t" and "EXPLAIN" not in settings + query


def test_unsafe_sql_never_reaches_the_database():
    engine = _RecordingEngine()
    executor = SafeSqlExecutor(engine)
    for sql in ("DELETE FROM t", "SELECT 1; SELECT 2", "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d",
                "SELECT pg_sleep(10)", ""):
        assert not executor.run(sql).success, sql
    assert engine.transactions == []


def test_validate_still_checks_with_explain():
    engine = _RecordingEngine()
    assert SafeSqlExecutor(engine).validate("SELECT n FROM t").is_valid
    assert engine.transactions[0][-1] == "EXPLAIN SELECT n FROM t"


# ── Keyword search tokens ────────────────────────────────────────────────────

def test_tokens_are_cached_and_immutable():
    tokens.cache_clear()
    first = tokens("customerSegments of the Orders")
    assert first == {"customer", "segment", "order"} and isinstance(first, frozenset)
    assert tokens("customerSegments of the Orders") is first
    assert tokens.cache_info().hits == 1
    assert tokens(None) == frozenset() and tokens("") == frozenset()
