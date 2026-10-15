"""
Schema profiles for user connections: background (re)profiling, schema
context for the agent, and description editing.

Flow
- Creating a connection (or its first use, for connections that predate
  profiling) schedules a profile job. Until it finishes, the agent gets the
  basic schema, so nothing ever waits on it.
- Every SCHEMA_CHECK_INTERVAL_S a cheap catalog fingerprint is compared with
  the stored one; a change schedules a re-profile. Users can also re-profile
  on demand (POST /api/schema/{id}/profile/refresh, "Re-profile" button).
- After profiling, tables whose structure changed (or that were never
  described) get LLM descriptions, capped per run. Descriptions written by
  users always win and are never overwritten.
- The retrieval index (indexer.py: embeddings, trigrams, category values) is
  updated after profiling, after describing and after a description edit.
  Updates only re-embed documents whose text changed.

Jobs run on a small in-process thread pool. A Redis lock stops two backend
processes profiling the same connection at once; without Redis an in-process
lock is used instead.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from cachetools import TTLCache
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models.connection import DBConnection
from app.models.schema_profile import SchemaAnnotation, SchemaProfileRecord
from app.services.redis_client import redis_client
from app.services.schema_index.index_store import get_store
from app.services.schema_index.indexer import HybridIndex, update_index
from app.services.schema_index.profiler import SchemaProfile, profile_database, schema_fingerprint
from app.services.schema_index.render import Descriptions, render_schema
from app.services.schema_index.retriever import SchemaView
from app.utils.db_manager import get_schema_context as basic_schema_context
from app.utils.db_manager import get_user_engine

logger = logging.getLogger(__name__)

_JOB_LOCK_TTL_S = 1800
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="schema-profile")
_local_jobs: set[int] = set()
_local_lock = threading.Lock()
_last_check: dict[int, float] = {}
_context_cache: TTLCache = TTLCache(maxsize=256, ttl=3600)
# (conn_id, version) -> (SchemaProfile, Descriptions), parsed once per version.
_profile_cache: TTLCache = TTLCache(maxsize=32, ttl=3600)
_context_lock = threading.Lock()


# ──────────────────────────────────────────────────────────────────────────────
# Job scheduling
# ──────────────────────────────────────────────────────────────────────────────

def _acquire(conn_id: int) -> bool:
    try:
        return bool(redis_client.client.set(
            f"schema_profile_job:{conn_id}", "1", nx=True, ex=_JOB_LOCK_TTL_S))
    except Exception:
        with _local_lock:
            if conn_id in _local_jobs:
                return False
            _local_jobs.add(conn_id)
            return True


def _release(conn_id: int) -> None:
    try:
        redis_client.client.delete(f"schema_profile_job:{conn_id}")
    except Exception:
        pass
    with _local_lock:
        _local_jobs.discard(conn_id)


def schedule_refresh(conn_id: int, *, describe: bool | None = None, force: bool = False) -> bool:
    """Profile (and describe) a connection in the background.
    False if profiling is disabled or a job for it is already running.
    force=True always re-profiles instead of reusing a twin connection's profile."""
    if not get_settings().SCHEMA_PROFILING_ENABLED or not _acquire(conn_id):
        return False

    def job():
        try:
            refresh_profile(conn_id, describe=describe, force=force)
        except Exception:
            logger.exception("Schema profile job failed for connection %s", conn_id)
        finally:
            _release(conn_id)

    _executor.submit(job)
    return True


def _due(conn_id: int) -> bool:
    """True at most once per SCHEMA_CHECK_INTERVAL_S per connection."""
    now = time.monotonic()
    with _local_lock:
        if now - _last_check.get(conn_id, -1e9) < get_settings().SCHEMA_CHECK_INTERVAL_S:
            return False
        _last_check[conn_id] = now
        return True


def _check_for_changes(conn_id: int, engine, stored_hash: str | None) -> None:
    """Re-profile when the catalog fingerprint no longer matches."""
    if not _due(conn_id):
        return

    def job():
        try:
            current, _ = schema_fingerprint(engine)
            if current != stored_hash:
                logger.info("Schema of connection %s changed; re-profiling", conn_id)
                schedule_refresh(conn_id)
        except Exception as exc:
            logger.info("Schema fingerprint check failed for connection %s: %s", conn_id, exc)

    _executor.submit(job)


