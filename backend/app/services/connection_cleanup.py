"""
Deleting a database connection and everything stored about it:

- its knowledge bases and query history;
- its schema profile and table/column descriptions;
- its retrieval index (embeddings, trigram documents, category values);
- every conversation that queried it at least once, with the messages and the
  agent's checkpoint threads of those conversations;
- its cached engine, Redis keys and in-process schema caches.

App-database rows go in one transaction; the rest is cleaned up after it
commits, and a failure there is logged rather than undoing the delete.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.connection import DBConnection
from app.models.conversation import Conversation, ConversationConnection, ConversationMessage
from app.models.knowledge import KnowledgeBase
from app.models.query_history import QueryHistory
from app.services.redis_client import redis_client
from app.services.schema_index.service import delete_index, forget_connection
from app.utils.db_manager import remove_engine

logger = logging.getLogger(__name__)


def delete_connection(db: Session, conn: DBConnection) -> list[str]:
    """Deletes `conn` and its data. Returns the ids of the deleted conversations."""
    conn_id, user_id = conn.id, conn.user_id
    threads = _checkpoint_threads(db, user_id, conn_id)

    conversation_ids = {
        cid for (cid,) in db.query(ConversationConnection.conversation_id)
        .filter(ConversationConnection.connection_id == conn_id)
    }
    # Turns from before conversation_connections existed are only in the
    # checkpoint thread names ("user:connection:conversation").
    conversation_ids |= {t.split(":", 2)[2] for t in threads if t.count(":") >= 2}
    conversation_ids = sorted(
        cid for (cid,) in db.query(Conversation.id).filter(
            Conversation.id.in_(conversation_ids), Conversation.user_id == user_id)
    ) if conversation_ids else []

    if conversation_ids:
        # Every thread of these conversations, also those on other connections.
        threads |= _conversation_threads(db, user_id, conversation_ids)
        db.query(ConversationMessage).filter(
            ConversationMessage.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
        db.query(Conversation).filter(
            Conversation.id.in_(conversation_ids)).delete(synchronize_session=False)
    db.query(KnowledgeBase).filter(KnowledgeBase.connection_id == conn_id).delete(synchronize_session=False)
    db.query(QueryHistory).filter(QueryHistory.connection_id == conn_id).delete(synchronize_session=False)
    # schema_profiles, schema_annotations and conversation_connections cascade.
    db.delete(conn)
    db.commit()

    remove_engine(conn_id)
    forget_connection(conn_id)
    delete_index(conn_id)
    _delete_threads(threads)
    _delete_redis_keys(user_id, conn_id)
    logger.info("Deleted connection %s with %d conversation(s) and %d agent thread(s)",
                conn_id, len(conversation_ids), len(threads))
    return conversation_ids


def _has_checkpoints(db: Session) -> bool:
    return bool(db.execute(text("SELECT to_regclass('checkpoints')")).scalar())


def _checkpoint_threads(db: Session, user_id: int, conn_id: int) -> set[str]:
    if not _has_checkpoints(db):
        return set()
    rows = db.execute(text("SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id LIKE :p"),
                      {"p": f"{user_id}:{conn_id}:%"})
    return {r[0] for r in rows}


def _conversation_threads(db: Session, user_id: int, conversation_ids: list[str]) -> set[str]:
    if not _has_checkpoints(db):
        return set()
    rows = db.execute(text(
        "SELECT DISTINCT thread_id FROM checkpoints "
        "WHERE split_part(thread_id, ':', 1) = :u AND split_part(thread_id, ':', 3) = ANY(:ids)"),
        {"u": str(user_id), "ids": conversation_ids})
    return {r[0] for r in rows}


def _delete_threads(threads: set[str]) -> None:
    if not threads:
        return
    try:
        from app.services.agent.graph import _get_checkpointer
        saver = _get_checkpointer()
        for thread_id in threads:
            saver.delete_thread(thread_id)
    except Exception as exc:
        logger.warning("Could not delete %d agent checkpoint thread(s): %s", len(threads), exc)


def _delete_redis_keys(user_id: int, conn_id: int) -> None:
    """Schema, preview, knowledge-base and suggestion caches of the connection,
    and the user's cached connection list."""
    try:
        keys = list(redis_client.client.scan_iter(f"*:user:{user_id}:connection:{conn_id}:*"))
        keys.append(f"kb:user:{user_id}:connections:all")
        redis_client.client.delete(*keys)
    except Exception as exc:
        logger.warning("Could not clear cached data of connection %s: %s", conn_id, exc)
