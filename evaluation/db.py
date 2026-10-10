"""Database access for evaluation: engine, schema context, and full-result
execution of gold / predicted SQL."""
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.utils import db_manager
from app.utils.db_manager import get_schema_context


def create_bird_engine(db_url: str, pool_size: int = 4) -> Engine:
    # Same read-only / timeout guard rails as production user engines.
    return create_engine(
        db_url,
        pool_size=pool_size,
        max_overflow=pool_size,
        pool_pre_ping=True,
        connect_args={
            "options": "-c default_transaction_read_only=on",
            "connect_timeout": 10,
        },
    )


class _NullCache:
    def get(self, key):
        return None

    def set(self, key, value, ex=3600):
        return None


def disable_schema_cache() -> None:
    """get_schema_context() caches in Redis. Evaluation builds each schema
    once per run anyway, so it shouldn't need (or pollute) Redis."""
    db_manager.redis_client = _NullCache()


def build_schema_context(engine: Engine, tables: list[str]) -> str:
    # Reuse the production builder so the agent sees exactly the same format.
    return get_schema_context(engine, tables)


@dataclass
class ExecResult:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    error: str | None = None
    timed_out: bool = False
    truncated: bool = False
    seconds: float = 0.0


def execute_sql(
    engine: Engine, sql: str, *, timeout_ms: int = 60_000, max_rows: int = 100_000
) -> ExecResult:
    """Execute a query in a read-only transaction and fetch the full result
    (unlike the agent tool, which caps rows at 50)."""
    start = time.perf_counter()
    try:
        with engine.begin() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
            # Raw DBAPI cursor with no parameters, so psycopg2 doesn't treat
            # `%` in LIKE patterns (or `:name` text) as placeholders.
            cursor = conn.connection.dbapi_connection.cursor()
            try:
                cursor.execute(sql)
                columns = [d[0] for d in cursor.description or []]
                fetched = cursor.fetchmany(max_rows + 1) if cursor.description else []
            finally:
                cursor.close()
    except Exception as exc:
        message = str(getattr(exc, "orig", exc)).strip()
        return ExecResult(
            ok=False,
            error=message,
            timed_out="statement timeout" in message.lower(),
            seconds=time.perf_counter() - start,
        )
    rows: list[Any] = [tuple(r) for r in fetched[:max_rows]]
    return ExecResult(
        ok=True,
        columns=columns,
        rows=rows,
        truncated=len(fetched) > max_rows,
        seconds=time.perf_counter() - start,
    )
