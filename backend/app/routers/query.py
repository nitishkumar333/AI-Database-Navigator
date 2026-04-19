from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import json
from app.database import get_db
from app.models.user import User
from app.models.connection import DBConnection
from app.models.knowledge import KnowledgeBase
from app.models.query_history import QueryHistory
from app.models.conversation import Conversation, ConversationMessage
from app.utils.security import get_current_user
from app.utils.db_manager import get_user_engine
from app.services.sql_agent import SQLAgent
from app.services.validate_sql import get_schema_context, get_all_table_names, execute_raw_sql

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
    
    schema_context = get_schema_context(engine, context_tables)

    print("schema_context", schema_context)

    sql_agent = SQLAgent(engine, schema_context)
    result = sql_agent.run_query(req.question, req.conversation_id or str(conn.id))

    # Save to history
    history = QueryHistory(
        user_id=current_user.id,
        connection_id=conn.id,
        nl_query=req.question,
        generated_sql=result.get("generated_sql", ""),
        row_count=result.get("row_count", 0),
        success=result.get("success", False),
        error_message=result.get("error", ""),
        latency_ms=result.get("latency_ms", 0),
    )
    db.add(history)

    # Save conversation messages if conversation_id provided
    if req.conversation_id:
        # Ensure the conversation exists
        conv = db.query(Conversation).filter(
            Conversation.id == req.conversation_id,
            Conversation.user_id == current_user.id,
        ).first()
        if conv:
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
                "rows": result.get("rows", [])[:100],  # Cap stored rows
                "row_count": result.get("row_count", 0),
                "latency_ms": result.get("latency_ms", 0),
                "success": result.get("success", False),
                "error": result.get("error", ""),
                "display_type": result.get("display_type", "table"),
                "products_data": result.get("products_data", []),
            }
            msg_type = "result" if result.get("success") and (result.get("rows") or result.get("display_type") == "product") else "text"
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

    return {
        **result,
        "connection_name": conn.name,
        "connection_id": conn.id,
    }


@router.post("/{conn_id}/execute-sql")
def execute_sql(
    conn_id: int,
    req: SQLExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute user-edited SQL query."""
    conn = _get_connection(conn_id, current_user, db)
    engine = get_user_engine(conn)

    result = execute_raw_sql(engine, req.sql)

    # Save to history
    history = QueryHistory(
        user_id=current_user.id,
        connection_id=conn_id,
        nl_query="[Manual SQL]",
        generated_sql=req.sql,
        row_count=result.get("row_count", 0),
        success=result.get("success", False),
        error_message=result.get("error", ""),
        latency_ms=result.get("latency_ms", 0),
    )
    db.add(history)
    db.commit()

    return result
