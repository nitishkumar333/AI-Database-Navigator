from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

settings = get_settings()

# Per worker process: up to 10 connections here plus 5 for the agent's
# checkpointer (agent/graph.py). With 4 workers (Dockerfile) that is 60 of
# Postgres' default 100. Requests hold one only briefly: a chat releases its
# connection while the agent runs.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.models import user, connection, knowledge, query_history, conversation, schema_profile  # noqa
    Base.metadata.create_all(bind=engine)
    _migrate()


# Foreign keys to db_connections that create_all doesn't update on existing
# tables: (table, constraint). Deleting a connection deletes these rows.
_CASCADE_FKS = [
    ("knowledge_base", "knowledge_base_connection_id_fkey"),
    ("query_history", "query_history_connection_id_fkey"),
]


# Indexes on foreign-key columns (index=True in the models) that create_all
# doesn't add to existing tables: (table, column).
_FK_INDEXES = [
    ("conversation_messages", "conversation_id"),
    ("conversations", "user_id"),
    ("query_history", "user_id"),
    ("query_history", "connection_id"),
    ("db_connections", "user_id"),
    ("knowledge_base", "connection_id"),
]


def _migrate() -> None:
    """Idempotent schema fixes for databases created by older versions."""
    with engine.begin() as conn:
        # Every worker process migrates at startup: one at a time.
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('sqlnav_migrate'))"))
        conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS suggestions JSON"))
        for table, column in _FK_INDEXES:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table} ({column})"))
        for table, name in _CASCADE_FKS:
            rule = conn.execute(text(
                "SELECT confdeltype FROM pg_constraint WHERE conname = :n"), {"n": name}).scalar()
            if rule is not None and rule != "c":
                conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT {name}"))
                conn.execute(text(
                    f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY (connection_id) "
                    f"REFERENCES db_connections(id) ON DELETE CASCADE"))
        # Conversations that queried a connection before conversation_connections
        # existed: the agent's checkpoint threads are named "user:connection:conversation".
        if conn.execute(text("SELECT to_regclass('checkpoints')")).scalar():
            conn.execute(text("""
                INSERT INTO conversation_connections (conversation_id, connection_id, first_used_at)
                SELECT c.id, dc.id, now()
                FROM (SELECT DISTINCT thread_id FROM checkpoints) t
                JOIN conversations c ON c.id = split_part(t.thread_id, ':', 3)
                                    AND c.user_id::text = split_part(t.thread_id, ':', 1)
                JOIN db_connections dc ON dc.id::text = split_part(t.thread_id, ':', 2)
                                      AND dc.user_id = c.user_id
                ON CONFLICT DO NOTHING
            """))
