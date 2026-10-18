"""
The agent's tools.

The model sees TOOL_SCHEMAS (names, descriptions, arguments); the graph's tool
node calls run_tool() with the run's AgentContext, so tools never hold
connection state and the tool list is bound to the model once per process.

Every tool returns (content, artifact): content goes to the model, the
artifact (a dict, always with "kind" and "success") stays in the ToolMessage
for the caller.
"""
from __future__ import annotations

import difflib
import logging
import threading
import weakref
from contextlib import contextmanager
from typing import Literal

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from langsmith import traceable
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.agent.state import AgentContext
from app.services.display import DisplayHint, describe_result
from app.services.schema_index.join_graph import JoinGraph
from app.services.schema_index.profiler import quote_ident, type_family
from app.services.schema_index.render import render_table, sql_ident
from app.services.validate_sql import SafeSqlExecutor
from app.utils.db_manager import get_schema_context as basic_schema_context

logger = logging.getLogger(__name__)

SEARCH_SCHEMA = "search_schema"
DESCRIBE_TABLES = "describe_tables"
FIND_VALUES = "find_values"
RUN_SQL = "run_sql"
SUBMIT_ANSWER = "submit_answer"
SQL_TOOLS = {RUN_SQL, SUBMIT_ANSWER}

_MAX_DESCRIBE = 6
_FIND_VALUES_MAX_COLUMNS = 8      # live-searched columns when no column is given
_FIND_VALUES_TIMEOUT_MS = 2_000
_FIND_VALUES_PER_COLUMN = 5
_EXPLORE_COUNT_LIMIT = 1_000      # run_sql counts result rows up to this many
_ANSWER_COUNT_LIMIT = 5_000


# ──────────────────────────────────────────────────────────────────────────────
# Schemas the model sees
# ──────────────────────────────────────────────────────────────────────────────

class SearchSchemaArgs(BaseModel):
    query: str = Field(description="Words describing the data you need, e.g. 'customer segment' or 'loan payments'")


class DescribeTablesArgs(BaseModel):
    tables: list[str] = Field(description=f"Table names, at most {_MAX_DESCRIBE}")


class FindValuesArgs(BaseModel):
    text: str = Field(description="The value as the user wrote it, e.g. 'czech republic' or 'premium'")
    column: str | None = Field(
        default=None,
        description="Optional 'table.column' to search; leave empty to search likely text columns")


class RunSqlArgs(BaseModel):
    sql: str = Field(description="One read-only PostgreSQL SELECT statement")
    purpose: str = Field(description="What this check is for, in a few words")


class SubmitAnswerArgs(BaseModel):
    sql: str = Field(description="The final read-only PostgreSQL SELECT that answers the question")
    assumptions: str = Field(
        default="",
        description="Interpretations you made (definitions, filters, ambiguous terms); empty if none")
    # Flat, null-free fields: every supported provider accepts them in a tool schema.
    display: Literal["auto", "table", "stat", "cards", "bar", "line", "pie", "scatter"] = Field(
        default="auto",
        description="How the UI shows the result: table, stat (one row of values), cards "
                    "(records with an image column), bar / line / pie / scatter chart, or auto")
    x: str = Field(default="", description="Charts: the result column for the x axis, "
                                           "categories or pie slices; empty to let the UI pick")
    y: list[str] = Field(default_factory=list,
                         description="Charts: the numeric result columns to plot; empty for all")
    series: str = Field(default="", description="Bar/line/scatter charts: optional result column "
                                                "whose values become separate series (one y only)")


def _schema(name: str, description: str, args: type[BaseModel]) -> StructuredTool:
    def _not_called_directly(**_):
        raise RuntimeError("Agent tools run through run_tool()")
    return StructuredTool.from_function(func=_not_called_directly, name=name,
                                        description=description, args_schema=args)


