"""
The conversation history sent to the model on each LLM call.

The checkpoint keeps every message; only what the model sees is shaped here.
The current turn is always sent whole. Earlier turns are sent in one of three
forms, newest first, each turn getting the richest form that still fits the
character budget (HistoryLimits.max_chars, about 4 characters per token):

    full       every message, as it was (only the last `full_turns` turns)
    short      the question, the successful submit_answer call with the first
               rows of its result, and the reply; exploration is dropped
    question   the question and the start of the reply

Once a turn does not fit even as a question, it and every older turn are left
out. The user's questions hold the details later turns depend on (definitions,
corrections) and the final SQL holds what exploration found (exact values,
join keys), so the short forms drop volume rather than meaning.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.services.agent.state import HistoryLimits
from app.services.agent.tools import SUBMIT_ANSWER

FULL, SHORT, QUESTION = "full", "short", "question"

_SHORT_ROWS = 5            # result rows kept in the short form
_SHORT_REPLY_CHARS = 600
_QUESTION_REPLY_CHARS = 300


@dataclass
class History:
    messages: list             # earlier turns (shaped) + the current turn
    forms: list[str]           # form of each earlier turn sent, oldest first
    dropped: int               # earlier turns left out
    chars: int                 # size of the earlier turns sent

    @property
    def shortened(self) -> bool:
        return self.dropped > 0 or any(f != FULL for f in self.forms)

    def submitted_sql(self) -> set[str]:
        """SQL of every successful submit_answer still in the history."""
        return {a["sql"] for m in self.messages
                if (a := _artifact(m)).get("kind") == SUBMIT_ANSWER and a.get("success")
                and a.get("sql")}


def build_history(messages: list, limits: HistoryLimits) -> History:
    turns = split_turns(messages)
    if not turns:
        return History(drop_unanswered_calls(list(messages)), [], 0, 0)
    current, earlier = turns[-1], turns[:-1]

    budget = limits.max_chars
    kept: list[tuple[str, list]] = []
    for age, turn in enumerate(reversed(earlier)):        # newest first
        options = ([FULL] if age < limits.full_turns else []) + [SHORT, QUESTION]
        for form in options:
            shaped = _shape(turn, form)
            size = sum(message_chars(m) for m in shaped)
            if size <= budget:
                budget -= size
                kept.append((form, shaped))
                break
        else:
            break                                         # this turn and older ones are dropped
    kept.reverse()
    out = [m for _, shaped in kept for m in shaped] + drop_unanswered_calls(current)
    return History(out, [form for form, _ in kept], len(earlier) - len(kept),
                   limits.max_chars - budget)


def split_turns(messages: list) -> list[list]:
    """Messages grouped by turn, each starting at its question. Anything
    before the first question is dropped."""
    turns: list[list] = []
    for m in messages:
        if isinstance(m, HumanMessage):
            turns.append([m])
        elif turns:
            turns[-1].append(m)
    return turns


def message_chars(m) -> int:
    """Rough size of a message as the provider receives it."""
    size = len(_text(m.content))
    if isinstance(m, AIMessage):
        if m.tool_calls:
            size += len(json.dumps([c.get("args") for c in m.tool_calls], default=str))
        size += len(str(m.additional_kwargs.get("reasoning_content") or ""))
    return size


# ── Turn forms ───────────────────────────────────────────────────────────────

def _shape(turn: list, form: str) -> list:
    if form == FULL:
        return drop_unanswered_calls(turn)
    question, reply = turn[0], _final_reply(turn)
    if form == QUESTION:
        return [question] + ([_clip_reply(reply, _QUESTION_REPLY_CHARS)] if reply else [])

    out = [question]
    submit = _successful_submit(turn)
    if submit is not None:
        call_msg, result = submit
        call = next(c for c in call_msg.tool_calls if c.get("id") == result.tool_call_id)
        out.append(_with_calls(call_msg, [call], content=""))
        out.append(result.model_copy(update={"content": _short_result(result)}))
    if reply is not None:
        out.append(_clip_reply(reply, _SHORT_REPLY_CHARS))
    return out


def _final_reply(turn: list) -> AIMessage | None:
    last = turn[-1]
    if isinstance(last, AIMessage) and not last.tool_calls and _text(last.content).strip():
        return last
    return None


def _successful_submit(turn: list) -> tuple[AIMessage, ToolMessage] | None:
    result = next((m for m in reversed(turn)
                   if _artifact(m).get("kind") == SUBMIT_ANSWER and _artifact(m).get("success")),
                  None)
    if result is None:
        return None
    call_msg = next((m for m in turn if isinstance(m, AIMessage)
                     and any(c.get("id") == result.tool_call_id for c in m.tool_calls or [])),
                    None)
    return (call_msg, result) if call_msg is not None else None


def _short_result(result: ToolMessage) -> str:
    """The answer's result reduced to its shape and first rows."""
    artifact = _artifact(result)
    rows = artifact.get("rows")
    if not isinstance(rows, list):
        return _clip(_text(result.content), 1_000)
    count = artifact.get("row_count")
    shown = rows[:_SHORT_ROWS]
    payload: dict = {"columns": artifact.get("columns") or [],
                     "row_count": count if count is not None else f">{len(rows)}",
                     "rows": shown}
    if len(shown) < (count if count is not None else len(rows) + 1):
        payload["note"] = (f"Earlier result, first {len(shown)} rows only. "
                           "Run the SQL again if you need the other rows.")
    return json.dumps(payload, default=str, ensure_ascii=False)


def _clip_reply(reply: AIMessage, limit: int) -> AIMessage:
    text = _text(reply.content)
    if len(text) <= limit:
        return reply
    return reply.model_copy(update={"content": _clip(text, limit)})


# ── Message helpers ──────────────────────────────────────────────────────────

def drop_unanswered_calls(messages: list) -> list:
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
                m = _with_calls(m, kept)
        out.append(m)
    return out


def _with_calls(m: AIMessage, calls: list, **update) -> AIMessage:
    """`m` with only `calls`; the provider's raw copy of the calls is dropped
    so it can't bring the others back."""
    extra = {k: v for k, v in m.additional_kwargs.items()
             if k not in ("tool_calls", "function_call")}
    return m.model_copy(update={"tool_calls": calls, "additional_kwargs": extra, **update})


def _artifact(m) -> dict:
    artifact = getattr(m, "artifact", None) if isinstance(m, ToolMessage) else None
    return artifact if isinstance(artifact, dict) else {}


def _text(content) -> str:
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content or "")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."
