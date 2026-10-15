"""
The SQL agent graph, compiled once per process and mode.

    link ──► agent ──tool calls──► tools ──► agent ... ──► END
               │                     │
               └─ no tool calls ─► END   └─ answer submitted ─► END (evaluation)
                                                             └─► agent writes the reply (production)

`link` (schema linking) only does work when the prompt holds the table list
instead of the full schema: it retrieves the tables the question most likely
needs (plus the bridge tables joining them) and adds them, in full, to this
turn's system prompt, so simple questions need no describe_tables call.

Budgets are enforced here, in graph state, rather than by the recursion limit:
the tools node refuses calls beyond Budget.max_tool_calls / max_sql_runs, and
once a budget is used up the next model call may only call submit_answer.
A model that explores but answers without submitting is asked to submit, too.
If no answer is submitted after Budget.max_forced_submits forced calls, the
graph ends and the caller falls back to the last successful exploratory query.

Everything connection-specific (engine, schema, model) comes from the
AgentContext passed with `graph.invoke(..., context=ctx)`.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.runtime import Runtime
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings
from app.services.agent import prompts, trace_log
from app.services.agent.state import AgentContext, AgentState, Budget
from app.services.agent.tools import (
    SQL_TOOLS, SUBMIT_ANSWER, SUBMIT_SCHEMA, TOOL_SCHEMAS, run_tool,
)
from app.services.schema_index.index_store import question_terms

logger = logging.getLogger(__name__)

RECURSION_LIMIT = 40           # safety net only; budgets end a turn long before
MAX_HISTORY_MESSAGES = 20      # messages kept from earlier turns of a conversation

_tool_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="agent-tool")


def is_rate_limit(exc: Exception) -> bool:
    """Provider rate-limit errors, which arrive as different exception types
    (Gemini RESOURCE_EXHAUSTED, Groq RateLimitError, ...)."""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(s in text for s in ("429", "resourceexhausted", "resource_exhausted", "ratelimit"))


# ──────────────────────────────────────────────────────────────────────────────
# Postgres checkpointer (production conversations), created lazily
# ──────────────────────────────────────────────────────────────────────────────
_checkpointer_lock = threading.Lock()
_checkpointer: PostgresSaver | None = None


def _get_checkpointer() -> PostgresSaver:
    global _checkpointer
    with _checkpointer_lock:
        if _checkpointer is None:
            db_url = get_settings().DATABASE_URL
            if not db_url:
                raise RuntimeError(
                    "DATABASE_URL must be set in settings to use the Postgres checkpointer.")
            pool = ConnectionPool(conninfo=db_url, min_size=2, max_size=5,
                                  kwargs={"autocommit": True, "row_factory": dict_row})
            saver = PostgresSaver(pool)
            saver.setup()                  # creates checkpoint tables if absent
            _checkpointer = saver
            logger.info("Postgres checkpointer initialized")
        return _checkpointer


# ──────────────────────────────────────────────────────────────────────────────
# Models with tools bound, cached per model instance
# ──────────────────────────────────────────────────────────────────────────────

class _BoundModels:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.tool_names = [t.name for t in TOOL_SCHEMAS]
        self.tools = llm.bind_tools(TOOL_SCHEMAS)
        self.submit = llm.bind_tools([SUBMIT_SCHEMA])
        try:
            self.forced = llm.bind_tools([SUBMIT_SCHEMA], tool_choice=SUBMIT_ANSWER)
        except Exception:                  # provider without forced tool choice
            self.forced = None


_bound: dict[int, _BoundModels] = {}
_bound_lock = threading.Lock()


def _models(llm: BaseChatModel) -> _BoundModels:
    with _bound_lock:
        models = _bound.get(id(llm))
        if models is None or models.llm is not llm:
            if len(_bound) >= 16:
                _bound.pop(next(iter(_bound)))
            models = _bound[id(llm)] = _BoundModels(llm)
        return models


# ──────────────────────────────────────────────────────────────────────────────
# Conversation history sent to the model
# ──────────────────────────────────────────────────────────────────────────────

def turn_start(messages: list) -> int:
    """Index of the current turn's question."""
    return max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=0)


def _history(messages: list) -> list:
    """The whole current turn, plus the last MAX_HISTORY_MESSAGES messages of
    earlier turns (starting at a question so tool results keep their calls)."""
    start = turn_start(messages)
    earlier = messages[:start][-MAX_HISTORY_MESSAGES:]
    while earlier and not isinstance(earlier[0], HumanMessage):
        earlier = earlier[1:]
    return _drop_unanswered_calls(earlier + messages[start:])


def _drop_unanswered_calls(messages: list) -> list:
    """Providers reject a tool call without a result. Calls can be left
    unanswered when a turn ends early (e.g. the model called a tool while
    writing its final reply), so strip them before replaying history."""
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    out = []
    for m in messages:
        if isinstance(m, AIMessage) and m.tool_calls:
            kept = [c for c in m.tool_calls if c.get("id") in answered]
            if len(kept) != len(m.tool_calls):
                if not kept and not m.content:
                    continue
                extra = {k: v for k, v in m.additional_kwargs.items()
                         if k not in ("tool_calls", "function_call")}
                m = m.model_copy(update={"tool_calls": kept, "additional_kwargs": extra})
        out.append(m)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Nodes
