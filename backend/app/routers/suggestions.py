from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import json

from app.database import get_db
from app.models.user import User
from app.models.connection import DBConnection
from app.models.knowledge import KnowledgeBase
from app.utils.security import get_current_user
from app.utils.db_manager import get_user_engine
from app.services.validate_sql import get_schema_context
from app.services.nl_to_sql import get_llm
from sqlalchemy import inspect

router = APIRouter(prefix="/api/suggestions", tags=["Suggestions"])


class InitialSuggestionsRequest(BaseModel):
    connection_id: int
    knowledge_base_id: Optional[int] = None


class ConversationSuggestionsRequest(BaseModel):
    connection_id: int
    knowledge_base_id: Optional[int] = None
    conversation_history: List[dict] = []  # [{role: "user"|"assistant", content: "..."}]


class SuggestionsResponse(BaseModel):
    suggestions: List[str]


def _get_schema_for_request(
    connection_id: int,
    knowledge_base_id: Optional[int],
    current_user: User,
    db: Session,
) -> str:
    """Resolve connection + optional KB to a schema context string."""
    conn = db.query(DBConnection).filter(
        DBConnection.id == connection_id,
        DBConnection.user_id == current_user.id,
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    engine = get_user_engine(conn)
    inspector = inspect(engine)
    all_tables = inspector.get_table_names()
    context_tables = all_tables
    if knowledge_base_id:
        kb = db.query(KnowledgeBase).filter(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.connection_id == connection_id,
        ).first()
        if kb and kb.tables:
            filtered = [t for t in kb.tables if t in all_tables]
            if filtered:
                context_tables = filtered
    return get_schema_context(engine, context_tables)


def _parse_suggestions(raw_text: str, count: int) -> List[str]:
    """Extract numbered suggestions from LLM output."""
    lines = raw_text.strip().split("\n")
    suggestions = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Strip leading numbering like "1.", "1)", "- ", "* "
        import re
        cleaned = re.sub(r'^[\d]+[.)]\s*', '', line)
        cleaned = re.sub(r'^[-*]\s*', '', cleaned)
        cleaned = cleaned.strip().strip('"').strip("'")
        if cleaned:
            suggestions.append(cleaned)
    return suggestions[:count]


@router.post("/initial", response_model=SuggestionsResponse)
def get_initial_suggestions(
    req: InitialSuggestionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate initial prompt suggestions based on the knowledge base schema."""
    try:
        schema_context = _get_schema_for_request(
            req.connection_id, req.knowledge_base_id, current_user, db
        )
        prompt = f"""You are a helpful data analyst assistant. Given the following database schema, suggest exactly 4 natural language questions that a user might want to ask about this data. The questions should be practical, insightful, and varied in complexity (some simple, some analytical).

DATABASE SCHEMA:
{schema_context}

RULES:
1. Return exactly 4 questions, one per line
2. Number them 1. 2. 3. 4.
3. Make questions specific to the actual table and column names in the schema
4. Include a mix of: simple data retrieval, aggregation/counting, filtering, and analytical questions
5. Keep questions concise (under 80 characters each)
6. Do NOT include any SQL — only natural language questions

QUESTIONS:"""

        llm = get_llm()
        response = llm.invoke(prompt)
        suggestions = _parse_suggestions(response.content, 4)
        if not suggestions:
            suggestions = [
                "Show all tables in the database",
                "How many records are in each table?",
                "Show me the first 10 rows",
                "What columns are available?",
            ]

        return SuggestionsResponse(suggestions=suggestions)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating initial suggestions: {e}")
        return SuggestionsResponse(suggestions=[
            "Show all tables in the database",
            "How many records are in each table?",
            "Show me the first 10 rows",
            "What columns are available?",
        ])


@router.post("/conversation", response_model=SuggestionsResponse)
def get_conversation_suggestions(
    req: ConversationSuggestionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate follow-up suggestions based on schema + conversation history."""
    try:
        schema_context = _get_schema_for_request(
            req.connection_id, req.knowledge_base_id, current_user, db
        )

        # Build conversation history string (last 5 exchanges max)
        history_lines = []
        for entry in req.conversation_history[-5:]:
            role = entry.get("role", "user").capitalize()
            content = entry.get("content", "")
            if len(content) > 200:
                content = content[:200] + "..."
            history_lines.append(f"{role}: {content}")
        history_text = "\n".join(history_lines) if history_lines else "No previous conversation."

        prompt = f"""You are a helpful data analyst assistant. Given the database schema and the recent conversation history below, suggest exactly 3 relevant follow-up questions the user might want to ask next.

DATABASE SCHEMA:
{schema_context}

RECENT CONVERSATION:
{history_text}

RULES:
1. Return exactly 3 questions, one per line
2. Number them 1. 2. 3.
3. Questions should be natural follow-ups to the conversation — drill deeper, explore related data, or pivot to related tables
4. Make questions specific to the actual table and column names in the schema
5. Keep questions concise (under 80 characters each)
6. Do NOT repeat questions already asked in the conversation
7. Do NOT include any SQL — only natural language questions

FOLLOW-UP QUESTIONS:"""

        llm = get_llm()
        response = llm.invoke(prompt)
        suggestions = _parse_suggestions(response.content, 3)

        if not suggestions:
            suggestions = [
                "Show me more details about the results",
                "What are the top records by count?",
                "Are there any related tables to explore?",
            ]

        return SuggestionsResponse(suggestions=suggestions)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating conversation suggestions: {e}")
        return SuggestionsResponse(suggestions=[
            "Show me more details about the results",
            "What are the top records by count?",
            "Are there any related tables to explore?",
        ])
