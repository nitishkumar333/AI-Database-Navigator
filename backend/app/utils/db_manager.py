from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from typing import Dict
from app.utils.security import decrypt_value
from cachetools import TTLCache

# Cache of user DB engines
# Prevents memory leaks by caching up to 100 engines, 
# and dropping connections after 1 hour (3600 seconds) of inactivity
_engine_cache = TTLCache(maxsize=100, ttl=3600)


def get_user_db_url(host: str, port: int, db_name: str, username: str, password: str) -> str:
    return f"postgresql://{username}:{password}@{host}:{port}/{db_name}"


def get_user_engine(connection):
    """Get or create a SQLAlchemy engine for a user's database connection."""
    cache_key = f"{connection.user_id}_{connection.id}"
    if cache_key not in _engine_cache:
        password = decrypt_value(connection.encrypted_password)
        url = get_user_db_url(
            connection.host,
            connection.port,
            connection.db_name,
            connection.username,
            password,
        )
        _engine_cache[cache_key] = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_pre_ping=True,
        )
    return _engine_cache[cache_key]


def test_connection(host: str, port: int, db_name: str, username: str, password: str) -> dict:
    """Test a database connection. Returns success status and message."""
    try:
        url = get_user_db_url(host, port, db_name, username, password)
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return {"success": True, "message": "Connection successful"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def remove_engine(conn_id: int):
    """Remove and dispose a cached engine."""
    keys_to_remove = [k for k in _engine_cache if k.endswith(f"_{conn_id}")]
    for key in keys_to_remove:
        _engine_cache[key].dispose()
        del _engine_cache[key]