# ──────────────────────────────────────────────────────────────────────────────
# The job itself
# ──────────────────────────────────────────────────────────────────────────────

def _record(db: Session, conn_id: int) -> SchemaProfileRecord:
    record = db.query(SchemaProfileRecord).filter_by(connection_id=conn_id).first()
    if record is None:
        record = SchemaProfileRecord(connection_id=conn_id, status="pending",
                                     description_status="idle", described_tables={}, version=0)
        db.add(record)
        db.commit()
        db.refresh(record)
    return record


def _reuse_twin(db: Session, conn: DBConnection, record: SchemaProfileRecord, engine) -> bool:
    """Copy the profile and generated descriptions of another connection to
    the same database with the same login, if its schema is unchanged.

    Several users can connect to the same database (e.g. a shared demo DB);
    this stops each connection from being profiled and described (LLM calls)
    again. Same login means same visible schema, so nothing leaks between users.
    User-written descriptions are never copied.
    """
    current_hash, _ = schema_fingerprint(engine)
    twin = (
        db.query(SchemaProfileRecord)
        .join(DBConnection, DBConnection.id == SchemaProfileRecord.connection_id)
        .filter(
            DBConnection.id != conn.id,
            DBConnection.host == conn.host,
            DBConnection.port == conn.port,
            DBConnection.db_name == conn.db_name,
            DBConnection.username == conn.username,
            SchemaProfileRecord.status == "ready",
            SchemaProfileRecord.schema_hash == current_hash,
        )
        .order_by(SchemaProfileRecord.version.desc())
        .first()
    )
    if twin is None:
        return False
    user_rows = {
        (a.table_name, a.column_name) for a in db.query(SchemaAnnotation).filter_by(
            connection_id=conn.id, source="user")
    }
    db.query(SchemaAnnotation).filter_by(connection_id=conn.id, source="generated").delete()
    for a in db.query(SchemaAnnotation).filter_by(connection_id=twin.connection_id, source="generated"):
        if (a.table_name, a.column_name) not in user_rows:
            db.add(SchemaAnnotation(connection_id=conn.id, table_name=a.table_name,
                                    column_name=a.column_name, description=a.description,
                                    source="generated"))
    record.profile = twin.profile
    record.schema_hash = twin.schema_hash
    record.described_tables = dict(twin.described_tables or {})
    record.status = "ready"
    record.profiled_at = twin.profiled_at
    record.version += 1
    db.commit()
    logger.info("Connection %s reused the schema profile of connection %s",
                conn.id, twin.connection_id)
    return True


def refresh_profile(conn_id: int, *, describe: bool | None = None, force: bool = False,
                    llm=None) -> None:
    """Profile a connection and describe what needs describing (blocking)."""
    settings = get_settings()
    describe = settings.SCHEMA_DESCRIBE_ENABLED if describe is None else describe
    db = SessionLocal()
    try:
        conn = db.get(DBConnection, conn_id)
        if conn is None:
            return
        record = _record(db, conn_id)
        record.status, record.error = "running", None
        db.commit()

        try:
            engine = get_user_engine(conn)
            if not force and _reuse_twin(db, conn, record, engine):
                twin_profile = SchemaProfile.from_dict(record.profile)
                _index(db, conn_id, twin_profile, engine)
                if describe:
                    _describe(db, record, twin_profile, llm)
                    _index(db, conn_id, twin_profile, engine)
                return
            profile = profile_database(engine)
        except Exception as exc:
            logger.warning("Profiling connection %s failed: %s", conn_id, exc)
            record.status, record.error = "failed", str(exc)[:1000]
            db.commit()
            return

        record.profile = profile.to_dict()
        record.schema_hash = profile.schema_hash
        record.status = "ready"
        record.profiled_at = datetime.now(timezone.utc)
        # Descriptions of a table whose structure changed are re-generated.
        described = dict(record.described_tables or {})
        record.described_tables = {
            t: h for t, h in described.items()
            if t in profile.tables and profile.tables[t].structure_hash == h
        }
        _drop_generated(db, conn_id, set(described) - set(record.described_tables))
        record.version += 1
        db.commit()
        logger.info("Profiled connection %s: %d tables, %d relations",
                    conn_id, len(profile.tables), len(profile.relations))

        # Index right away (descriptions can take a while), again once described.
        _index(db, conn_id, profile, engine)
        if describe:
            _describe(db, record, profile, llm)
            _index(db, conn_id, profile, engine)
        elif record.description_status == "idle":
            record.description_status = "disabled"
            db.commit()
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# Retrieval index
# ──────────────────────────────────────────────────────────────────────────────

