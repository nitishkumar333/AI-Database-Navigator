from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import json
from app.database import get_db
from app.models.user import User
from app.models.connection import DBConnection
from app.models.knowledge import KnowledgeBase
from app.models.query_history import QueryHistory
from app.models.conversation import Conversation, ConversationConnection, ConversationMessage
from app.utils.security import get_current_user
from app.utils.db_manager import get_user_engine
from app.services.display import json_rows
from app.services.sql_agent import SQLAgent
from app.utils.db_manager import get_all_table_names
from app.services.schema_index.service import build_agent_schema

router = APIRouter(prefix="/api/query", tags=["Query"])


class NLQueryRequest(BaseModel):
    question: str


class SQLExecuteRequest(BaseModel):
    sql: str


class ChatRequest(BaseModel):
    question: str
    connection_id: int | None = None
    knowledge_base_id: int | None = None
    conversation_id: str | None = None
    query_id: str | None = None


def _get_connection(conn_id: int, user: User, db: Session) -> DBConnection:
    conn = db.query(DBConnection).filter(
        DBConnection.id == conn_id, DBConnection.user_id == user.id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


# NOTE: /chat must be defined BEFORE /{conn_id} to avoid FastAPI
# matching "chat" as a path parameter for conn_id.


@router.post("/chat")
def chat_query(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    REST endpoint for NL→SQL chat.
    If connection_id is provided, use that connection.
    Otherwise, use the first available connection for the user.
    Returns structured response with SQL, results, and formatted text.
    """
    # Find connection
    conn = None
    if req.connection_id:
        conn = db.query(DBConnection).filter(
            DBConnection.id == req.connection_id,
            DBConnection.user_id == current_user.id,
        ).first()
        if not conn:
            raise HTTPException(status_code=404, detail="Connection not found")
    else:
        conn = db.query(DBConnection).filter(
            DBConnection.user_id == current_user.id
        ).first()
        if not conn:
            raise HTTPException(
                status_code=400,
                detail="No database connections configured. Go to Settings to add a PostgreSQL connection.",
            )

    # Rate limits are enforced before this runs (RateLimitMiddleware); a request
    # refused there is not saved anywhere.
    engine = get_user_engine(conn)

    # If knowledge_base_id provided (which points to a KnowledgeBase)
    # filter to those tables only
    table_filter = None
    if req.knowledge_base_id:
        kb_entry = db.query(KnowledgeBase).filter(
            KnowledgeBase.id == req.knowledge_base_id,
            KnowledgeBase.connection_id == conn.id,
        ).first()
        if kb_entry:
            table_filter = kb_entry.tables
    
    all_tables = get_all_table_names(engine)
    if table_filter:
        # Only use tables that exist in both the filter and the actual DB
        context_tables = [t for t in table_filter if t in all_tables]
        if not context_tables:
            context_tables = all_tables  # Fallback if filter matches nothing
    else:
        context_tables = all_tables
    
    # SQLAgent puts the schema text in the prompt when it is small enough (see
    # AGENT_FULL_SCHEMA_MAX_CHARS), else only the table list; the view is what
    # its schema tools search and describe.
    schema_context, schema_view = build_agent_schema(db, conn, engine, context_tables)

    # The graph is compiled once per process; SQLAgent only bundles this
    # connection's engine, schema and scope for one turn.
    sql_agent = SQLAgent(engine, schema_context, schema_view=schema_view)
    # The agent runs for many seconds without the app database: end the
    # transaction so its connection goes back to the pool meanwhile. Committing
    # expires the loaded rows, so read the ids first: reading them afterwards
    # would query (and hold) a connection again.
    user_id, conn_id = current_user.id, conn.id
    db.commit()
    try:
        result = sql_agent.run_query(
            req.question,
            user_id=user_id,
            conn_id=conn_id,
            conversation_id=req.conversation_id,
        )
    except HTTPException as exc:
        # The LLM provider's rate limit. The agent noted it in its thread; save
        # the turn too, so the conversation shows what the agent remembers.
        _save_turn(db, current_user, conn, req, _rejected(req.question, exc))
        raise

    # One JSON form for the response and the stored turn, so a reloaded answer
    # renders exactly like the live one (numbers stay numbers). The rows are
    # already trimmed by the SQL tools: AgentContext.answer_rows of them, the
    # agent having seen the first answer_rows_shown.
    result = {**result, "rows": json_rows(result.get("rows") or [])}
    _save_turn(db, current_user, conn, req, result)
    return {
        **result,
        "connection_name": conn.name,
        "connection_id": conn.id,
    }


def _rejected(question: str, exc: HTTPException) -> dict:
    """A turn that ended with an HTTP error, in run_query's result shape."""
    detail = str(exc.detail)
    return {"success": False, "question": question, "generated_sql": "", "columns": [],
            "rows": [], "error": detail, "response_text": detail}


def _save_turn(db: Session, user: User, conn: DBConnection, req: ChatRequest, result: dict) -> None:
    """Saves the turn to the query history and, with a conversation_id, as the
    conversation's user and assistant messages."""
    # Save to history
    history = QueryHistory(
        user_id=user.id,
        connection_id=conn.id,
        nl_query=req.question,
        generated_sql=result.get("generated_sql", ""),
        success=result.get("success", False),
        error_message=result.get("error", ""),
    )
    db.add(history)

    # Save conversation messages if conversation_id provided
    if req.conversation_id:
        # Ensure the conversation exists
        conv = db.query(Conversation).filter(
            Conversation.id == req.conversation_id,
            Conversation.user_id == user.id,
        ).first()
        if conv:
            # Remember that this conversation used the connection (deleting the
            # connection deletes the conversation).
            db.execute(
                pg_insert(ConversationConnection)
                .values(conversation_id=conv.id, connection_id=conn.id)
                .on_conflict_do_nothing()
            )
            # Save user message
            user_msg = ConversationMessage(
                conversation_id=req.conversation_id,
                role="user",
                content=req.question,
                message_type="text",
                metadata_json="{}",
                query_id=req.query_id,
            )
            db.add(user_msg)

            # Save assistant response
            assistant_metadata = {
                "generated_sql": result.get("generated_sql", ""),
                "columns": result.get("columns", []),
                "rows": result.get("rows", []),
                "row_count": result.get("row_count"),
                "truncated": result.get("truncated", False),
                "column_meta": result.get("column_meta", []),
                "views": result.get("views", []),
                "success": result.get("success", False),
                "error": result.get("error", ""),
                "assumptions": result.get("assumptions", ""),
            }
            msg_type = "result" if result.get("success") and result.get("rows") else "text"
            assistant_msg = ConversationMessage(
                conversation_id=req.conversation_id,
                role="assistant",
                content=result.get("response_text", ""),
                message_type=msg_type,
                metadata_json=json.dumps(assistant_metadata, default=str),
                query_id=req.query_id,
            )
            db.add(assistant_msg)

    db.commit()
