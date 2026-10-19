"""
Redis cache. A cache must never take the API down: when Redis can't be
reached (or doesn't answer within a second) every call acts as a cache miss,
and Redis is left alone for _RETRY_AFTER_S before it is tried again, so an
outage costs one timeout, not one per call.
"""
import json
import logging
import os
import threading
import time

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

logger = logging.getLogger(__name__)

_TIMEOUT_S = 1
_RETRY_AFTER_S = 30


class RedisClient:
    def __init__(self):
        # `client` is also used directly (locks, key scans); callers catch its errors.
        self.client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=0,
            decode_responses=True,
            socket_timeout=_TIMEOUT_S,
            socket_connect_timeout=_TIMEOUT_S,
            retry=Retry(NoBackoff(), 0),
        )
        self._down_until = 0.0
        self._lock = threading.Lock()

    def _call(self, default, method, *args, **kwargs):
        if time.monotonic() < self._down_until:
            return default
        try:
            return getattr(self.client, method)(*args, **kwargs)
        except redis.RedisError as exc:
            with self._lock:
                if time.monotonic() >= self._down_until:
                    logger.error("Redis unavailable, caching skipped for %ds: %s", _RETRY_AFTER_S, exc)
                self._down_until = time.monotonic() + _RETRY_AFTER_S
            return default

    def set(self, key, value, ex=3600):
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        return self._call(None, "set", key, value, ex=ex)

    def get(self, key):
        value = self._call(None, "get", key)
        if value and isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    def delete(self, key):
        return self._call(0, "delete", key)

    def exists(self, key):
        return self._call(0, "exists", key)

    def get_or_set(self, key, value, ex=3600):
        if self.exists(key):
            return self.get(key)
        self.set(key, value, ex=ex)
        return value


redis_client = RedisClient()
