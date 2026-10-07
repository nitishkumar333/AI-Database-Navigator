from sqlalchemy import create_engine, text, inspect
from sqlalchemy.pool import QueuePool
from app.utils.security import decrypt_value
from cachetools import TTLCache
from fastapi import HTTPException
import re, hashlib
from app.services.redis_client import redis_client

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
        try:
            password = decrypt_value(connection.encrypted_password)
        except Exception as e:
            print(e)
            raise HTTPException(status_code=401, detail="Invalid token")
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


def refine_sql_from_markdown(text_input: str) -> str:
    # Remove markdown code block syntax (```sql, ```, etc.)
    text_input = re.sub(r'```sql\s*', '', text_input)
    text_input = re.sub(r'```\s*', '', text_input)
    
    # Replace \n literals with actual spaces
    text_input = text_input.replace('\\n', ' ')
    
    # Replace actual newlines with spaces
    text_input = text_input.replace('\n', ' ')
    
    # Replace tabs with spaces
    text_input = text_input.replace('\t', ' ')
    
    # Remove extra whitespace (multiple spaces to single space)
    text_input = re.sub(r'\s+', ' ', text_input)
    
    # Clean up whitespace around parentheses and commas
    text_input = re.sub(r'\s*\(\s*', '(', text_input)
    text_input = re.sub(r'\s*\)\s*', ')', text_input)
    text_input = re.sub(r'\s*,\s*', ', ', text_input)
    text_input = re.sub(r'\s*;\s*', ';', text_input)
    
    # Trim leading/trailing whitespace
    text_input = text_input.strip()
    
    # Ensure semicolon at the end if missing
    if text_input and not text_input.endswith(';'):
        text_input += ';'

    return text_input


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
            context_parts.append(f"  TABLE {table_name}: (unable to read schema)")

    schema_str = "\n\n".join(context_parts)
    redis_client.set(cache_key, schema_str, ex=3600)
    return schema_str