def index_key(conn_id: int) -> str:
    return f"conn:{conn_id}"


def _index(db: Session, conn_id: int, profile: SchemaProfile, engine) -> None:
    """Update the connection's retrieval index. Failures are logged, never
    raised: without an index the agent falls back to keyword search."""
    try:
        if db.get(DBConnection, conn_id) is None:      # deleted while profiling
            return
        update_index(index_key(conn_id), profile, load_descriptions(db, conn_id),
                     source_engine=engine)
    except Exception:
        logger.exception("Indexing the schema of connection %s failed", conn_id)


def schedule_index(conn_id: int) -> None:
    """Re-index in the background (after a description edit)."""
    if not get_settings().SCHEMA_RETRIEVAL_ENABLED:
        return

    def job():
        db = SessionLocal()
        try:
            conn = db.get(DBConnection, conn_id)
            record = db.query(SchemaProfileRecord).filter_by(connection_id=conn_id).first()
            if conn is None or record is None or not record.profile:
                return
            _index(db, conn_id, SchemaProfile.from_dict(record.profile), get_user_engine(conn))
        except Exception:
            logger.exception("Re-indexing connection %s failed", conn_id)
        finally:
            db.close()

    _executor.submit(job)


_index_attempts: dict[int, float] = {}


def _index_due(conn_id: int) -> bool:
    """True at most once per SCHEMA_CHECK_INTERVAL_S per connection."""
    now = time.monotonic()
    with _local_lock:
        if now - _index_attempts.get(conn_id, -1e9) < get_settings().SCHEMA_CHECK_INTERVAL_S:
            return False
        _index_attempts[conn_id] = now
        return True


def forget_connection(conn_id: int) -> None:
    """Drop the in-process caches and timers of a deleted connection."""
    with _context_lock:
        for cache in (_context_cache, _profile_cache):
            for key in [k for k in list(cache.keys()) if k[0] == conn_id]:
                cache.pop(key, None)
    with _local_lock:
        _last_check.pop(conn_id, None)
        _index_attempts.pop(conn_id, None)


def delete_index(conn_id: int) -> None:
    try:
        store = get_store()
        if store is not None:
            store.delete(index_key(conn_id))
    except Exception as exc:
        logger.warning("Could not delete the schema index of connection %s: %s", conn_id, exc)


def _drop_generated(db: Session, conn_id: int, tables: set[str]) -> None:
    if tables:
        db.query(SchemaAnnotation).filter(
            SchemaAnnotation.connection_id == conn_id,
            SchemaAnnotation.table_name.in_(tables),
            SchemaAnnotation.source == "generated",
        ).delete(synchronize_session=False)


def _describe(db: Session, record: SchemaProfileRecord, profile: SchemaProfile, llm) -> None:
    from app.services.llm_factory import create_chat_model
    from app.services.schema_index.describer import describe_tables

    done = record.described_tables or {}
    pending = sorted(t for t, table in profile.tables.items() if done.get(t) != table.structure_hash)
    if not pending:
        record.description_status = "done"
        db.commit()
        return
    limit = get_settings().SCHEMA_DESCRIBE_MAX_TABLES
    batch = pending[:limit]
    record.description_status = "running"
    db.commit()

    try:
        llm = llm or create_chat_model(max_retries=2)
    except Exception as exc:          # e.g. no API key configured
        record.description_status, record.error = "failed", f"describe: {exc}"[:1000]
        db.commit()
        return

    def save(table: str, docs: dict) -> None:
        user_rows = {
            a.column_name for a in db.query(SchemaAnnotation.column_name).filter_by(
                connection_id=record.connection_id, table_name=table, source="user")
        }
        _drop_generated(db, record.connection_id, {table})
        entries = {"": docs["description"], **docs["columns"]}
        for column, description in entries.items():
            if column not in user_rows and description:
                db.add(SchemaAnnotation(connection_id=record.connection_id, table_name=table,
                                        column_name=column, description=description,
                                        source="generated"))
        record.described_tables = {**(record.described_tables or {}),
                                   table: profile.tables[table].structure_hash}
        record.version += 1
        db.commit()

    described = describe_tables(llm, profile, batch, on_described=save)
    complete = len(described) == len(pending)
    record.description_status = "done" if complete else ("partial" if described else "failed")
    db.commit()
    logger.info("Described %d/%d tables for connection %s",
                len(described), len(pending), record.connection_id)


