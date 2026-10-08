import ipaddress
import logging
import re
import socket
import hashlib
import threading

from cachetools import TTLCache
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import URL as _SAURL
from sqlalchemy.pool import QueuePool
from fastapi import HTTPException

from app.utils.security import decrypt_value
from app.services.redis_client import redis_client

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Engine cache with proper disposal and thread safety
#
# Plain TTLCache evicts engines without calling .dispose(), leaking pooled
# connections.  This subclass overrides popitem (called on maxsize eviction)
# and __delitem__ (called on explicit removal) to dispose the engine.
# All access is guarded by _engine_lock since TTLCache is not thread-safe.
# ──────────────────────────────────────────────────────────────────────────────
class _DisposingEngineCache(TTLCache):
    """TTLCache that disposes SQLAlchemy engines on eviction / removal."""

    def popitem(self):
        key, engine = super().popitem()
        try:
            engine.dispose()
            logger.debug("Disposed evicted engine for %s", key)
        except Exception:
            logger.warning("Failed to dispose evicted engine for %s", key, exc_info=True)
        return key, engine

    def __delitem__(self, key):
        try:
            engine = self[key]          # grab before it's gone
        except KeyError:
            engine = None
        super().__delitem__(key)
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                logger.warning("Failed to dispose engine for %s", key, exc_info=True)


_engine_cache = _DisposingEngineCache(maxsize=100, ttl=3600)
_engine_lock = threading.Lock()


# ──────────────────────────────────────────────────────────────────────────────
# Host validation (SSRF protection)
#
# Users supply host/port, which means they can probe cloud metadata endpoints
# (169.254.169.254) via SSRF.  We block link-local addresses while keeping
# private and loopback open — this is a database navigator and users
# legitimately connect to databases on private networks.
# ──────────────────────────────────────────────────────────────────────────────
def _validate_db_host(host: str, port: int) -> None:
    """Block connections to link-local addresses (cloud metadata SSRF)."""
    try:
        addrs = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError("Unable to resolve database host")

    for _, _, _, _, sockaddr in addrs:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_link_local:
            raise ValueError("Connection to this address is not allowed")


# ──────────────────────────────────────────────────────────────────────────────
# URL builder
# ──────────────────────────────────────────────────────────────────────────────
def get_user_db_url(host: str, port: int, db_name: str, username: str, password: str) -> str:
    """Build a PostgreSQL connection URL that is safe for passwords with special characters."""
    return _SAURL.create(
        drivername="postgresql",
        username=username,
        password=password,
        host=host,
        port=port,
        database=db_name,
    ).render_as_string(hide_password=False)


# ──────────────────────────────────────────────────────────────────────────────
# Engine management
# ──────────────────────────────────────────────────────────────────────────────
def get_user_engine(connection):
    """Get or create a SQLAlchemy engine for a user's database connection.

    Engines are cached per (user_id, connection_id).  Each engine enforces
    read-only transactions and a 15-second statement timeout at the
    connection level as defence-in-depth on top of SafeSqlExecutor.
    """
    cache_key = (connection.user_id, connection.id)

    with _engine_lock:
        if cache_key in _engine_cache:
            return _engine_cache[cache_key]

    try:
        password = decrypt_value(connection.encrypted_password)
    except Exception:
        logger.exception("Failed to decrypt password for connection %s", connection.id)
        raise HTTPException(
            status_code=500,
            detail="Failed to decrypt database credentials. The encryption key may have changed.",
        )

    url = get_user_db_url(
        connection.host,
        connection.port,
        connection.db_name,
        connection.username,
        password,
    )

    engine = create_engine(
        url,
        poolclass=QueuePool,
        pool_size=2,
        max_overflow=3,
        pool_timeout=30,
        pool_pre_ping=True,
        connect_args={
            "options": "-c default_transaction_read_only=on -c statement_timeout=15000",
            "connect_timeout": 10,
        },
    )

    with _engine_lock:
        # Double-check: another thread may have created it while we were busy
        if cache_key in _engine_cache:
            engine.dispose()
            return _engine_cache[cache_key]
        _engine_cache[cache_key] = engine

    return engine