# ──────────────────────────────────────────────────────────────────────────────

def _budget_used_up(state: AgentState, budget: Budget) -> bool:
    return (state.get("tool_calls_used", 0) >= budget.max_tool_calls
            or state.get("sql_runs_used", 0) >= budget.max_sql_runs)


def _invoke(ctx: AgentContext, number: int, purpose: str, bound, tools: list[str],
            tool_choice: str | None, messages: list) -> AIMessage:
    """One LLM call, logged with its parameters, timing and result."""
    trace_log.llm_request(ctx.turn_id, number, purpose, ctx.llm, tools, tool_choice, messages)
    start = time.perf_counter()
    try:
        response = bound.invoke(messages)
    except Exception as exc:
        trace_log.llm_failed(ctx.turn_id, number, time.perf_counter() - start, exc)
        raise
    trace_log.llm_response(ctx.turn_id, number, response, time.perf_counter() - start)
    return response


def _llm_calls_so_far(history: list) -> int:
    turn = history[turn_start(history):]
    return sum(1 + (m.response_metadata or {}).get("discarded_llm_calls", 0)
               for m in turn if isinstance(m, AIMessage))


_SHORT_QUESTION_TERMS = 6     # follow-ups this short also search with the previous question


def _retrieval_query(state: AgentState) -> str:
    """The text schema linking searches with: the question, plus the previous
    question for short follow-ups ("and by year?") that name no tables."""
    question =state.get("last_user_input") or ""
    if len(question_terms(question)) > _SHORT_QUESTION_TERMS:
        return question
    earlier = [m for m in state["messages"][:turn_start(state["messages"])]
               if isinstance(m, HumanMessage)]
    if not earlier:
        return question
    previous = earlier[-1].content if isinstance(earlier[-1].content, str) else ""
    return f"{question}\n{previous}"