TOOL_SCHEMAS = [
    _schema(SEARCH_SCHEMA,
            "Search the database's tables and columns by meaning (names, descriptions, sample "
            "values). Use it to find where data lives when the schema in the prompt doesn't "
            "make it obvious.", SearchSchemaArgs),
    _schema(DESCRIBE_TABLES,
            "Full details of the given tables: every column with type, description, sample "
            "values and keys, plus the join conditions between the tables (through bridge "
            "tables if needed). Use it before joining tables whose relationship is unclear.",
            DescribeTablesArgs),
    _schema(FIND_VALUES,
            "Find how a value the user mentioned is actually stored (spelling, case, codes), "
            "e.g. 'czech' -> country = 'Czech Republic'. Use it before filtering on a text value "
            "that isn't listed in the schema.", FindValuesArgs),
    _schema(RUN_SQL,
            "Run an exploratory read-only SELECT (distinct values, counts, checking a join or "
            "a filter) and see up to 20 rows plus the total row count. Not the final answer. "
            "Independent checks can be requested together in one turn.", RunSqlArgs),
    _schema(SUBMIT_ANSWER,
            "Submit the final SELECT that answers the question. It is executed and its result "
            "is the answer. Call it exactly once, when you are confident; this ends the search.",
            SubmitAnswerArgs),
]
SUBMIT_SCHEMA = TOOL_SCHEMAS[-1]
TOOL_NAMES = {t.name for t in TOOL_SCHEMAS}


# ──────────────────────────────────────────────────────────────────────────────
# Concurrency: parallel tool calls share the connection's small engine pool
# ──────────────────────────────────────────────────────────────────────────────

_MAX_PARALLEL_SQL = 3
_slots: "weakref.WeakKeyDictionary[Engine, threading.BoundedSemaphore]" = weakref.WeakKeyDictionary()
_slots_lock = threading.Lock()


@contextmanager
def sql_slot(engine: Engine):
    """Limits concurrent queries per engine to fewer than its pool holds."""
    with _slots_lock:
        slot = _slots.get(engine)
        if slot is None:
            try:
                capacity = engine.pool.size() + max(engine.pool._max_overflow, 0)
            except Exception:
                capacity = _MAX_PARALLEL_SQL
            slot = _slots[engine] = threading.BoundedSemaphore(max(1, min(_MAX_PARALLEL_SQL, capacity - 1)))
    with slot:
        yield


# ──────────────────────────────────────────────────────────────────────────────
# Dispatch
# ──────────────────────────────────────────────────────────────────────────────

def _trace_inputs(inputs: dict) -> dict:
    """LangSmith: record the tool's arguments only, not the AgentContext
    (engine, model, schema text)."""
    return dict(inputs.get("args") or {})


def _trace_outputs(output) -> dict:
    """LangSmith: what the model saw, plus a summary of the artifact (its
    rows already appear in the content)."""
    content, artifact = output
    summary = {"content": content, "success": artifact.get("success")}
    for key in ("row_count", "tables", "method"):
        if key in artifact:
            summary[key] = artifact[key]
    return summary


# The graph passes langsmith_extra={"name": <tool>} so each run is named after its tool.
@traceable(run_type="tool", process_inputs=_trace_inputs, process_outputs=_trace_outputs)
def run_tool(ctx: AgentContext, name: str, args: dict) -> tuple[str, dict]:
    impl = _IMPLEMENTATIONS.get(name)
    if impl is None:
        return (f"Error: unknown tool '{name}'. Available: {', '.join(sorted(TOOL_NAMES))}.",
                {"kind": name, "success": False})
    try:
        return impl(ctx, **(args or {}))
    except TypeError as exc:            # missing / unexpected arguments
        return f"Error: bad arguments for {name}: {exc}", {"kind": name, "success": False}
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return f"Error: {name} failed: {exc}", {"kind": name, "success": False}


# ──────────────────────────────────────────────────────────────────────────────
# search_schema
# ──────────────────────────────────────────────────────────────────────────────