# ──────────────────────────────────────────────────────────────────────────────
# Schema context for the agent
# ──────────────────────────────────────────────────────────────────────────────

def load_descriptions(db: Session, conn_id: int) -> Descriptions:
    docs: Descriptions = {}
    for row in db.query(SchemaAnnotation).filter_by(connection_id=conn_id):
        entry = docs.setdefault(row.table_name, {"description": None, "columns": {}})
        if row.column_name:
            entry["columns"][row.column_name] = row.description
        else:
            entry["description"] = row.description
    return docs


def _profile_meta(db: Session, conn: DBConnection, engine):
    """(version, schema_hash) of the connection's profile, or None if there is
    none yet. Also keeps profiles current: schedules the first profile (or a
    retry after a failure) and the periodic schema-change check."""
    if not get_settings().SCHEMA_PROFILING_ENABLED:
        return None
    meta = (db.query(SchemaProfileRecord.version, SchemaProfileRecord.schema_hash,
                     SchemaProfileRecord.status)
            .filter_by(connection_id=conn.id).first())
    if meta is None or meta.schema_hash is None:
        # Never profiled, or the first attempt failed (retried at most once per interval).
        if meta is None or (meta.status == "failed" and _due(conn.id)):
            schedule_refresh(conn.id)
        return None
    _check_for_changes(conn.id, engine, meta.schema_hash)
    return meta


def build_schema_context(db: Session, conn: DBConnection, engine, tables: list[str]) -> str:
    """Schema text for `tables`: enriched once a profile exists, basic until then."""
    meta = _profile_meta(db, conn, engine)
    if meta is None:
        return basic_schema_context(engine, tables)

    key = (conn.id, meta.version, hashlib.md5(",".join(sorted(tables)).encode()).hexdigest())
    with _context_lock:
        cached = _context_cache.get(key)
    if cached is not None:
        return cached

    profile, descriptions = _profile_and_descriptions(db, conn.id, meta.version)
    context = render_schema(profile, tables, descriptions)
    missing = [t for t in tables if t not in profile.tables]
    if missing:       # created since the last profile; the fingerprint check will catch up
        context = "\n\n".join(p for p in (context, basic_schema_context(engine, missing)) if p)
    with _context_lock:
        _context_cache[key] = context
    return context


def _profile_and_descriptions(db: Session, conn_id: int, version: int):
    key = (conn_id, version)
    with _context_lock:
        cached = _profile_cache.get(key)
    if cached is None:
        record = db.query(SchemaProfileRecord).filter_by(connection_id=conn_id).first()
        cached = (SchemaProfile.from_dict(record.profile), load_descriptions(db, conn_id))
        with _context_lock:
            _profile_cache[key] = cached
    return cached


def build_schema_view(db: Session, conn: DBConnection, engine, tables: list[str]) -> SchemaView:
    """What the agent's schema tools (search_schema, describe_tables,
    find_values) see: `tables` with their profile and descriptions, or names,
    types and keys only until the connection has been profiled."""
    profile = descriptions = index = None
    meta = _profile_meta(db, conn, engine)
    if meta is not None:
        profile, descriptions = _profile_and_descriptions(db, conn.id, meta.version)
        index = HybridIndex.for_key(index_key(conn.id))
        if index is None and _index_due(conn.id):
            schedule_index(conn.id)       # profiled before indexing existed, or it failed
    return SchemaView(tables, profile=profile, descriptions=descriptions, engine=engine,
                      index=index)


# ──────────────────────────────────────────────────────────────────────────────
# Status and description editing (API)
# ──────────────────────────────────────────────────────────────────────────────

