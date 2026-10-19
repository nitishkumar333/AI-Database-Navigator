"""
SQLAgent: the entry point used by the query router and the evaluation suite.

A thin wrapper around the agent graph in services/agent: it bundles the
connection-specific context, runs one turn, and turns the final state into a
result dict. The graph itself is compiled once per process.
"""
import dataclasses
import logging
import threading
import time
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import HTTPException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from app.config import get_settings
from app.services.agent import trace_log
from app.services.agent.graph import RECURSION_LIMIT, get_graph, is_rate_limit, turn_start
from app.services.agent.state import AgentContext, Budget, HistoryLimits
from app.services.agent.tools import DESCRIBE_TABLES, RUN_SQL, SUBMIT_ANSWER
from app.services.display import describe_result
from app.services.llm_factory import create_chat_model
from app.services.schema_index.retriever import SchemaView

load_dotenv()
logger = logging.getLogger(__name__)
settings = get_settings()

# AGENT_MODE values. In evaluation mode the graph ends as soon as an answer is
# submitted, so the final answer-writing LLM call is never made.
AGENT_MODE_PRODUCTION = "production"
AGENT_MODE_EVALUATION = "evaluation"

_NO_ANSWER_TEXT = (
    "I couldn't settle on a final query within the allowed number of steps. "
    "The table shows the closest query I ran; please check it, or rephrase "
    "the question."
)

_default_llm: BaseChatModel | None = None
_default_llm_lock = threading.Lock()


def _get_default_llm() -> BaseChatModel:
    """The configured chat model, created once per process."""
    global _default_llm
    with _default_llm_lock:
        if _default_llm is None:
            _default_llm = create_chat_model()
        return _default_llm


_reply_llm: BaseChatModel | None = None


def _get_reply_llm() -> BaseChatModel | None:
    """The model that writes the reply when settings name one (REPLY_LLM_*),
    created once per process; None = the agent's own model."""
    global _reply_llm
    if not (settings.REPLY_LLM_PROVIDER or settings.REPLY_LLM_MODEL):
        return None
    with _default_llm_lock:
        if _reply_llm is None:
            _reply_llm = create_chat_model(settings.REPLY_LLM_PROVIDER or None,
                                           settings.REPLY_LLM_MODEL or None)
        return _reply_llm


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


def _artifact(msg) -> dict:
    artifact = getattr(msg, "artifact", None) if isinstance(msg, ToolMessage) else None
    return artifact if isinstance(artifact, dict) else {}


def thread_id_for(user_id: int, conn_id: int, conversation_id: str) -> str:
    """The checkpoint thread of one conversation on one connection."""
    return f"{user_id}:{conn_id}:{conversation_id}"


# ── Failed turns ─────────────────────────────────────────────────────────────
# A turn the agent ran but couldn't finish (LLM rate limit, error) leaves a
# note in the conversation's checkpoint thread after its question, so the model
# knows the question went unanswered and why, and a follow-up such as "try
# again" can answer it. Requests refused by the API's own rate limits never
# reach the agent and leave nothing.

FAILED_LLM_RATE_LIMIT = "the AI service's rate limit was reached"
FAILED_TOO_MANY_STEPS = "answering it needed more steps than allowed"
FAILED_ERROR = "an internal error occurred"

_FAILED_TURN_NOTE = (
    "(Not answered: {reason}. The question above is still open; if the user asks to try "
    "again, answer it now.)"
)


