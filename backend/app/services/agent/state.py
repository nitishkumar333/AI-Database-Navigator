"""Graph state (checkpointed per conversation) and the per-run context
(connection-specific objects, passed with `graph.invoke(..., context=...)`
and never written to a checkpoint)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.message import AnyMessage, add_messages
from sqlalchemy.engine import Engine

from app.services.schema_index.retriever import SchemaView


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    last_user_input: str | None
    # Per-turn counters; the caller resets them with every new question.
    tool_calls_used: int
    sql_runs_used: int
    forced_submits: int        # LLM calls made with only submit_answer allowed
    answer: dict | None        # artifact of the successful submit_answer


@dataclass(frozen=True)
class Budget:
    max_tool_calls: int = 8    # all tools, per turn
    max_sql_runs: int = 6      # run_sql + submit_answer, per turn
    max_forced_submits: int = 2


@dataclass
class AgentContext:
    engine: Engine
    schema_context: str        # schema text in the system prompt (full schema or table catalog)
    schema: SchemaView         # what the schema tools look at
    llm: BaseChatModel
    budget: Budget = field(default_factory=Budget)
    explore_rows: int = 20     # rows run_sql shows the model
    answer_rows: int = 200     # rows submit_answer returns to the caller
    answer_rows_shown: int = 50  # ... of which the model sees this many
    sql_timeout_ms: int = 10_000
    catalog_prompt: bool = False  # schema_context is the table catalog; columns via describe_tables
    turn_id: str = "-"         # tags this turn's log lines (set per turn by SQLAgent)