def _clip(value: str | None, limit: int) -> str:
    value = " ".join((value or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def search_schema(ctx: AgentContext, query: str) -> tuple[str, dict]:
    view = ctx.schema
    results = view.search(query)
    if not results:
        names = ", ".join(sql_ident(t) for t in view.scope[:80])
        return (f"No tables or columns match '{query}'. Tables available: {names}",
                {"kind": SEARCH_SCHEMA, "success": True, "tables": []})
    lines = []
    for match in results:
        table = match.table
        head = f"TABLE {sql_ident(table.name)}"
        facts = []
        if table.row_count is not None:
            facts.append(f"~{table.row_count:,} rows")
        if view.table_description(table):
            facts.append(_clip(view.table_description(table), 120))
        lines.append(head + (" -- " + ". ".join(facts) if facts else ""))
        for col, _ in match.columns:
            line = f"  {sql_ident(col.name)} {col.data_type}"
            notes = []
            description = view.column_description(table, col)
            if description:
                notes.append(_clip(description, 100))
            if match.values.get(col.name):
                notes.append("matching stored values: " + ", ".join(
                    "'" + v.replace("'", "''") + "'" for v in match.values[col.name][:3]))
            if notes:
                line += " -- " + "; ".join(notes)
            lines.append(line)
    lines.append("Use describe_tables for full column details and join paths.")
    return "\n".join(lines), {"kind": SEARCH_SCHEMA, "success": True, "method": view.search_method,
                              "tables": [m.table.name for m in results]}


# ──────────────────────────────────────────────────────────────────────────────
# describe_tables
# ──────────────────────────────────────────────────────────────────────────────

def describe_tables(ctx: AgentContext, tables: list[str]) -> tuple[str, dict]:
    view = ctx.schema
    if isinstance(tables, str):
        tables = [t for t in tables.replace(",", " ").split() if t]
    resolved, unknown = [], []
    for name in tables:
        real = view.resolve_table(name)
        if real is None:
            unknown.append(name)
        elif real not in resolved:
            resolved.append(real)
    notes = []
    if len(resolved) > _MAX_DESCRIBE:
        notes.append(f"Only the first {_MAX_DESCRIBE} tables are described.")
        resolved = resolved[:_MAX_DESCRIBE]
    for name in unknown:
        close = difflib.get_close_matches(name.lower(), [t.lower() for t in view.scope], n=3)
        hint = f" Did you mean: {', '.join(view.resolve_table(c) for c in close)}?" if close else ""
        notes.append(f"Unknown table '{name}'.{hint}")

    relations = view.relations()
    blocks, missing = [], []
    for name in resolved:
        table = view.table(name)
        if table is None:
            missing.append(name)
        else:
            blocks.append(render_table(table, relations, view.descriptions, level="detail"))
    if missing:          # not in the profile and not inspectable: basic format
        blocks.append(basic_schema_context(ctx.engine, missing))

    if len(resolved) > 1:
        paths = JoinGraph(relations).describe_paths(resolved)
        blocks.append("JOIN PATHS (foreign keys; [inferred] = found from the data):\n"
                      + "\n".join("  " + p for p in paths))
    content = "\n\n".join(notes + blocks) if blocks else "\n".join(notes) or "No tables given."
    return content, {"kind": DESCRIBE_TABLES, "success": bool(blocks), "tables": resolved}


# ──────────────────────────────────────────────────────────────────────────────
# find_values
# ──────────────────────────────────────────────────────────────────────────────

_NAMEY = ("name", "title", "type", "category", "status", "city", "country", "state", "region",
          "code", "label", "description", "kind", "class", "segment", "gender", "language")


def find_values(ctx: AgentContext, text: str, column: str | None = None) -> tuple[str, dict]:
    needle = (text or "").strip()
    if not needle:
        return "Error: give the value to look for.", {"kind": FIND_VALUES, "success": False}
    view = ctx.schema
    if column:
        targets = view.resolve_column(column)
        if not targets:
            return (f"Error: unknown column '{column}'. Use 'table.column'.",
                    {"kind": FIND_VALUES, "success": False})
    else:
        targets = [(t, c) for t in view.tables() for c in t.columns
                   if type_family(c.data_type) == "text"]

    low = needle.lower()
    found: dict[tuple[str, str], list[str]] = {}

    # 1. Values Postgres statistics already list (no query needed).
    for table, col in targets:
        for value in col.sample_values or []:
            v = value.lower()
            if low in v or difflib.SequenceMatcher(None, low, v).ratio() >= 0.85:
                found.setdefault((table.name, col.name), []).append(value)

    # 2. The retrieval index: every value of low-cardinality text columns (fuzzy match).
    if view.index is not None:
        wanted = {(t.name, c.name) for t, c in targets}
        try:
            indexed = view.index.find_values(needle, sorted({t for t, _ in wanted}))
        except Exception as exc:
            logger.info("Value index lookup failed: %s", exc)
            indexed = []
        for table_name, col_name, value in indexed:
            if (table_name, col_name) in wanted:
                existing = found.setdefault((table_name, col_name), [])
                if value not in existing:
                    existing.append(value)

    # 3. Live search on columns whose values the statistics don't fully cover.
    def complete(col) -> bool:
        return (col.sample_coverage or 0) >= 0.999

    live = [(t, c) for t, c in targets
            if column or not (complete(c) or c.text_format or c.is_primary_key)]
    if not column:
        live.sort(key=lambda tc: (
            not any(w in tc[1].name.lower() for w in _NAMEY),
            tc[0].row_count if tc[0].row_count is not None else 10**12,
        ))
        live = live[:_FIND_VALUES_MAX_COLUMNS]
    searched = []
    for table, col in live:
        values = _ilike(ctx.engine, table.name, col.name, needle)
        searched.append(f"{table.name}.{col.name}")
        if values:
            existing = found.setdefault((table.name, col.name), [])
            existing += [v for v in values if v not in existing]

    if not found:
        where = ", ".join(searched) if searched else "the column statistics"
        return (f"No stored value matches '{needle}' (searched {where}). Try another spelling, "
                "a shorter fragment, or a specific column.",
                {"kind": FIND_VALUES, "success": True, "matches": {}})

    def rank(item):
        values = item[1]
        return (not any(v.lower() == low for v in values), len(values))

    lines = []
    for (table, col), values in sorted(found.items(), key=rank)[:10]:
        values = sorted(values, key=lambda v: (v.lower() != low, len(v)))[:_FIND_VALUES_PER_COLUMN]
        listed = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
        lines.append(f"{sql_ident(table)}.{sql_ident(col)}: {listed}")
    return ("Stored values (use them exactly, they are case-sensitive):\n" + "\n".join(lines),
            {"kind": FIND_VALUES, "success": True,
             "matches": {f"{t}.{c}": v for (t, c), v in found.items()}})


def _ilike(engine: Engine, table: str, column: str, needle: str) -> list[str]:
    pattern = "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    sql = text(
        f"SELECT DISTINCT {quote_ident(column)}::text AS v FROM {quote_ident(table)} "
        f"WHERE {quote_ident(column)}::text ILIKE :pattern LIMIT {_FIND_VALUES_PER_COLUMN}"
    )
    try:
        with sql_slot(engine), engine.begin() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f"SET LOCAL statement_timeout = {_FIND_VALUES_TIMEOUT_MS}"))
            return [r[0] for r in conn.execute(sql, {"pattern": pattern}) if r[0] is not None]
    except Exception as exc:
        logger.info("find_values on %s.%s failed: %s", table, column, exc)
        return []