def profile_status(db: Session, conn_id: int) -> dict:
    record = db.query(SchemaProfileRecord).filter_by(connection_id=conn_id).first()
    if record is None:
        return {"status": "none", "description_status": "idle", "tables": []}
    profile = SchemaProfile.from_dict(record.profile) if record.profile else None
    docs = load_descriptions(db, conn_id)
    sources = {
        (a.table_name, a.column_name): a.source
        for a in db.query(SchemaAnnotation).filter_by(connection_id=conn_id)
    }
    tables = []
    if profile:
        for name, table in sorted(profile.tables.items()):
            tables.append({
                "name": name,
                "row_count": table.row_count,
                "column_count": len(table.columns),
                "description": (docs.get(name) or {}).get("description") or table.comment,
                "description_source": sources.get((name, "")) or ("comment" if table.comment else None),
            })
    return {
        "status": record.status,
        "description_status": record.description_status,
        "error": record.error,
        "profiled_at": record.profiled_at.isoformat() if record.profiled_at else None,
        "relation_count": len(profile.relations) if profile else 0,
        "index": _index_status(conn_id),
        "tables": tables,
    }


def _index_status(conn_id: int) -> dict:
    store = get_store()
    if store is None:
        return {"status": "unavailable"}
    state = store.state(index_key(conn_id)) or {}
    return {
        "status": state.get("status", "none"),
        "error": state.get("error"),
        "documents": state.get("doc_count", 0),
        "embedded": state.get("embedded_count", 0),
        "values": state.get("value_count", 0),
        "embedding_model": state.get("embedding_model"),
        "updated_at": state["updated_at"].isoformat() if state.get("updated_at") else None,
    }


def table_details(db: Session, conn_id: int, table_name: str) -> dict | None:
    """Description and profile facts for one table; None if it isn't profiled."""
    record = db.query(SchemaProfileRecord).filter_by(connection_id=conn_id).first()
    if record is None or not record.profile:
        return None
    profile = SchemaProfile.from_dict(record.profile)
    table = profile.tables.get(table_name)
    if table is None:
        return None
    rows = {
        a.column_name: a for a in db.query(SchemaAnnotation).filter_by(
            connection_id=conn_id, table_name=table_name)
    }

    def doc(column: str, comment: str | None) -> tuple[str | None, str | None]:
        row = rows.get(column)
        if row:
            return row.description, row.source
        return (comment, "comment") if comment else (None, None)

    relations = [r for r in profile.relations if r.from_table == table_name]
    columns = []
    for col in table.columns:
        description, source = doc(col.name, col.comment)
        fk = next((r for r in relations if r.from_columns == [col.name]), None)
        columns.append({
            "name": col.name,
            "data_type": col.data_type,
            "description": description,
            "description_source": source,
            "null_frac": col.null_frac,
            "distinct_count": col.distinct_count,
            "sample_values": col.sample_values,
            "text_format": col.text_format,
            "min_value": col.min_value,
            "max_value": col.max_value,
            "relation": {"table": fk.to_table, "column": fk.to_columns[0], "source": fk.source}
            if fk else None,
        })
    description, source = doc("", table.comment)
    return {
        "name": table_name,
        "row_count": table.row_count,
        "description": description,
        "description_source": source,
        "columns": columns,
    }


def set_description(db: Session, conn_id: int, table_name: str, column_name: str,
                    description: str) -> None:
    """Save a user description ("" for the table itself). Empty text removes
    the override; a generated description returns on the next refresh."""
    record = db.query(SchemaProfileRecord).filter_by(connection_id=conn_id).first()
    if record is None or not record.profile:
        raise LookupError("This connection has not been profiled yet")
    table = SchemaProfile.from_dict(record.profile).tables.get(table_name)
    if table is None or (column_name and table.column(column_name) is None):
        raise LookupError("Unknown table or column")

    row = db.query(SchemaAnnotation).filter_by(
        connection_id=conn_id, table_name=table_name, column_name=column_name).first()
    description = description.strip()
    if not description:
        if row:
            db.delete(row)
        # Let the next refresh generate it again.
        record.described_tables = {
            t: h for t, h in (record.described_tables or {}).items() if t != table_name}
    elif row:
        row.description, row.source = description, "user"
    else:
        db.add(SchemaAnnotation(connection_id=conn_id, table_name=table_name,
                                column_name=column_name, description=description, source="user"))
    record.version += 1
    db.commit()
    schedule_index(conn_id)
