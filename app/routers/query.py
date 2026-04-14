from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from app.database import get_db
from app.models.user import User
from app.models.connection import DBConnection
from app.models.knowledge import KnowledgeBase
from app.models.query_history import QueryHistory
from app.utils.security import get_current_user
from app.utils.db_manager import get_user_engine
from app.services.nl_to_sql import nl_to_sql, execute_raw_sql

router = APIRouter(prefix="/api/query", tags=["Query"])


class NLQueryRequest(BaseModel):
    question: str


class SQLExecuteRequest(BaseModel):
    sql: str


class ChatRequest(BaseModel):
    question: str
    connection_id: int | None = None
    knowledge_base_id: int | None = None


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
    print("req", req)
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

    result = nl_to_sql(conn.id, engine, req.question, table_filter=table_filter)

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
    db.commit()

    # Build formatted response text
    sql = result.get("generated_sql", "")
    rows = result.get("rows", [])
    cols = result.get("columns", [])
    row_count = result.get("row_count", 0)
    latency_ms = result.get("latency_ms", 0)

    if result.get("success"):
        md_table = ""
        if rows and cols:
            md_table = "\n\n| " + " | ".join(str(c) for c in cols) + " |\n"
            md_table += "| " + " | ".join(["---"] * len(cols)) + " |\n"
            for row in rows[:50]:
                md_table += (
                    "| "
                    + " | ".join(str(row.get(c, ""))[:50] for c in cols)
                    + " |\n"
                )
            if row_count > 50:
                md_table += f"\n*Showing 50 of {row_count} rows.*\n"

        response_text = (
            f"**Query executed successfully** ({latency_ms:.0f}ms, {row_count} rows)\n\n"
            f"```sql\n{sql}\n```\n"
            f"{md_table}"
        )
    else:
        error_msg = result.get("error", "Unknown error occurred")
        response_text = f"**Query failed**\n\n"
        if sql:
            response_text += f"```sql\n{sql}\n```\n\n"
        response_text += f"**Error:** {error_msg}"

    return {
        **result,
        "response_text": response_text,
        "connection_name": conn.name,
        "connection_id": conn.id,
    }


@router.post("/{conn_id}")
def natural_language_query(
    conn_id: int,
    req: NLQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Convert natural language to SQL, execute"""
    conn = _get_connection(conn_id, current_user, db)
    engine = get_user_engine(conn)

    result = nl_to_sql(conn_id, engine, req.question)

    # Save to history
    history = QueryHistory(
        user_id=current_user.id,
        connection_id=conn_id,
        nl_query=req.question,
        generated_sql=result.get("generated_sql", ""),
        row_count=result.get("row_count", 0),
        success=result.get("success", False),
        error_message=result.get("error", ""),
        latency_ms=result.get("latency_ms", 0),
    )
    db.add(history)
    db.commit()

    return result


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