# ──────────────────────────────────────────────────────────────────────────────
# run_sql / submit_answer
# ──────────────────────────────────────────────────────────────────────────────

def run_sql(ctx: AgentContext, sql: str, purpose: str = "") -> tuple[str, dict]:
    executor = SafeSqlExecutor(ctx.engine, max_rows=ctx.explore_rows,
                               count_limit=_EXPLORE_COUNT_LIMIT, timeout_ms=ctx.sql_timeout_ms)
    with sql_slot(ctx.engine):
        result = executor.run(sql)
    if not result.success:
        return f"Error: {result.error}", {"kind": RUN_SQL, "success": False, "sql": result.sql}
    return result.to_llm_string(), {
        "kind": RUN_SQL, "success": True, "sql": result.sql, "purpose": purpose,
        "columns": result.columns, "rows": result.rows, "row_count": result.total_rows,
    }


def submit_answer(ctx: AgentContext, sql: str, assumptions: str = "", display: str = "auto",
                  x: str = "", y: list[str] | str | None = None,
                  series: str = "") -> tuple[str, dict]:
    executor = SafeSqlExecutor(ctx.engine, max_rows=ctx.answer_rows,
                               count_limit=_ANSWER_COUNT_LIMIT, timeout_ms=ctx.sql_timeout_ms)
    with sql_slot(ctx.engine):
        result = executor.run(sql)
    if not result.success:
        return (f"Error: {result.error}\nFix the query and call submit_answer again.",
                {"kind": SUBMIT_ANSWER, "success": False, "sql": result.sql})
    content = result.to_llm_string(max_rows=ctx.answer_rows_shown)
    shown = describe_result(result.columns, result.rows, truncated=result.truncated,
                            hint=DisplayHint.parse(display, x, y, series))
    if shown["display_note"]:
        content += "\n" + shown["display_note"]
    return content, {
        "kind": SUBMIT_ANSWER, "success": True, "sql": result.sql,
        "columns": result.columns, "rows": result.rows, "truncated": result.truncated,
        "row_count": result.total_rows, "assumptions": (assumptions or "").strip(),
        "column_meta": shown["column_meta"], "views": shown["views"],
    }


_IMPLEMENTATIONS = {
    SEARCH_SCHEMA: search_schema,
    DESCRIBE_TABLES: describe_tables,
    FIND_VALUES: find_values,
    RUN_SQL: run_sql,
    SUBMIT_ANSWER: submit_answer,
}

