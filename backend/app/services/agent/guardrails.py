"""
Deterministic guardrails for the SQL agent: regexes and the sqlglot tree the
executor parses anyway, never an LLM call, so they add microseconds per turn.

    question ──check_question──► graph ──run_sql / submit_answer──► check_sql
                                   │                                    │
                     reply ◄─leaks_prompt                  rows ─► redact_rows

  check_question  before the graph runs: an empty, too long, prompt-injection
                  or data-changing request is refused without any LLM call and
                  is not written to the conversation's thread.
  check_sql       every SQL tool call, after validate_sql's read-only check:
                  only the conversation's tables (its knowledge-base scope),
                  no system catalogs or other schemas, credential columns never
                  selected (they may still be filtered on or counted).
  redact_rows     every SQL tool result: credential columns and secret-looking
                  values are replaced before the model or the user sees them.
  leaks_prompt    a reply that repeats the system prompt is replaced (graph).

The question checks are heuristics tuned for precision (a refused real
question is worse than a missed attack: the SQL layer already makes every
query read-only); GUARDRAILS_ENABLED=false turns the injection and
write-request checks off. The SQL and result checks are always on.
"""
from __future__ import annotations

import functools
import re
import unicodedata
from dataclasses import dataclass

from sqlglot import exp

# ──────────────────────────────────────────────────────────────────────────────
# Question
# ──────────────────────────────────────────────────────────────────────────────

BLOCKED_EMPTY = "empty"
BLOCKED_TOO_LONG = "too_long"
BLOCKED_INJECTION = "prompt_injection"
BLOCKED_WRITE = "write_request"

_MESSAGES = {
    BLOCKED_EMPTY: "Please type a question about your data.",
    BLOCKED_TOO_LONG: ("Your question is too long ({length:,} characters; the limit is "
                       "{limit:,}). Please shorten it."),
    BLOCKED_INJECTION: ("Suspicious activity detected. Please something about your data."),
    BLOCKED_WRITE: ("I can only read data: I can't change, add or delete anything in the "
                    "database. Ask me about the data instead, e.g. how many rows would match."),
}


@dataclass(frozen=True)
class Blocked:
    code: str           # BLOCKED_*
    message: str        # shown to the user


# Prompt injection: instruction overrides, prompt extraction, role hijacking and
# chat-template markup. Matched on the lowercased question with whitespace
# collapsed. "ignore my previous instructions" (a user correcting themselves)
# does not match: only "the/your/all/system ..." instructions do.
_INJECTION = [re.compile(p) for p in (
    r"\b(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+(?:of\s+)?)?"
    r"(?:the\s+|your\s+|any\s+|these\s+|those\s+)?"
    r"(?:(?:previous|prior|above|earlier|preceding|system|original|initial|developer|safety)\s+)*"
    r"(?:instructions?|prompts?|rules|guidelines|directives|guardrails|restrictions|programming)\b",
    r"\bsystem\s+(?:prompt|message|instructions?)\b",
    r"\b(?:reveal|show|print|display|repeat|output|tell|give|share|leak|dump|list|"
    r"what\s+(?:is|are|were|was))\b(?:\s+\w+){0,3}?\s+your\s+(?:\w+\s+)?"
    r"(?:prompt|instructions|rules|guidelines|directives|configuration)\b",
    r"\b(?:repeat|print|output|echo)\s+(?:everything|all|the\s+text|the\s+words)\s+"
    r"(?:above|before)\b",
    r"\byou\s+are\s+now\b",
    r"\bfrom\s+now\s+on,?\s+you\b",
    r"\bpretend\s+(?:to\s+be|you\s+are)\b",
    r"\b(?:developer|god|jailbreak|dan)\s+mode\b",
    r"\bjailbreak",
    r"\bdo\s+anything\s+now\b",
    r"\bno\s+longer\s+(?:bound|restricted|limited)\b",
    r"<\|?\s*(?:im_start|im_end|system|endoftext)\s*\|?>",
    r"\[/?(?:inst|sys)\]",
    r"<<\s*/?sys\s*>>",
    r"(?:^|\n)\s*(?:system|assistant)\s*:",
    r"#{2,}\s*(?:system|instruction)",
)]

# Requests to change data: SQL statements, or an imperative verb at the start
# of a clause followed (within a few words) by a generic data noun. "Show the
# deleted orders" or "the price drop by month" do not match.
_WRITE_SQL = re.compile(
    r"\b(?:(?:drop|truncate)\s+(?:table|database|schema|view|index|column|role|user)"
    r"|delete\s+from|insert\s+into|update\s+[\w.\"]+\s+set"
    r"|alter\s+(?:table|database|schema|role|user|column))\b")
