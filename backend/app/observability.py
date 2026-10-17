"""
LangSmith tracing: setup and data redaction.

Tracing is switched on by environment variables, read by the langsmith
package itself (main.py loads .env into the environment first):

    LANGSMITH_TRACING=true   LANGSMITH_API_KEY=...   LANGSMITH_PROJECT=sqlnav-dev

LangChain and LangGraph runs (graph, nodes, LLM calls) are traced on their
own; the agent's tools are traced with @traceable (agent/tools.py). Every run
goes through one LangSmith client, set here with ls.configure(), so its
redaction applies to the whole trace: query result rows are replaced by
"[N rows hidden]" in every run (tool outputs, LLM inputs, graph state).
Questions, SQL, the schema (with its sample values), values found by
find_values and the model's replies are still sent, and a reply can restate
result values.
"""
from __future__ import annotations

import json
import logging

import langsmith as ls
from langchain_core.messages import BaseMessage, ToolMessage
from langsmith import utils as ls_utils

from app.logging_setup import get_logger

logger = logging.getLogger(__name__)

_REDACTION_FAILED = {"redacted": "redaction failed; data hidden"}
_MAX_DEPTH = 20


def tracing_enabled() -> bool:
    return bool(ls_utils.tracing_is_enabled())


def configure_tracing() -> None:
    """Sets the LangSmith client every run is sent with. Call once at startup."""
    if not tracing_enabled():
        return
    ls.configure(client=ls.Client(hide_inputs=redact_rows, hide_outputs=redact_rows))
    get_logger("agent").info("LangSmith tracing on: project=%s (result rows hidden)",
                             ls_utils.get_tracer_project())


def flush() -> None:
    """Sends runs still waiting in the background queue (call at shutdown)."""
    if not tracing_enabled():
        return
    from langchain_core.tracers.langchain import wait_for_all_tracers
    try:
        wait_for_all_tracers()
    except Exception:
        logger.exception("Flushing LangSmith traces failed")


# ── Redaction ────────────────────────────────────────────────────────────────

def redact_rows(data: dict) -> dict:
    """Run inputs/outputs with every query result's rows replaced. Rows show
    up as a "rows" list (tool artifacts, graph state) or inside the JSON text
    tools give the model ('{"columns": [...], "row_count": ..., "rows": [...]}').
    If anything goes wrong the whole payload is hidden, never sent as is."""
    try:
        return _redact(data, 0)
    except Exception:
        logger.exception("Redacting a LangSmith payload failed")
        return dict(_REDACTION_FAILED)


def _redact(value, depth: int):
    if depth > _MAX_DEPTH:
        return "[hidden: nested too deep]"
    if isinstance(value, dict):
        return {k: _hidden_rows(v) if k == "rows" and isinstance(v, list) else _redact(v, depth + 1)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v, depth + 1) for v in value]
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, BaseMessage):
        update = {"content": _redact(value.content, depth + 1)}
        if isinstance(value, ToolMessage) and value.artifact is not None:
            update["artifact"] = _redact(value.artifact, depth + 1)
        return value.model_copy(update=update)
    return value


def _hidden_rows(rows: list) -> str:
    return f"[{len(rows)} rows hidden]"


def _redact_text(text: str) -> str:
    # QueryResult.to_llm_string and the short history form both start this way.
    if not text.startswith('{"columns"'):
        return text
    try:
        payload = json.loads(text)
    except ValueError:
        return "[query result hidden]"
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        payload["rows"] = _hidden_rows(payload["rows"])
    return json.dumps(payload, ensure_ascii=False)
