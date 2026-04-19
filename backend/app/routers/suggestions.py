from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from app.database import get_db
from app.models.user import User
from app.models.connection import DBConnection
from app.models.knowledge import KnowledgeBase
from app.utils.security import get_current_user
from app.utils.db_manager import get_user_engine
from app.services.validate_sql import get_schema_context, get_all_table_names
from app.services.redis_client import redis_client
from app.utils.prompts import initial_suggestions_prompt, conversation_suggestions_prompt
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/suggestions", tags=["Suggestions"])


class InitialSuggestionsRequest(BaseModel):
    connection_id: int
    knowledge_base_id: Optional[int] = None
    force_refresh: bool = False


class ConversationSuggestionsRequest(BaseModel):
    connection_id: int
    knowledge_base_id: Optional[int] = None
    conversation_history: List[dict] = []  # [{role: "user"|"assistant", content: "..."}]


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
    all_tables = get_all_table_names(engine)
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

@router.post("/initial", response_model=SuggestionsResponse)
def get_initial_suggestions(
    req: InitialSuggestionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate initial prompt suggestions based on the knowledge base schema."""
    try:
        cache_key = f"initial_suggestions:user:{current_user.id}:connection:{req.connection_id}:kb:{req.knowledge_base_id or 'all'}"
        
        if not req.force_refresh:
            cached_suggestions = redis_client.get(cache_key)
            if cached_suggestions:
                return SuggestionsResponse(suggestions=cached_suggestions)

        schema_context = _get_schema_for_request(
            req.connection_id, req.knowledge_base_id, current_user, db
        )
        prompt = initial_suggestions_prompt(schema_context)
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0,
        )
        structured_llm = llm.with_structured_output(SuggestionList)
        result: SuggestionList = structured_llm.invoke(prompt)
        suggestions = result.suggestions[:4] if result.suggestions else _DEFAULT_SUGGESTIONS
        
        redis_client.set(cache_key, suggestions, ex=3600)
        
        return SuggestionsResponse(suggestions=suggestions)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating initial suggestions: {e}")
        return SuggestionsResponse(suggestions=_DEFAULT_SUGGESTIONS)

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
        prompt = conversation_suggestions_prompt(schema_context, history_text)
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0,
        )
        structured_llm = llm.with_structured_output(SuggestionList)
        result: SuggestionList = structured_llm.invoke(prompt)
        suggestions = result.suggestions[:3] if result.suggestions else _DEFAULT_SUGGESTIONS
        return SuggestionsResponse(suggestions=suggestions)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating conversation suggestions: {e}")
        return SuggestionsResponse(suggestions=_DEFAULT_SUGGESTIONS)
