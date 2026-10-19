from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from functools import lru_cache
from app.database import get_db
from app.models.user import User
from app.models.connection import DBConnection
from app.models.knowledge import KnowledgeBase
from app.models.conversation import Conversation, ConversationMessage
import json
import logging
from app.utils.security import get_current_user
from app.utils.db_manager import get_user_engine
from app.services.schema_index.service import build_schema_context
from app.services.redis_client import redis_client
from app.utils.prompts import initial_suggestions_prompt, conversation_suggestions_prompt
from app.config import get_settings
from app.services.llm_factory import create_chat_model

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/suggestions", tags=["Suggestions"])


class InitialSuggestionsRequest(BaseModel):
    connection_id: int
    knowledge_base_id: Optional[int] = None
    force_refresh: bool = False


class ConversationSuggestionsRequest(BaseModel):
    conversation_id: str  # its last turns are read from the database; the suggestions are saved with it


class SuggestionsResponse(BaseModel):
    suggestions: List[str]


class SuggestionList(BaseModel):
    """Structured output schema for LLM-generated prompt suggestions."""
    suggestions: List[str] = Field(
        description="A list of natural language questions a user might ask about the data.",
        min_length=1,
        max_length=4,
    )

_DEFAULT_SUGGESTIONS = [
    "Show all tables in the database",
    "How many records are in each table?",
    "Show me the first 10 rows",
    "What columns are available?",
]

@lru_cache(maxsize=1)
def _suggestions_llm():
    """The suggestions model (SUGGESTIONS_LLM_*, else the agent's), created once."""
    llm = create_chat_model(settings.SUGGESTIONS_LLM_PROVIDER or None,
                            settings.SUGGESTIONS_LLM_MODEL or None)
    return llm.with_structured_output(SuggestionList)


def _get_schema_for_request(
    connection_id: int,
    knowledge_base_id: int,
    current_user: User,
    db: Session,
) -> Optional[str]:
    """Schema context for the knowledge base's tables (the agent's, from the
    cached profile once there is one); None when the KB is not found or lists
    no tables (the caller then returns the defaults)."""
    conn = db.query(DBConnection).filter(
        DBConnection.id == connection_id,
        DBConnection.user_id == current_user.id,
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == knowledge_base_id,
        KnowledgeBase.connection_id == connection_id,
    ).first()
    if not kb or not kb.tables:
        return None
    return build_schema_context(db, conn, get_user_engine(conn), list(kb.tables))

@router.post("/initial", response_model=SuggestionsResponse)
def get_initial_suggestions(
    req: InitialSuggestionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate initial prompt suggestions based on the knowledge base schema."""
    if not req.knowledge_base_id:
        return SuggestionsResponse(suggestions=_DEFAULT_SUGGESTIONS)
    try:
        cache_key = f"initial_suggestions:user:{current_user.id}:connection:{req.connection_id}:kb:{req.knowledge_base_id}"

        if not req.force_refresh:
            cached_suggestions = redis_client.get(cache_key)
            if cached_suggestions:
                return SuggestionsResponse(suggestions=cached_suggestions)

        schema_context = _get_schema_for_request(
            req.connection_id, req.knowledge_base_id, current_user, db
        )
        if schema_context is None:
            return SuggestionsResponse(suggestions=_DEFAULT_SUGGESTIONS)
        prompt = initial_suggestions_prompt(schema_context)
        db.commit()     # release the app database connection during the LLM call
        result: SuggestionList = _suggestions_llm().invoke(prompt)
        suggestions = result.suggestions if result.suggestions else _DEFAULT_SUGGESTIONS
        
        redis_client.set(cache_key, suggestions, ex=7200)
        
        return SuggestionsResponse(suggestions=suggestions)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Error generating initial suggestions: %s", e)
        return SuggestionsResponse(suggestions=_DEFAULT_SUGGESTIONS)

def _save_suggestions(db: Session, user: User, req: ConversationSuggestionsRequest,
                      suggestions: List[str]) -> None:
    """Stores the conversation's latest suggestions, so a reloaded conversation
    shows them. Never raises: they were already generated."""
    try:
        db.query(Conversation).filter(
            Conversation.id == req.conversation_id,
            Conversation.user_id == user.id,
        ).update({Conversation.suggestions: suggestions}, synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("Error saving conversation suggestions: %s", e)


_HISTORY_TURNS = 3       # last turns sent to the suggestions model
_HISTORY_TEXT_CHARS = 300  # per question / reply
_HISTORY_SQL_CHARS = 600


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _recent_turns(db: Session, user: User, conversation_id: str) -> str:
    """The conversation's last turns as text: user question, SQL and AI reply.
    Empty when the conversation isn't the user's or has no messages."""
    messages = (
        db.query(ConversationMessage)
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .order_by(ConversationMessage.id.desc())
        .limit(_HISTORY_TURNS * 2)
        .all()
    )
    lines = []
    for m in reversed(messages):
        if m.role == "user":
            lines.append(f"User: {_clip(m.content, _HISTORY_TEXT_CHARS)}")
            continue
        try:
            sql = json.loads(m.metadata_json or "{}").get("generated_sql") or ""
        except ValueError:
            sql = ""
        if sql:
            lines.append(f"SQL: {_clip(sql, _HISTORY_SQL_CHARS)}")
        lines.append(f"AI: {_clip(m.content, _HISTORY_TEXT_CHARS)}")
    return "\n".join(lines)


@router.post("/conversation", response_model=SuggestionsResponse)
def get_conversation_suggestions(
    req: ConversationSuggestionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate follow-up suggestions from the conversation's last turns only
    (question, SQL, reply); no schema."""
    try:
        history_text = _recent_turns(db, current_user, req.conversation_id)
        if not history_text:
            return SuggestionsResponse(suggestions=_DEFAULT_SUGGESTIONS)
        prompt = conversation_suggestions_prompt(history_text)
        db.commit()     # release the app database connection during the LLM call
        result: SuggestionList = _suggestions_llm().invoke(prompt)
        suggestions = result.suggestions if result.suggestions else _DEFAULT_SUGGESTIONS
        if result.suggestions:
            _save_suggestions(db, current_user, req, suggestions)
        return SuggestionsResponse(suggestions=suggestions)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Error generating conversation suggestions: %s", e)
        return SuggestionsResponse(suggestions=_DEFAULT_SUGGESTIONS)
