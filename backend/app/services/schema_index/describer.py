"""
LLM-written table and column descriptions, one structured call per table.

The model sees the same profile text the agent sees (types, keys, joins,
sample values, formats), so descriptions explain meaning, units, encodings and
what one row represents. They are generated once per table structure and
stored; human edits always take precedence (see service.py).
"""
from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.services.schema_index.profiler import SchemaProfile
from app.services.schema_index.render import render_table

logger = logging.getLogger(__name__)


class ColumnDescription(BaseModel):
    name: str = Field(description="Column name exactly as given")
    description: str = Field(description="At most 20 words")


class TableDescription(BaseModel):
    description: str = Field(description="One sentence: what one row represents")
    columns: list[ColumnDescription]


_SYSTEM = (
    "You document database tables for analysts who write SQL against them. "
    "Write descriptions from the evidence given: names, types, keys, joins, "
    "sample values and detected formats. Be concrete and brief.\n"
    "- Table: one sentence saying what one row represents (its grain), e.g. "
    "'One row per customer per month with gas consumption.'\n"
    "- Column: at most 20 words. Say what it means, its unit or encoding, and "
    "what codes mean when the values make it clear. Do not repeat the type or "
    "list the sample values.\n"
    "- If the meaning is uncertain, start with 'Possibly'. Never invent facts "
    "the evidence doesn't support.\n"
    "- Describe every column, using the exact column names."
)


def describe_table(llm: BaseChatModel, profile: SchemaProfile, table_name: str) -> dict:
    """Returns {"description": str, "columns": {column: str}} for one table."""
    table = profile.tables[table_name]
    relations = [
        r for r in profile.relations if table_name in (r.from_table, r.to_table)
    ]
    neighbours = sorted({r.to_table if r.from_table == table_name else r.from_table
                         for r in relations} - {table_name})
    prompt = render_table(table, relations, level="full")
    if neighbours:
        prompt += "\n\nRelated tables: " + ", ".join(neighbours)

    structured = llm.with_structured_output(TableDescription)
    result: TableDescription = structured.invoke(
        [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)]
    )

    by_lower = {c.name.lower(): c.name for c in table.columns}
    columns = {}
    for item in result.columns:
        name = by_lower.get(item.name.strip().strip('"').lower())
        if name and item.description.strip():
            columns[name] = item.description.strip()
    return {"description": result.description.strip(), "columns": columns}


def describe_tables(
    llm: BaseChatModel,
    profile: SchemaProfile,
    tables: list[str],
    *,
    on_described=None,
    on_failed=None,
) -> dict[str, dict]:
    """Describe tables one at a time (keeps provider rate limits predictable).

    `on_described(table, docs)` is called after each table so callers can
    persist progress; a failed table is logged, reported to `on_failed(table)`
    and skipped. A rate limit stops the run: the tables after it are neither
    described nor failed.
    """
    out: dict[str, dict] = {}
    for name in tables:
        if name not in profile.tables:
            continue
        try:
            docs = describe_table(llm, profile, name)
        except Exception as exc:
            if _is_rate_limit(exc):
                logger.warning("Rate limited while describing %s; stopping early", name)
                break
            logger.warning("Could not describe table %s: %s", name, exc)
            if on_failed:
                on_failed(name)
            continue
        out[name] = docs
        if on_described:
            on_described(name, docs)
    return out


def _is_rate_limit(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(s in text for s in ("429", "resourceexhausted", "resource_exhausted", "ratelimit"))