_WRITE_REQUEST = re.compile(
    r"(?:^|[.!?;:\n]\s*|\b(?:please|pls|can\s+you|could\s+you|would\s+you|will\s+you|"
    r"i\s+want\s+(?:you\s+)?to|i\s+need\s+(?:you\s+)?to|i'?d\s+like\s+(?:you\s+)?to|help\s+me|"
    r"go\s+ahead\s+and|let'?s|now|then|and)\s+)"
    r"(?:delete|drop|truncate|wipe|erase|purge|insert|update|modify|alter|overwrite)\b"
    r"(?:\s+[\w\"'.-]+){0,4}?\s+(?:tables?|database|db|schema|rows?|records?|entries|entry|"
    r"data|columns?|values?|fields?)\b")

_ZERO_WIDTH = {"​", "‌", "‍", "⁠", "﻿", "­"}


def sanitize_question(text: str) -> str:
    """NFKC-normalized (full-width and other look-alike forms folded), without
    zero-width characters or control characters other than newline and tab
    (Postgres can't store NUL, and both hide words from the checks)."""
    text = unicodedata.normalize("NFKC", text or "")
    return "".join(ch for ch in text if ch in "\n\t" or (
        ch not in _ZERO_WIDTH and unicodedata.category(ch) not in ("Cc", "Cf"))).strip()


def check_question(text: str, *, max_chars: int, heuristics: bool = True) -> Blocked | None:
    """Why the (sanitized) question must not reach the agent, or None."""
    if not text:
        return Blocked(BLOCKED_EMPTY, _MESSAGES[BLOCKED_EMPTY])
    if len(text) > max_chars:
        return Blocked(BLOCKED_TOO_LONG,
                       _MESSAGES[BLOCKED_TOO_LONG].format(length=len(text), limit=max_chars))
    if not heuristics:
        return None
    low = re.sub(r"[ \t]+", " ", text.lower())     # newlines kept: "system:" lines
    if any(p.search(low) for p in _INJECTION):
        return Blocked(BLOCKED_INJECTION, _MESSAGES[BLOCKED_INJECTION])
    if _WRITE_SQL.search(low) or _WRITE_REQUEST.search(low):
        return Blocked(BLOCKED_WRITE, _MESSAGES[BLOCKED_WRITE])
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Credentials
# ──────────────────────────────────────────────────────────────────────────────

REDACTED = "[redacted]"

# Column names (camelCase split, lowercased) that hold credentials or card
# secrets. Whole words between underscores: "secretary" or "tokens_used" with
# numbers are left alone (only text values are redacted).
_CREDENTIAL_NAME = re.compile(
    r"(?:^|_)(?:password|passwd|passcode|pwd|pass_hash|secret|client_secret|api_?key|"
    r"secret_?key|private_?key|access_?key|token|auth_?token|access_?token|refresh_?token|"
    r"session_?token|reset_?token|otp_?secret|totp_?secret|mfa_?secret|cvv|cvc|"
    r"card_?number|cc_?number)(?:_|$)")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# Values that are secrets whatever their column is called (password hashes,
# JWTs, private keys, well-known API key formats).
_SECRET_VALUE = re.compile(
    r"^(?:\$(?:2[abxy]?|argon2(?:id|i|d)?|pbkdf2[\w-]*|scrypt|[156])\$\S+"
    r"|eyJ[\w-]{8,}\.eyJ[\w-]{8,}\.[\w-]{8,}"
    r"|(?:AKIA|ASIA)[0-9A-Z]{16}"
    r"|sk-[\w-]{20,}|(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}"
    r"|gh[pousr]_[A-Za-z0-9]{30,}|xox[abprs]-[\w-]{10,}|AIza[\w-]{35}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*)$")


def is_credential_column(name: str) -> bool:
    return bool(_CREDENTIAL_NAME.search(_CAMEL.sub("_", name or "").lower()))