def _link(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    ctx = runtime.context
    empty = {"linked_schema": None, "linked_tables": [], "link_method": None}
    if not ctx.catalog_prompt:
        return empty
    start = time.perf_counter()
    try:
        result = ctx.schema.link(_retrieval_query(state), ctx.link_max_tables, ctx.link_max_chars)
    except Exception as exc:
        logger.exception("Schema linking failed")
        trace_log.schema_link_failed(ctx.turn_id, f"{type(exc).__name__}: {exc}")
        return empty
    if result is None:
        trace_log.schema_linked(ctx.turn_id, ctx.schema.search_method, [], [], 0,
                                time.perf_counter() - start)
        return empty
    trace_log.schema_linked(ctx.turn_id, result.method, result.tables, result.bridges,
                            len(result.text), time.perf_counter() - start)
    return {"linked_schema": result.text, "linked_tables": result.all_tables,
            "link_method": result.method}


def _agent(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    ctx = runtime.context
    models = _models(ctx.llm)
    system = prompts.system_prompt(ctx.schema_context, ctx.budget, catalog=ctx.catalog_prompt,
                                   linked=state.get("linked_schema"))
    history = _history(state["messages"])
    answered = state.get("answer") is not None
    number = _llm_calls_so_far(history) + 1

    if not answered and _budget_used_up(state, ctx.budget):
        trace_log.llm_note(ctx.turn_id, "budget used up: only submit_answer is allowed now")
        return _force_submit(ctx, state, models, system, history, prompts.BUDGET_REASON, number)

    purpose = "write reply" if answered else "agent step"
    response = _invoke(ctx, number, purpose, models.tools, models.tool_names, None,
                       [SystemMessage(content=system)] + history)
    if (not answered and not response.tool_calls and state.get("sql_runs_used", 0)
            and not state.get("forced_submits", 0)):
        # Explored, then replied without submitting: ask for the final query.
        trace_log.llm_note(ctx.turn_id, "replied without submitting after exploring: "
                                        "discarding the reply and asking for submit_answer")
        return _force_submit(ctx, state, models, system, history, prompts.UNSUBMITTED_REASON,
                             number + 1, discarded=response)
    return {"messages": [response]}


def _force_submit(ctx: AgentContext, state: AgentState, models: _BoundModels, system: str,
                  history: list, reason: str, number: int,
                  discarded: AIMessage | None = None) -> dict:
    messages = [SystemMessage(content=system + prompts.FORCE_SUBMIT_NOTE.format(reason=reason))]
    messages += history
    response = None
    if models.forced is not None:
        try:
            response = _invoke(ctx, number, "forced submit", models.forced, [SUBMIT_ANSWER],
                               SUBMIT_ANSWER, messages)
        except Exception as exc:
            if is_rate_limit(exc):
                raise
            # e.g. DeepSeek thinking mode rejects a forced tool choice.
            trace_log.llm_note(ctx.turn_id, "provider rejected the forced tool choice; "
                                            "retrying with submit_answer as the only tool")
            models.forced = None
            number += 1
    if response is None:
        response = _invoke(ctx, number, "submit only", models.submit, [SUBMIT_ANSWER], None,
                           messages)
    if discarded is not None:
        response = _absorb_usage(response, discarded)
    return {"messages": [response], "forced_submits": state.get("forced_submits", 0) + 1}


def _absorb_usage(response: AIMessage, discarded: AIMessage) -> AIMessage:
    """Keeps a dropped reply's tokens and call count in the turn's totals."""
    usage = dict(response.usage_metadata or {})
    for key, value in (discarded.usage_metadata or {}).items():
        if isinstance(value, int):
            usage[key] = usage.get(key, 0) + value
    metadata = dict(response.response_metadata or {})
    metadata["discarded_llm_calls"] = metadata.get("discarded_llm_calls", 0) + 1
    update = {"response_metadata": metadata}
    if usage:
        update["usage_metadata"] = usage
    return response.model_copy(update=update)


def _tools(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    ctx = runtime.context
    budget = ctx.budget
    calls = state["messages"][-1].tool_calls
    used = state.get("tool_calls_used", 0)
    sql_used = state.get("sql_runs_used", 0)
    submitting = any(c["name"] == SUBMIT_ANSWER for c in calls)

    planned: list[tuple[dict, str | None]] = []      # (call, reason it is not run)
    submit_seen = False
    for call in calls:
        name = call["name"]
        if name == SUBMIT_ANSWER:
            # Always allowed: forced calls after the budget is used up must run.
            skip = "Only one submit_answer per turn is run." if submit_seen else None
            submit_seen = True
        elif submitting:
            skip = "Skipped: the final answer was submitted in the same turn."
        elif used >= budget.max_tool_calls:
            skip = "Not run: the tool budget for this question is used up. Call submit_answer now."
        elif name in SQL_TOOLS and sql_used >= budget.max_sql_runs:
            skip = "Not run: the SQL budget for this question is used up. Call submit_answer now."
        else:
            skip = None
        if skip is None:
            used += 1
            sql_used += name in SQL_TOOLS
        planned.append((call, skip))

    def execute(item):
        call, skip = item
        if skip is not None:
            trace_log.tool_skipped(ctx.turn_id, call, skip)
            return skip, {"kind": call["name"], "success": False, "skipped": True}
        trace_log.tool_started(ctx.turn_id, call)
        start = time.perf_counter()
        content, artifact = run_tool(ctx, call["name"], call.get("args") or {})
        trace_log.tool_finished(ctx.turn_id, call, content, artifact, time.perf_counter() - start)
        return content, artifact

    runnable = sum(1 for _, skip in planned if skip is None)
    results = list(_tool_pool.map(execute, planned)) if runnable > 1 else [execute(p) for p in planned]

    messages, answer = [], state.get("answer")
    for (call, _), (content, artifact) in zip(planned, results):
        messages.append(ToolMessage(
            content=content, tool_call_id=call["id"], name=call["name"], artifact=artifact,
            status="success" if artifact.get("success") else "error",
        ))
        if artifact.get("kind") == SUBMIT_ANSWER and artifact.get("success"):
            answer = artifact
    return {"messages": messages, "tool_calls_used": used, "sql_runs_used": sql_used,
            "answer": answer}


# ──────────────────────────────────────────────────────────────────────────────
# Routing
# ──────────────────────────────────────────────────────────────────────────────

def _after_agent(state: AgentState) -> str:
    if state.get("answer") is not None:
        return END                         # production: the reply is written
    last = state["messages"][-1]
    return "tools" if isinstance(last, AIMessage) and last.tool_calls else END


def _after_tools_for(evaluation: bool):
    def route(state: AgentState, runtime: Runtime[AgentContext]) -> str:
        if state.get("answer") is not None:
            # Evaluation scores the SQL only, so the reply is never written.
            return END if evaluation else "agent"
        if state.get("forced_submits", 0) >= runtime.context.budget.max_forced_submits:
            return END                     # give up; the caller uses the best query so far
        return "agent"
    return route


# ──────────────────────────────────────────────────────────────────────────────
# Compiled graphs
# ──────────────────────────────────────────────────────────────────────────────

_graphs: dict[bool, object] = {}
_graphs_lock = threading.Lock()


def get_graph(evaluation: bool):
    """The compiled graph. Production keeps conversations in the Postgres
    checkpointer; evaluation runs single turns without one."""
    with _graphs_lock:
        if evaluation not in _graphs:
            graph = StateGraph(AgentState, context_schema=AgentContext)
            graph.add_node("link", _link)
            graph.add_node("agent", _agent)
            graph.add_node("tools", _tools)
            graph.set_entry_point("link")
            graph.add_edge("link", "agent")
            graph.add_conditional_edges("agent", _after_agent, ["tools", END])
            graph.add_conditional_edges("tools", _after_tools_for(evaluation), ["agent", END])
            _graphs[evaluation] = graph.compile(
                checkpointer=None if evaluation else _get_checkpointer())
        return _graphs[evaluation]
