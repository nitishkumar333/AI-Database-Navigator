import time
from fastapi import HTTPException
from app.services.redis_client import redis_client

# ── Rate-limit config ────────────────────────────────────────────
RATE_LIMIT_MAX_REQUESTS = 3   # max requests allowed
RATE_LIMIT_WINDOW_SECS  = 90  # sliding window in seconds


def _enforce_limit(key: str, max_requests: int, window: int):
    """
    Sliding-window check on a single Redis sorted-set key.
    Raises HTTP 429 if the limit is exceeded.
    """
    now = time.time()
    window_start = now - window
    pipe = redis_client.client.pipeline()
    pipe.zremrangebyscore(key, "-inf", window_start)
    pipe.zcard(key)
    _, current_count = pipe.execute()

    if current_count >= max_requests:
        oldest = redis_client.client.zrange(key, 0, 0, withscores=True)
        retry_after = int((oldest[0][1] + window) - now) + 1 if oldest else window
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    pipe2 = redis_client.client.pipeline()
    pipe2.zadd(key, {f"{now}": now})
    pipe2.expire(key, window + 10)
    pipe2.execute()


def check_rate_limit(user_id: int, client_ip: str):
    """
    Two independent sliding-window rate limits:
      1. Per-IP   – prevents abuse even when creating multiple accounts.
      2. Per-User – prevents a single account from abusing across IPs/VPNs.
    Both must pass for the request to go through.
    """
    # IP-based limit (checked first — catches multi-account abuse)
    _enforce_limit(f"rate_limit:chat:ip:{client_ip}", RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECS)
    # User-based limit
    _enforce_limit(f"rate_limit:chat:user:{user_id}", RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECS)