def redact_rows(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """(rows with credential values replaced by REDACTED, the columns where
    something was). Only text values are replaced; NULLs and numbers stay."""
    if not rows:
        return rows, []
    credential = {c: is_credential_column(str(c)) for c in rows[0]}
    redacted: list[str] = []
    out = []
    for row in rows:
        new = row
        for column, value in row.items():
            if isinstance(value, (bytes, bytearray, memoryview)):
                hide = credential.get(column, False) and len(value) > 0
            elif isinstance(value, str):
                hide = bool(value) and (credential.get(column, False)
                                        or _SECRET_VALUE.match(value.strip()) is not None)
            else:
                hide = False
            if hide:
                if new is row:
                    new = dict(row)
                new[column] = REDACTED
                if column not in redacted:
                    redacted.append(column)
        out.append(new)
    return out, redacted


# ──────────────────────────────────────────────────────────────────────────────
# SQL
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}
_ALLOWED_QUALIFIERS = {"public"}
# A credential column may appear in the projection only inside these
# (COUNT(password), password IS NULL): they never output its value.
_VALUE_HIDING = (exp.Count, exp.Is)


def check_sql(tree: exp.Expression, schema) -> str | None:
    """An error for the model when the parsed query reads outside the
    conversation's tables or selects a credential column, else None.
    `schema` is the turn's SchemaView: its scope is the allowed tables."""
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            continue                    # a table function, e.g. generate_series(...)
        name, qualifier = table.name, (table.db or "").lower()
        if table.catalog or (qualifier and qualifier not in _ALLOWED_QUALIFIERS):
            if qualifier in _SYSTEM_SCHEMAS or qualifier.startswith("pg_"):
                return _SYSTEM_CATALOG_ERROR
            return (f"Table '{table.sql(dialect='postgres')}' is not available: refer to tables "
                    "by the names the schema lists, without a schema prefix.")
        if not qualifier and name.lower() in ctes:
            continue
        if schema.resolve_table(name) is None:
            if name.lower().startswith("pg_"):
                return _SYSTEM_CATALOG_ERROR
            return (f"Table '{name}' is not available. Use only the tables the schema lists "
                    "(search_schema finds them).")
    for column in tree.find_all(exp.Column):
        if is_credential_column(column.name) and _projected(column):
            return (f"Column '{column.name}' holds credentials and can't be selected. It may "
                    "only be filtered on or counted (e.g. WHERE col IS NULL, COUNT(col)).")
    return None


_SYSTEM_CATALOG_ERROR = ("System catalogs (pg_catalog, information_schema, pg_* views) are not "
                         "available. Use describe_tables / search_schema for the schema.")


def _projected(column: exp.Column) -> bool:
    """Whether the column's value is output by the SELECT it belongs to."""
    node = column
    while node.parent is not None:
        parent = node.parent
        if isinstance(parent, _VALUE_HIDING):
            return False
        if isinstance(parent, exp.Select):
            return node.arg_key == "expressions"
        node = parent
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Reply
# ──────────────────────────────────────────────────────────────────────────────

LEAK_REPLY = "I can't share how I'm set up. Ask me a question about the data in this database."

_SHINGLE = 6                # words per shingle
_LEAK_SHINGLES = 3          # a reply sharing this many with the prompts repeats them
_WORDS = re.compile(r"[a-z0-9_`']+")


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = _WORDS.findall(text.lower())
    return {tuple(words[i:i + _SHINGLE]) for i in range(len(words) - _SHINGLE + 1)}


@functools.cache
def _prompt_shingles() -> frozenset[tuple[str, ...]]:
    """Shingles of the fixed text of every prompt the agent sees (placeholders
    removed). Imported here, not at module level: the schema profiler imports
    this module, and prompts imports the schema package."""
    from app.services.agent import prompts
    parts = [re.sub(r"\{\w+\}", " ", prompts._WORKFLOW), prompts.REPLY_PROMPT,
             prompts.FORCE_SUBMIT_NOTE, prompts._SHORTENED_HISTORY_NOTE,
             prompts._PREVIOUS_SQL_HEADER, prompts._LINKED_HEADER, prompts._CATALOG_HEADER]
    parts += [prompts._FULL_FIRST_STEP, prompts._CATALOG_FIRST_STEP, prompts._LINKED_FIRST_STEP]
    return frozenset(_shingles("\n".join(parts)))


def text_of(content) -> str:
    """Message content as plain text (some providers return a list of parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content) if content else ""


def leaks_prompt(reply: str) -> bool:
    """Whether the reply repeats a passage of the agent's instructions."""
    if len(reply) < 40:
        return False
    shared = 0
    known = _prompt_shingles()
    for shingle in _shingles(reply):
        if shingle in known:
            shared += 1
            if shared >= _LEAK_SHINGLES:
                return True
    return False
