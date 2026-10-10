import logging
import threading
from typing import TypedDict, Annotated
from uuid import uuid4

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import tools_condition, ToolNode
from langgraph.graph.message import AnyMessage, add_messages
from langgraph.errors import GraphRecursionError
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from fastapi import HTTPException

from app.services.validate_sql import SafeSqlExecutor
from app.config import get_settings
from app.services.llm_factory import create_chat_model

load_dotenv()
logger = logging.getLogger(__name__)
settings = get_settings()

# ──────────────────────────────────────────────────────────────────────────────
# Agent configuration
# ──────────────────────────────────────────────────────────────────────────────
_RECURSION_LIMIT = 25          # graph *steps*, not tool calls (~8 round-trips)
_MAX_HISTORY_MESSAGES = 20     # cap on messages sent to the LLM per step

# AGENT_MODE values. In evaluation mode the graph ends as soon as the SQL tool
# succeeds, so the final answer-generation LLM call is never made.
AGENT_MODE_PRODUCTION = "production"
AGENT_MODE_EVALUATION = "evaluation"


# ──────────────────────────────────────────────────────────────────────────────
# Lazy-initialized Postgres checkpointer with connection pool
#
# Deferred initialization avoids requiring a live DB at import time (helps
# tests and makes startup failures more obvious).  A ConnectionPool is used
# instead of a single connection so concurrent requests don't bottleneck and
# the pool automatically recovers from dropped connections.
# ──────────────────────────────────────────────────────────────────────────────
_checkpointer_lock = threading.Lock()
_checkpointer: PostgresSaver | None = None
_pg_pool: ConnectionPool | None = None


def _get_checkpointer() -> PostgresSaver:
    """Return (and lazily create) the shared PostgresSaver instance."""
    global _checkpointer, _pg_pool
    if _checkpointer is not None:
        return _checkpointer

    with _checkpointer_lock:
        if _checkpointer is not None:          # double-check after lock
            return _checkpointer

        db_url = settings.DATABASE_URL
        if not db_url:
            raise RuntimeError(
                "DATABASE_URL must be set in settings to use the Postgres checkpointer."
            )

        _pg_pool = ConnectionPool(
            conninfo=db_url,
            min_size=2,
            max_size=5,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )
        saver = PostgresSaver(_pg_pool)
        saver.setup()                          # creates checkpoint tables if absent
        _checkpointer = saver
        logger.info("Postgres checkpointer initialized")
        return _checkpointer


# ──────────────────────────────────────────────────────────────────────────────
# SQL tool — rows travel as ToolMessage.artifact (no shared mutable state)
# ──────────────────────────────────────────────────────────────────────────────
def create_sql_tool(engine):
    @tool(response_format="content_and_artifact")
    def execute_sql_query(sql_query: str):
        """
        Execute one read-only PostgreSQL SELECT query and return its result
        (at most 50 rows are shown).

        Args:
            sql_query: A single PostgreSQL SELECT statement.
        """
        executor = SafeSqlExecutor(engine, max_rows=50)
        result = executor.run(sql_query)

        if not result.success:
            return f"Error: {result.error}", {"success": False}

        artifact = {
            "success": True,
            "sql":     result.sql,
            "columns": result.columns,
            "rows":    result.rows,
        }
        return result.to_llm_string(), artifact

    return execute_sql_query


