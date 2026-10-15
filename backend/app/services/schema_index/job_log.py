"""
Terminal log of the schema background jobs (profile, index, describe), one
line per step so their progress can be followed live:

    14:02:11 INFO [jobs] conn 91 PROFILE start | SHOP_LARGE (shop_large)
    14:02:13 INFO [jobs] conn 91 PROFILE done | 102 tables, 162 relations | 1.9s
    14:02:16 INFO [jobs] conn 91 INDEX ready | hybrid | 1,186 docs (1,186 embedded), 433 values | 3.1s
    14:02:16 INFO [jobs] conn 91 DESCRIBE start | 102 tables to describe
    14:02:31 INFO [jobs] conn 91 DESCRIBE 5/102 | users, orders, products, employees, product_variants | 14.8s

Lines go to the "jobs" area of the shared log (app/logging_setup.py).
JOB_LOG_LEVEL: INFO (default), WARNING (problems only) or ERROR (off).
"""
from __future__ import annotations

import logging

from app.logging_setup import get_logger


def _log() -> logging.Logger:
    return get_logger("jobs")


def info(conn_id: int, step: str, message: str) -> None:
    _log().info("conn %s %s %s", conn_id, step, message)


def warning(conn_id: int, step: str, message: str) -> None:
    _log().warning("conn %s %s %s", conn_id, step, message)


def names(tables: list[str] | set[str], limit: int = 6) -> str:
    """'a, b, c' or 'a, b, c, ... (+4)' for long lists."""
    tables = list(tables)
    shown = ", ".join(tables[:limit])
    return shown + (f", ... (+{len(tables) - limit})" if len(tables) > limit else "")


def seconds(value: float) -> str:
    return f"{value:.1f}s" if value < 120 else f"{int(value // 60)}m{int(value % 60):02d}s"