def record_failed_turn(thread_id: str, question: HumanMessage, reason: str) -> None:
    """Appends the failure note to the thread, and the question too when the
    failed turn never stored it (it failed before the first checkpoint).
    Never raises: losing the note must not hide the original error."""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        graph = get_graph(evaluation=False)
        stored = graph.get_state(config).values.get("messages") or []
        messages = [] if any(m.id == question.id for m in stored) else [question]
        messages.append(AIMessage(content=_FAILED_TURN_NOTE.format(reason=reason),
                                  response_metadata={"turn_failed": True}))
        # As if the agent node had replied: the thread ends cleanly (no pending step).
        graph.update_state(config, {"messages": messages}, as_node="agent")
    except Exception:
        logger.exception("Could not note the failed turn in thread %s", thread_id)


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
    def __init__(
        self,
        engine,
        schema_context: str | None,
        *,
        mode: str | None = None,
        llm: BaseChatModel | None = None,
        schema_view: SchemaView | None = None,
        budget: Budget | None = None,
    ):
        """`schema_context` is the full schema text (None if it couldn't be
        built). `schema_view` is what the schema tools search and describe;
        without it they see every table of the database."""
        self.mode = (mode or settings.AGENT_MODE or AGENT_MODE_PRODUCTION).strip().lower()
        if self.mode not in (AGENT_MODE_PRODUCTION, AGENT_MODE_EVALUATION):
            raise ValueError(f"Unknown AGENT_MODE '{self.mode}'")
        if schema_view is None:
            from sqlalchemy import inspect
            schema_view = SchemaView(inspect(engine).get_table_names(), engine=engine)

        # The full schema goes in the prompt when it is small enough; otherwise
        # the prompt lists tables only and the agent reads columns with
        # describe_tables. "full" | "catalog": what this agent's prompt holds.
        use_full = (schema_context is not None
                    and len(schema_context) <= settings.AGENT_FULL_SCHEMA_MAX_CHARS)
        self.schema_prompt = "full" if use_full else "catalog"

        self.context = AgentContext(
            engine=engine,
            schema_context=schema_context if use_full else schema_view.catalog(),
            catalog_prompt=not use_full,
            link_max_tables=settings.SCHEMA_LINK_MAX_TABLES,
            link_max_chars=settings.SCHEMA_LINK_MAX_CHARS,
            schema=schema_view,
            llm=llm or _get_default_llm(),
            reply_llm=None if self.is_evaluation else _get_reply_llm(),  # evaluation writes no reply
            budget=budget or Budget(),
            history=HistoryLimits(full_turns=settings.AGENT_HISTORY_FULL_TURNS,
                                  max_chars=settings.AGENT_HISTORY_MAX_CHARS),
        )

    @property
    def is_evaluation(self) -> bool:
        return self.mode == AGENT_MODE_EVALUATION

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
        thread_id = thread_id_for(user_id, conn_id, conversation_id or uuid4().hex)
        # Failed turns are noted in the thread, so a later "try again" has the question.
        # Only conversations are continued; evaluation keeps no checkpoint.
        note_failure = conversation_id is not None and not self.is_evaluation
        question = HumanMessage(content=user_input, id=uuid4().hex)
        # A copy per turn: one SQLAgent can serve concurrent turns (evaluation workers).
        context = dataclasses.replace(self.context, turn_id=uuid4().hex[:6])
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": RECURSION_LIMIT,
            # LangSmith: name of the turn's root run; tags and metadata are
            # inherited by every run under it (nodes, LLM calls).
            "run_name": "SQLAgent",
            "tags": [self.mode],
            "metadata": {
                "user_id": user_id,
                "conn_id": conn_id,
                "conversation_id": conversation_id,
                "schema_prompt": self.schema_prompt,
                "turn_id": context.turn_id,     # matches the terminal log's [turn_id]
            },
        }
        initial_state: dict = {
            "messages": [question],
            "last_user_input": user_input,
            # Budgets and the answer are per turn.
            "tool_calls_used": 0,
            "sql_runs_used": 0,
            "forced_submits": 0,
            "answer": None,
            "linked_schema": None,
            "linked_tables": [],
            "link_method": None,
        }

        trace_log.turn_started(context.turn_id, self.mode, thread_id, user_input, context.llm,
                               f"{self.schema_prompt} ({len(context.schema_context):,} chars)")
        started = time.perf_counter()
        try:
            # durability="exit": the thread is saved once, when the turn ends,
            # not after every step (each save rewrites the whole message list).
            # Evaluation has no checkpointer, so nothing to save.
            durability = {} if self.is_evaluation else {"durability": "exit"}
            state = get_graph(self.is_evaluation).invoke(initial_state, config, context=context,
                                                         **durability)
        except GraphRecursionError:
            logger.warning("Agent hit recursion limit (%d steps) for thread %s",
                           RECURSION_LIMIT, thread_id)
            trace_log.turn_failed(context.turn_id, "recursion limit", time.perf_counter() - started)
            if note_failure:
                record_failed_turn(thread_id, question, FAILED_TOO_MANY_STEPS)
            return _failure(
                user_input,
                "The query required too many steps. Please simplify your question.",
                "I wasn't able to answer within the allowed number of steps. "
                "Please try rephrasing or simplifying your question.",
            )
        except Exception as e:
            trace_log.turn_failed(context.turn_id, f"{type(e).__name__}: {e}",
                                  time.perf_counter() - started)
            if note_failure:
                record_failed_turn(thread_id, question,
                                   FAILED_LLM_RATE_LIMIT if is_rate_limit(e) else FAILED_ERROR)
            if is_rate_limit(e):
                raise HTTPException(
                    status_code=429,
                    detail="LLM API rate limit exceeded. Please try again later.",
                )
            logger.exception("Error executing SQL agent workflow")
            message = "An internal error occurred while processing your query."
            return _failure(user_input, message, message)

        # With a checkpointer, state["messages"] holds the whole thread. Only
        # look at the current turn so a previous turn's SQL is never returned.
        messages = state["messages"]
        turn = messages[turn_start(messages):]

        answer, source = state.get("answer"), "submit"
        if answer is None:
            # No submitted answer (budget used up): best query so far.
            answer = next((_artifact(m) for m in reversed(turn)
                           if _artifact(m).get("kind") == RUN_SQL and _artifact(m).get("success")),
                          None)
            source = "exploration" if answer else None
        answer = answer or {}

        last = turn[-1] if turn else None
        final_text = (_normalize_content(last.content)
                      if isinstance(last, AIMessage) and not last.tool_calls else "")
        if self.is_evaluation:
            response_text = ""
        elif source == "submit":
            response_text = final_text or "Here is the result."
        elif source == "exploration":
            response_text = _NO_ANSWER_TEXT
        else:
            response_text = final_text or "I wasn't able to answer that. Please try rephrasing."

        if answer.get("rows") and "views" not in answer:   # an exploration query: no hint
            count = answer.get("row_count")
            truncated = count is None or count > len(answer["rows"])
            answer = {**answer, "truncated": truncated,
                      **describe_result(answer.get("columns") or [], answer["rows"],
                                        truncated=truncated)}
        result = {
            "success": True,
            "question": user_input,
            "generated_sql": answer.get("sql", ""),
            "columns": answer.get("columns", []),
            "rows": answer.get("rows", []),
            "row_count": answer.get("row_count"),
            "truncated": bool(answer.get("truncated")),
            "column_meta": answer.get("column_meta", []),
            "views": answer.get("views", []),
            "assumptions": answer.get("assumptions", ""),
            "answer_source": source,
            "response_text": response_text,
        }
        trace_log.turn_finished(context.turn_id, source, result["generated_sql"],
                                answer.get("row_count") or len(result["rows"]), state,
                                time.perf_counter() - started)
        if self.is_evaluation:
            result["trace"] = self._collect_trace(turn, state, source)
            result["trace"]["schema_prompt"] = self.schema_prompt
            if self.schema_prompt == "catalog":
                linked = list(state.get("linked_tables") or [])
                result["trace"]["linked_tables"] = linked
                result["trace"]["link_method"] = state.get("link_method")
                # Tables whose columns the agent saw (linked into the prompt or
                # described): the schema-linking metric's context.
                result["trace"]["context_tables"] = sorted(set(linked) | {
                    t for m in turn if _artifact(m).get("kind") == DESCRIBE_TABLES
                    for t in _artifact(m).get("tables") or []})
        return result

    @staticmethod
    def _collect_trace(messages: list, state: dict, answer_source: str | None) -> dict:
        """Per-turn diagnostics for offline evaluation: every SQL the agent
        submitted or explored with, the tool errors it saw, tool calls by
        name, budget use and LLM token usage."""
        attempted_sql: list[str] = []       # submit_answer calls
        exploration_sql: list[str] = []     # run_sql calls
        tool_errors: list[str] = []
        tool_calls: dict[str, int] = {}
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        llm_calls = 0
        for msg in messages:
            if isinstance(msg, AIMessage):
                llm_calls += 1 + (msg.response_metadata or {}).get("discarded_llm_calls", 0)
                for call in msg.tool_calls or []:
                    name = call.get("name", "")
                    tool_calls[name] = tool_calls.get(name, 0) + 1
                    sql = str((call.get("args") or {}).get("sql", ""))
                    if name == SUBMIT_ANSWER:
                        attempted_sql.append(sql)
                    elif name == RUN_SQL:
                        exploration_sql.append(sql)
                for key, value in (msg.usage_metadata or {}).items():
                    if key in usage and isinstance(value, int):
                        usage[key] += value
            elif isinstance(msg, ToolMessage):
                artifact = _artifact(msg)
                if not artifact.get("success") and not artifact.get("skipped"):
                    tool_errors.append(f"{msg.name}: {_normalize_content(msg.content)}")
        last = messages[-1] if messages else None
        return {
            "attempted_sql": attempted_sql,
            "exploration_sql": exploration_sql,
            "tool_errors": tool_errors,
            "tool_calls": tool_calls,
            "llm_calls": llm_calls,
            "usage": usage,
            "answer_source": answer_source,
            "budget": {
                "tool_calls": state.get("tool_calls_used", 0),
                "sql_runs": state.get("sql_runs_used", 0),
                "forced_submits": state.get("forced_submits", 0),
            },
            "final_text": (_normalize_content(last.content)
                           if isinstance(last, AIMessage) else ""),
        }