def test_connection(host: str, port: int, db_name: str, username: str, password: str) -> dict:
    """Test a database connection. Returns success status and a sanitized message."""
    try:
        _validate_db_host(host, port)
    except ValueError as e:
        return {"success": False, "message": str(e)}

    engine = None
    try:
        url = get_user_db_url(host, port, db_name, username, password)
        engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"success": True, "message": "Connection successful"}
    except Exception as e:
        logger.warning("Connection test failed for %s:%s/%s: %s", host, port, db_name, e)
        # Return a user-friendly message instead of raw driver internals
        raw = str(getattr(e, "orig", e)).lower()
        if "could not connect" in raw or "connection refused" in raw:
            return {"success": False, "message": "Could not connect to the database. Check host, port, and firewall rules."}
        if "password authentication failed" in raw:
            return {"success": False, "message": "Authentication failed. Check username and password."}
        if "does not exist" in raw:
            return {"success": False, "message": f"Database '{db_name}' does not exist on the server."}
        if "timeout" in raw:
            return {"success": False, "message": "Connection timed out. Check host and port."}
        return {"success": False, "message": "Connection failed. Check your connection details."}
    finally:
        if engine is not None:
            engine.dispose()


def remove_engine(conn_id: int):
    """Remove and dispose a cached engine."""
    with _engine_lock:
        keys_to_remove = [k for k in _engine_cache if k[1] == conn_id]
        for key in keys_to_remove:
            del _engine_cache[key]     # __delitem__ calls .dispose()


# ──────────────────────────────────────────────────────────────────────────────
# SQL cleanup
# ──────────────────────────────────────────────────────────────────────────────
def refine_sql_from_markdown(text_input: str) -> str:
    """Strip markdown code-fence wrappers from LLM-generated SQL.

    Only removes ````` fences.  The SQL content is left intact so that
    ``--`` line comments, string literals, and whitespace are preserved.
    The previous implementation collapsed all whitespace and edited around
    parentheses and commas, which corrupted comments and string values.
    """
    # Remove opening fence: ```sql or just ```
    text_input = re.sub(r'```sql\s*\n?', '', text_input)
    # Remove closing fence: ```
    text_input = re.sub(r'\n?```', '', text_input)
    return text_input.strip()


# ──────────────────────────────────────────────────────────────────────────────
# Schema introspection
# ──────────────────────────────────────────────────────────────────────────────
def get_all_table_names(engine) -> list:
    url_str = str(engine.url)
    url_hash = hashlib.md5(url_str.encode()).hexdigest()
    cache_key = f"tables:{url_hash}"
    
    cached_tables = redis_client.get(cache_key)
    if cached_tables:
        return cached_tables
        
    inspector = inspect(engine)
    all_tables = inspector.get_table_names()
    
    redis_client.set(cache_key, all_tables, ex=3600)
    return all_tables


def get_schema_context(engine, table_names: list) -> str:
    """Build schema context string for the given tables."""
    url_str = str(engine.url)
    table_names_sorted = sorted(table_names)
    tables_hash = hashlib.md5((url_str + ":" + ",".join(table_names_sorted)).encode()).hexdigest()
    cache_key = f"schema:{tables_hash}"
    
    cached_schema = redis_client.get(cache_key)
    if cached_schema:
        return cached_schema

    inspector = inspect(engine)
    context_parts = []

    for table_name in table_names:
        try:
            columns = inspector.get_columns(table_name)
            pk = inspector.get_pk_constraint(table_name)
            fks = inspector.get_foreign_keys(table_name)

            col_lines = []
            pk_cols = pk.get("constrained_columns", []) if pk else []
            for col in columns:
                flags = []
                if col["name"] in pk_cols:
                    flags.append("PRIMARY KEY")
                if not col.get("nullable", True):
                    flags.append("NOT NULL")
                flag_str = f" ({', '.join(flags)})" if flags else ""
                col_lines.append(f"    {col['name']} {col['type']}{flag_str}")

            fk_lines = []
            for fk in fks:
                fk_lines.append(
                    f"    FOREIGN KEY ({', '.join(fk['constrained_columns'])}) "
                    f"REFERENCES {fk['referred_table']}({', '.join(fk['referred_columns'])})"
                )

            table_def = f"  TABLE {table_name}:\n" + "\n".join(col_lines)
            if fk_lines:
                table_def += "\n  Foreign Keys:\n" + "\n".join(fk_lines)

            context_parts.append(table_def)
        except Exception:
            logger.warning("Failed to read schema for table %s", table_name, exc_info=True)
            context_parts.append(f"  TABLE {table_name}: (unable to read schema)")

    schema_str = "\n\n".join(context_parts)
    redis_client.set(cache_key, schema_str, ex=3600)
    return schema_str