# ──────────────────────────────────────────────────────────────────────────────
# Content normalization
# ──────────────────────────────────────────────────────────────────────────────
def _normalize_content(content) -> str:
    """Normalize LLM response content to a plain string.

    Gemini can return content as a list of parts rather than a plain string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content) if content else ""


def _tool_succeeded(msg) -> bool:
    """True for a ToolMessage whose SQL ran (explicit flag, not row count)."""
    artifact = getattr(msg, "artifact", None)
    return (
        isinstance(msg, ToolMessage)
        and isinstance(artifact, dict)
        and bool(artifact.get("success"))
    )


def _is_rate_limit(exc: Exception) -> bool:
    """Provider rate-limit errors, which arrive as different exception types
    (Gemini RESOURCE_EXHAUSTED, Groq RateLimitError, ...)."""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(s in text for s in ("429", "resourceexhausted", "resource_exhausted", "ratelimit"))


def _failure(question: str, error: str, response_text: str) -> dict:
    return {
        "success": False,
        "question": question,
        "generated_sql": "",
        "columns": [],
        "rows": [],
        "error": error,
        "response_text": response_text,
    }


class SQLAgent:
    class UserState(TypedDict):
        messages: Annotated[list[AnyMessage], add_messages]
        last_user_input: str | None

    def __init__(
        self,
        engine,
        schema_context: str,
        *,
        mode: str | None = None,
        llm: BaseChatModel | None = None,
    ):
        self.engine = engine
        self.mode = (mode or settings.AGENT_MODE or AGENT_MODE_PRODUCTION).strip().lower()
        if self.mode not in (AGENT_MODE_PRODUCTION, AGENT_MODE_EVALUATION):
            raise ValueError(f"Unknown AGENT_MODE '{self.mode}'")

        # Use a SystemMessage instead of ChatPromptTemplate so that { }
        # in column types / names (e.g. jsonb, hstore) are never interpreted
        # as template variables.
        self.system_message = SystemMessage(
            content=self._build_system_text(schema_context)
        )
        self.execute_sql_query = create_sql_tool(engine)

        # Provider/model come from LLM_PROVIDER unless a model is injected.
        self.llm_with_tools = (llm or create_chat_model()).bind_tools(
            [self.execute_sql_query]
        )

        self.workflow = self._build_workflow()

    @staticmethod
    def _build_system_text(schema_context: str) -> str:
        return (
            "You are a data analyst assistant for a PostgreSQL database. Answer the "
            "user's question by running one read-only SELECT query with the "
            "`execute_sql_query` tool, then answer from its result.\n\n"
            "QUERY RULES:\n"
            "1. Return exactly what the question asks for. SELECT only the columns "
            "needed to answer it, in the order the question mentions them. Do not "
            "add helper columns (ids, counts, totals, intermediate values used in a "
            "calculation) unless the question asks for them.\n"
            "2. For a calculation (ratio, percentage, average, difference), return "
            "only the final value as one column. Do not round unless asked. Cast to "
            "NUMERIC before dividing to avoid integer division, and wrap divisors in "
            "NULLIF(..., 0).\n"
            "3. Use LIMIT only when the question asks for a specific number of "
            "results (e.g. 'top 5', 'the highest', 'which one'). Otherwise return all "
            "matching rows; the tool already caps how many are displayed.\n"
            "4. Use DISTINCT when the question asks for unique values or when joins "
            "could repeat the requested rows.\n"
            "5. Use only tables and columns from the schema below. Double-quote "
            "identifiers that contain uppercase letters or special characters.\n"
            "6. If the question asks to list or show individual records (e.g. "
            "products, people) and their table has an image column (image_url, "
            "image, thumbnail, photo, avatar, ...), also select it so the UI can "
            "display it. Never add image columns to counts, aggregates or "
            "single-value answers.\n"
            "7. Follow any definitions, formulas or hints the user gives.\n"
            "8. If the tool returns an error, fix the query and call it again.\n\n"
            "ANSWER: once the query succeeds, reply with a clear, concise answer "
            "based only on the result. If the result is empty, say so.\n\n"
            "DATABASE SCHEMA:\n" + schema_context
        )

    def _generate_response(self, state: "SQLAgent.UserState") -> dict:
        conversation = state["messages"]
        # Keep conversation history bounded to avoid replaying very long
        # histories (including large ToolMessage payloads) back to the LLM.
        if len(conversation) > _MAX_HISTORY_MESSAGES:
            conversation = conversation[-_MAX_HISTORY_MESSAGES:]
            # Ensure we start on a HumanMessage for coherent context
            while conversation and not isinstance(conversation[0], HumanMessage):
                conversation = conversation[1:]

        messages = [self.system_message] + conversation
        response = self.llm_with_tools.invoke(messages)
        # Return only the delta; the add_messages reducer appends it
        return {"messages": response}

    @property
    def is_evaluation(self) -> bool:
        return self.mode == AGENT_MODE_EVALUATION

    @staticmethod
    def _route_after_tools(state: "SQLAgent.UserState") -> str:
        """Evaluation mode: stop once the SQL tool has succeeded.

        Failed tool calls still go back to the LLM so its self-correction
        (retrying after a schema/syntax error) is part of what gets evaluated.
        """
        for msg in reversed(state["messages"]):
            if not isinstance(msg, ToolMessage):
                break
            if _tool_succeeded(msg):
                return END
        return "generate_response"

    def _build_workflow(self):
        graph = StateGraph(SQLAgent.UserState)
        graph.add_node("generate_response", self._generate_response)
        graph.add_node(
            "tools",
            ToolNode([self.execute_sql_query], handle_tool_errors=True),
        )
        graph.set_entry_point("generate_response")
        graph.add_conditional_edges("generate_response", tools_condition)
        if self.is_evaluation:
            # Single-turn runs: skip the Postgres checkpointer entirely.
            graph.add_conditional_edges(
                "tools", self._route_after_tools, ["generate_response", END]
            )
            return graph.compile()
        graph.add_edge("tools", "generate_response")
        return graph.compile(checkpointer=_get_checkpointer())

    # ── Public API ───────────────────────────────────────────────────────────

    def run_query(
        self,
        user_input: str,
        *,
        user_id: int,
        conn_id: int,
        conversation_id: str | None = None,
    ) -> dict:
        """
        Invoke the agent for one user turn.

        Thread ID is namespaced as ``"{user_id}:{conn_id}:{conversation_id}"``.
        Without a conversation_id a unique thread is created so callers never
        accidentally share state.
        """
        conv_segment = conversation_id or uuid4().hex
        thread_id = f"{user_id}:{conn_id}:{conv_segment}"

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": _RECURSION_LIMIT,
        }

        initial_state: dict = {
            "messages": [HumanMessage(content=user_input)],
            "last_user_input": user_input,
        }

        try:
            state = self.workflow.invoke(initial_state, config)
        except GraphRecursionError:
            logger.warning(
                "Agent hit recursion limit (%d steps) for thread %s",
                _RECURSION_LIMIT,
                thread_id,
            )
            return _failure(
                user_input,
                "The query required too many steps. Please simplify your question.",
                "I wasn't able to answer within the allowed number of steps. "
                "Please try rephrasing or simplifying your question.",
            )
        except Exception as e:
            if _is_rate_limit(e):
                raise HTTPException(
                    status_code=429,
                    detail="LLM API rate limit exceeded. Please try again later.",
                )
            logger.exception("Error executing SQL agent workflow")
            message = "An internal error occurred while processing your query."
            return _failure(user_input, message, message)

        # With a checkpointer, state["messages"] holds the whole thread. Only
        # look at messages after the last HumanMessage (the current turn) so
        # SQL/rows from a previous turn are never returned.
        messages = state["messages"]
        turn_start = max(
            (i for i, msg in enumerate(messages) if isinstance(msg, HumanMessage)),
            default=0,
        )
        turn = messages[turn_start:]
        last_sql_artifact = next(
            (msg.artifact for msg in reversed(turn) if _tool_succeeded(msg)), {}
        )

        result = {
            "success": True,
            "question": user_input,
            "generated_sql": last_sql_artifact.get("sql", ""),
            "columns":       last_sql_artifact.get("columns", []),
            "rows":          last_sql_artifact.get("rows", []),
            "response_text": (
                "" if self.is_evaluation else _normalize_content(messages[-1].content)
            ),
        }
        if self.is_evaluation:
            result["trace"] = self._collect_trace(turn)
        return result

    @staticmethod
    def _collect_trace(messages: list) -> dict:
        """Per-turn diagnostics for offline evaluation: every SQL the agent
        tried, the tool errors it saw, and LLM token usage."""
        attempted_sql: list[str] = []
        tool_errors: list[str] = []
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        llm_calls = 0
        for msg in messages:
            if isinstance(msg, AIMessage):
                llm_calls += 1
                for call in msg.tool_calls or []:
                    attempted_sql.append(str(call.get("args", {}).get("sql_query", "")))
                for key, value in (msg.usage_metadata or {}).items():
                    if key in usage and isinstance(value, int):
                        usage[key] += value
            elif isinstance(msg, ToolMessage) and not _tool_succeeded(msg):
                tool_errors.append(_normalize_content(msg.content))
        return {
            "attempted_sql": attempted_sql,
            "tool_errors":   tool_errors,
            "llm_calls":     llm_calls,
            "usage":         usage,
            "final_text":    _normalize_content(messages[-1].content) if messages else "",
        }