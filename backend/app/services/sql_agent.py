import logging
import threading
from typing import TypedDict, Annotated
from uuid import uuid4

from dotenv import load_dotenv
from langgraph.graph import StateGraph
from langgraph.prebuilt import tools_condition, ToolNode
from langgraph.graph.message import AnyMessage, add_messages
from langgraph.errors import GraphRecursionError
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from google.api_core.exceptions import ResourceExhausted
from fastapi import HTTPException

from app.services.validate_sql import SafeSqlExecutor
from app.config import get_settings

load_dotenv()
logger = logging.getLogger(__name__)
settings = get_settings()

# ──────────────────────────────────────────────────────────────────────────────
# Agent configuration
# ──────────────────────────────────────────────────────────────────────────────
_RECURSION_LIMIT = 25          # graph *steps*, not tool calls (~8 round-trips)
_MAX_HISTORY_MESSAGES = 20     # cap on messages sent to the LLM per step


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
        Executes a SQL query safely against the database.
        RULES:
        1. sql_query must be a valid PostgreSQL SELECT query
        2. Use proper table and column names from the schema
        3. Add appropriate LIMIT clause if the query could return many rows
        4. Prioritize and include image URL columns (e.g., image_url, image, thumbnail) whenever present in the queried tables

        Args:
            sql_query: Single SQL query string to execute

        Returns:
            (content_str, artifact_dict) where artifact carries the raw result rows.
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


# ──────────────────────────────────────────────────────────────────────────────
# SQLAgent
# ──────────────────────────────────────────────────────────────────────────────
class SQLAgent:
    class UserState(TypedDict):
        messages: Annotated[list[AnyMessage], add_messages]
        last_user_input: str | None

    def __init__(self, engine, schema_context: str):
        self.engine = engine
        # Use a SystemMessage instead of ChatPromptTemplate so that { }
        # in column types / names (e.g. jsonb, hstore) are never interpreted
        # as template variables.
        self.system_message = SystemMessage(
            content=self._build_system_text(schema_context)
        )
        self.execute_sql_query = create_sql_tool(engine)

        # Build the LLM + tool binding once, not on every graph step
        self.llm_with_tools = ChatGoogleGenerativeAI(
            model=getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite"),
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0,
        ).bind_tools([self.execute_sql_query])

        self.workflow = self._build_workflow()

    # ── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _build_system_text(schema_context: str) -> str:
        return (
            "You are an AI agent with capability to generate SQL queries. "
            "You can use tool `execute_sql_query` to generate a PostgreSQL "
            "SELECT query and answer the user's question based on the query result.\n\n"
            "CRITICAL QUERY INSTRUCTIONS:\n"
            "1. Always prioritize and include columns containing image URLs "
            "(such as `image_url`, `image`, `img`, `thumbnail`, `photo`, "
            "`picture`, `avatar`, etc.) in the SELECT list whenever the queried "
            "tables or joined tables contain them, so that the final SQL query "
            "result includes image links.\n"
            "2. When using GROUP BY or aggregations on tables with image columns, "
            "ensure the image column is preserved in the output (e.g., include it "
            "in the GROUP BY or use MAX/MIN or an appropriate aggregate).\n"
            "3. Generate only valid PostgreSQL SELECT queries. Do not generate "
            "DDL/DML statements (INSERT, UPDATE, DELETE, DROP, etc.).\n"
            "4. Use clear column aliases where helpful and add an appropriate "
            "LIMIT clause if many rows could be returned.\n"
            "5. In your final natural language response, provide a clear, "
            "concise summary of the findings.\n\n"
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

    def _build_workflow(self):
        graph = StateGraph(SQLAgent.UserState)
        graph.add_node("generate_response", self._generate_response)
        graph.add_node(
            "tools",
            ToolNode([self.execute_sql_query], handle_tool_errors=True),
        )
        graph.set_entry_point("generate_response")
        graph.add_conditional_edges("generate_response", tools_condition)
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
        except ResourceExhausted:
            raise HTTPException(
                status_code=429,
                detail="LLM API rate limit exceeded. Please try again later.",
            )
        except GraphRecursionError:
            logger.warning(
                "Agent hit recursion limit (%d steps) for thread %s",
                _RECURSION_LIMIT,
                thread_id,
            )
            return {
                "success": False,
                "question": user_input,
                "generated_sql": "",
                "columns": [],
                "rows": [],
                "error": "The query required too many steps. Please simplify your question.",
                "response_text": (
                    "I wasn't able to answer within the allowed number of steps. "
                    "Please try rephrasing or simplifying your question."
                ),
            }
        except Exception as e:
            logger.exception("Error executing SQL agent workflow")
            # Catch rate-limit errors that arrive wrapped in a generic exception
            is_rate_limit = (
                "429" in str(e)
                or "ResourceExhausted" in type(e).__name__
            )
            if is_rate_limit:
                raise HTTPException(
                    status_code=429,
                    detail="LLM API rate limit exceeded. Please try again later.",
                )
            return {
                "success": False,
                "question": user_input,
                "generated_sql": "",
                "columns": [],
                "rows": [],
                "error": "An internal error occurred while processing your query.",
                "response_text": "An internal error occurred while processing your query.",
            }

        # ── Collect artifacts from the current turn only ─────────────────────
        # With a checkpointer, state["messages"] contains the full thread
        # history.  Only scan messages after the last HumanMessage to avoid
        # returning SQL/rows from a previous turn.
        last_human_idx = 0
        for i, msg in enumerate(state["messages"]):
            if isinstance(msg, HumanMessage):
                last_human_idx = i

        last_sql_artifact: dict = {}
        for msg in state["messages"][last_human_idx:]:
            if (
                isinstance(msg, ToolMessage)
                and isinstance(getattr(msg, "artifact", None), dict)
                and msg.artifact.get("success")   # explicit flag, not row count
            ):
                last_sql_artifact = msg.artifact

        return {
            "success": True,
            "question": user_input,
            "generated_sql": last_sql_artifact.get("sql", ""),
            "columns":       last_sql_artifact.get("columns", []),
            "rows":          last_sql_artifact.get("rows", []),
            "response_text": _normalize_content(state["messages"][-1].content),
        }