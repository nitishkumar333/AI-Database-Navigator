"""
Terminal log of what the agent does: every LLM call and every tool call, with
their parameters, timing and outcome.

Lines go to the "agent" area of the shared log (app/logging_setup.py).
AGENT_LOG_LEVEL controls it: INFO (default) logs calls and results, DEBUG also
logs full tool output and the model's input messages, WARNING silences it.

Every line starts with the turn's id, so turns running concurrently (several
users, or `evaluation run --workers N`) stay readable.
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, BaseMessage

from app.logging_setup import get_logger

_MAX_ARG_CHARS = 2_000
_MAX_TEXT_CHARS = 300

def _log() -> logging.Logger:
    return get_logger("agent")


def _clip(text: str, limit: int) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _one_line(text: str, limit: int = _MAX_TEXT_CHARS) -> str:
    return _clip(" ".join(str(text).split()), limit)


def format_args(args: dict | None) -> str:
    """Tool arguments as one-line JSON."""
    text = json.dumps(args or {}, ensure_ascii=False, default=str)
    return _clip(text, _MAX_ARG_CHARS)


def _content_text(content) -> str:
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content or "")


def model_name(llm) -> str:
    for attr in ("model_name", "model"):
        value = getattr(llm, attr, None)
        if isinstance(value, str) and value:
            return value
    return type(llm).__name__


# ── Turn ─────────────────────────────────────────────────────────────────────

def turn_started(turn_id: str, mode: str, thread_id: str, question: str, llm,
                 schema_prompt: str = "") -> None:
    _log().info("[%s] === TURN START | mode=%s thread=%s model=%s schema_prompt=%s | question=%r",
                turn_id, mode, thread_id, model_name(llm), schema_prompt,
                _one_line(question, 500))


def turn_finished(turn_id: str, source: str | None, sql: str, row_count: int,
                  state: dict, seconds: float) -> None:
    _log().info("[%s] === TURN END | answer_source=%s rows=%d tool_calls=%d sql_runs=%d "
                "forced_submits=%d | %.2fs%s",
                turn_id, source, row_count, state.get("tool_calls_used", 0),
                state.get("sql_runs_used", 0), state.get("forced_submits", 0), seconds,
                f"\n    final SQL: {sql}" if sql else "")


def turn_failed(turn_id: str, error: str, seconds: float) -> None:
    _log().warning("[%s] === TURN FAILED after %.2fs: %s", turn_id, seconds, error)


# ── LLM calls ────────────────────────────────────────────────────────────────

def llm_request(turn_id: str, number: int, purpose: str, llm, tools: list[str],
                tool_choice: str | None, messages: list[BaseMessage]) -> None:
    log = _log()
    chars = sum(len(_content_text(m.content)) for m in messages)
    log.info("[%s] LLM #%d request (%s) | model=%s tools=%s tool_choice=%s | %d messages, ~%d chars",
             turn_id, number, purpose, model_name(llm), tools, tool_choice or "auto",
             len(messages), chars)
    if log.isEnabledFor(logging.DEBUG):
        for m in messages[1:]:          # the system prompt is long and fixed
            log.debug("[%s]     %s: %s", turn_id, type(m).__name__,
                      _clip(_content_text(m.content) or getattr(m, "tool_calls", ""), 2_000))


def llm_response(turn_id: str, number: int, response: AIMessage, seconds: float) -> None:
    usage = response.usage_metadata or {}
    calls = response.tool_calls or []
    lines = [f"[{turn_id}] LLM #{number} response | {seconds:.2f}s | tokens in={usage.get('input_tokens', '?')} "
             f"out={usage.get('output_tokens', '?')} | "
             + (f"{len(calls)} tool call(s)" if calls else "text reply")]
    for call in calls:
        lines.append(f"    -> {call.get('name')}({format_args(call.get('args'))})")
    text = _content_text(response.content).strip()
    if text:
        lines.append(f"    text: {_one_line(text)}")
    _log().info("\n".join(lines))


def llm_failed(turn_id: str, number: int, seconds: float, exc: Exception) -> None:
    _log().warning("[%s] LLM #%d FAILED after %.2fs: %s: %s",
                   turn_id, number, seconds, type(exc).__name__, _one_line(exc, 500))


def llm_note(turn_id: str, message: str) -> None:
    _log().info("[%s] NOTE: %s", turn_id, message)


# ── Schema linking ───────────────────────────────────────────────────────────

def schema_linked(turn_id: str, method: str, tables: list[str], bridges: list[str],
                  chars: int, seconds: float) -> None:
    _log().info("[%s] LINK %s | %.2fs | tables=%s bridges=%s | %s chars added to the prompt",
                turn_id, method, seconds, tables, bridges, f"{chars:,}")


def schema_link_failed(turn_id: str, error: str) -> None:
    _log().warning("[%s] LINK FAILED: %s", turn_id, _one_line(error, 500))


# ── Tool calls ───────────────────────────────────────────────────────────────

def tool_skipped(turn_id: str, call: dict, reason: str) -> None:
    _log().info("[%s] TOOL %s(%s) SKIPPED: %s",
                turn_id, call.get("name"), format_args(call.get("args")), reason)


def tool_started(turn_id: str, call: dict) -> None:
    _log().info("[%s] TOOL %s(%s)", turn_id, call.get("name"), format_args(call.get("args")))


def tool_finished(turn_id: str, call: dict, content: str, artifact: dict, seconds: float) -> None:
    log = _log()
    name = call.get("name")
    if artifact.get("success"):
        log.info("[%s] TOOL %s ok | %.2fs | %s", turn_id, name, seconds, _summary(artifact, content))
    else:
        log.info("[%s] TOOL %s ERROR | %.2fs | %s", turn_id, name, seconds, _one_line(content, 500))
    if log.isEnabledFor(logging.DEBUG):
        log.debug("[%s]     %s output:\n%s", turn_id, name, _clip(content, 4_000))


def _summary(artifact: dict, content: str) -> str:
    if "rows" in artifact:
        count = artifact.get("row_count")
        shown = len(artifact.get("rows") or [])
        rows = f"{count} rows" if count is not None else f"more rows than counted ({shown} kept)"
        return f"{rows}, columns={artifact.get('columns')}"
    if "tables" in artifact:
        return f"tables={artifact['tables']}"
    if "matches" in artifact:
        return f"matches={_clip(json.dumps(artifact['matches'], ensure_ascii=False), 300)}"
    return _one_line(content)
