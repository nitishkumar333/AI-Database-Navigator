"""
Renders a SchemaProfile (+ table/column descriptions) as the compact schema
text the agent reads. One line per column:

    TABLE yearmonth -- ~383,282 rows. Monthly gas consumption per customer.
      customerid bigint -> customers.customerid (inferred)
      date text -- year+month as text 'YYYYMM'; e.g. '201305', '201307', '201306'
      consumption real -- range ~-1988.63 .. 1.7004801e+06

Descriptions passed in win over database COMMENTs. When the full rendering
exceeds `max_chars`, a compact level drops examples, ranges and long text.
"""
from __future__ import annotations

import re

from app.services.schema_index.profiler import (
    ColumnProfile, RelationProfile, SchemaProfile, TableProfile, type_family,
)

# {table: {"description": str | None, "columns": {column: str}}}
Descriptions = dict[str, dict]

DEFAULT_MAX_CHARS = 60_000      # ~15k tokens
_MAX_CATEGORICAL = 25           # distinct values at or below this are listed
# "detail" is what the agent's describe_tables tool returns for a few tables.
_SHOWN_VALUES = {"detail": 25, "full": 10, "compact": 5}
_EXAMPLES = {"detail": 10, "full": 3}
_SHOWN_CHARS = 40
_DESCRIPTION_CHARS = {"detail": 1000, "full": 300, "compact": 100}

_SIMPLE_IDENT = re.compile(r"^[a-z_][a-z0-9_$]*$")
# PostgreSQL reserved key words (cannot be used unquoted as table/column names).
_RESERVED = frozenset("""
all analyse analyze and any array as asc asymmetric authorization binary both case cast check
collate collation column concurrently constraint create cross current_catalog current_date
current_role current_schema current_time current_timestamp current_user default deferrable desc
distinct do else end except false fetch for foreign freeze from full grant group having ilike in
initially inner intersect into is isnull join lateral leading left like limit localtime
localtimestamp natural not notnull null offset on only or order outer overlaps placing primary
references returning right select session_user similar some symmetric system_user table
tablesample then to trailing true union unique user using variadic verbose when where window with
""".split())

_TYPE_ALIASES = (
    ("character varying", "varchar"),
    ("timestamp without time zone", "timestamp"),
    ("timestamp with time zone", "timestamptz"),
    ("time without time zone", "time"),
    ("time with time zone", "timetz"),
    ("character(", "char("),
)


def sql_ident(name: str) -> str:
    """The identifier as it must be written in SQL (quoted only when needed)."""
    if _SIMPLE_IDENT.match(name) and name not in _RESERVED:
        return name
    return '"' + name.replace('"', '""') + '"'


def _short_type(data_type: str) -> str:
    for long, short in _TYPE_ALIASES:
        data_type = data_type.replace(long, short)
    return data_type


def _clip(value: str, limit: int) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _literal(value: str, family: str, limit: int = _SHOWN_CHARS) -> str:
    if family == "bool":
        return {"t": "true", "f": "false"}.get(value, value)
    if family in ("int", "num"):
        return value
    return "'" + _clip(value, limit).replace("'", "''") + "'"


def _value_notes(col: ColumnProfile, level: str, is_key: bool) -> list[str]:
    family = type_family(col.data_type)
    notes: list[str] = []
    if col.text_format:
        notes.append(col.text_format)
    if col.data_type == "real":
        # SUM(real) is computed in float4 and silently loses digits.
        notes.append("float4: aggregate as col::double precision")

    distinct = col.distinct_count
    values = col.sample_values
    categorical = (
        values and distinct is not None and distinct <= _MAX_CATEGORICAL
        and family in ("text", "int", "num", "bool", "temporal")
        and not (col.is_unique or col.all_distinct)
    )
    if categorical:
        shown = values[: _SHOWN_VALUES[level]]
        # Exact values matter for filters, so they are not shortened further.
        listed = ", ".join(_literal(v, family, limit=10_000) for v in shown)
        if distinct > len(shown):
            notes.append(f"top values: {listed} ({distinct} distinct)")
        else:
            notes.append(f"values: {listed}")
    elif level in _EXAMPLES and values and family == "text":
        notes.append("e.g. " + ", ".join(_literal(v, family) for v in values[:_EXAMPLES[level]]))

    if (level != "compact" and not categorical and not is_key and not (col.is_unique or col.all_distinct)
            and family in ("int", "num", "temporal") and col.min_value and col.max_value):
        notes.append(f"range ~{_clip(col.min_value, 30)} .. {_clip(col.max_value, 30)}")

    if col.null_frac is not None:
        if col.null_frac >= 0.999:
            notes.append("always NULL")
        elif col.null_frac >= 0.05:
            notes.append(f"{round(100 * col.null_frac)}% NULL")
    return notes


def render_table(
    table: TableProfile,
    relations: list[RelationProfile],
    descriptions: Descriptions | None = None,
    *,
    level: str = "full",
) -> str:
    docs = (descriptions or {}).get(table.name) or {}
    column_docs = docs.get("columns") or {}

    header = f"TABLE {sql_ident(table.name)}"
    facts = []
    if table.row_count is not None:
        facts.append("empty" if table.row_count == 0 else f"~{table.row_count:,} rows")
    table_description = docs.get("description") or table.comment
    if table_description:
        facts.append(_clip(table_description, _DESCRIPTION_CHARS[level]))
    if facts:
        header += " -- " + ". ".join(facts)

    single_fks: dict[str, RelationProfile] = {}
    multi_fks: list[RelationProfile] = []
    for rel in relations:
        if rel.from_table != table.name:
            continue
        if len(rel.from_columns) == 1:
            single_fks.setdefault(rel.from_columns[0], rel)
        else:
            multi_fks.append(rel)

    lines = [header]
    for col in table.columns:
        parts = [f"  {sql_ident(col.name)} {_short_type(col.data_type)}"]
        if col.is_primary_key:
            parts.append("PK" if len(table.primary_key) == 1 else "PK*")
        elif not col.nullable:
            parts.append("NOT NULL")
        if col.is_unique and not col.is_primary_key:
            parts.append("UNIQUE")
        fk = single_fks.get(col.name)
        if fk:
            parts.append(f"-> {sql_ident(fk.to_table)}.{sql_ident(fk.to_columns[0])}"
                         + (" (inferred)" if fk.source == "inferred" else ""))
        notes = []
        description = column_docs.get(col.name) or col.comment
        if description:
            notes.append(_clip(description, _DESCRIPTION_CHARS[level]).rstrip(". "))
        notes += _value_notes(col, level, is_key=col.is_primary_key or fk is not None)
        line = " ".join(parts)
        if notes:
            line += " -- " + "; ".join(notes)
        lines.append(line)
    if len(table.primary_key) > 1:
        lines.append(f"  PK* = ({', '.join(sql_ident(c) for c in table.primary_key)})")
    for rel in multi_fks:
        lines.append(
            f"  FK ({', '.join(sql_ident(c) for c in rel.from_columns)}) -> "
            f"{sql_ident(rel.to_table)}({', '.join(sql_ident(c) for c in rel.to_columns)})"
            + (" (inferred)" if rel.source == "inferred" else ""))
    return "\n".join(lines)


def render_schema(
    profile: SchemaProfile,
    tables: list[str],
    descriptions: Descriptions | None = None,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Schema text for `tables` (those missing from the profile are skipped;
    callers render them some other way). Joins are shown only between the
    requested tables."""
    present = [t for t in tables if t in profile.tables]
    relations = profile.relations_for(set(present))
    rendered = ""
    for level in ("full", "compact"):
        rendered = "\n\n".join(
            render_table(profile.tables[t], relations, descriptions, level=level)
            for t in sorted(present)
        )
        if len(rendered) <= max_chars:
            break
    return rendered


DEFAULT_CATALOG_CHARS = 24_000      # ~6k tokens: ~300 tables with descriptions
_CATALOG_DESCRIPTION_CHARS = 100


def render_catalog(
    tables: list[TableProfile | str],
    descriptions: Descriptions | None = None,
    *,
    max_chars: int = DEFAULT_CATALOG_CHARS,
) -> str:
    """The table list the agent keeps in its prompt (columns come from the
    describe_tables tool). One line per table with its row count and a short
    description; plain names, then a cut-off list, when that doesn't fit.

    A str entry is a table without a profile: only its name is shown.
    """
    def row_count(t) -> str:
        if isinstance(t, str) or t.row_count is None:
            return ""
        return " (empty)" if t.row_count == 0 else f" (~{t.row_count:,} rows)"

    def description(t) -> str:
        if isinstance(t, str):
            return ""
        text = ((descriptions or {}).get(t.name) or {}).get("description") or t.comment
        return " -- " + _clip(text, _CATALOG_DESCRIPTION_CHARS) if text else ""

    ordered = sorted(tables, key=lambda t: t if isinstance(t, str) else t.name)
    names = [sql_ident(t if isinstance(t, str) else t.name) for t in ordered]
    full = "\n".join(f"{n}{row_count(t)}{description(t)}" for n, t in zip(names, ordered))
    if len(full) <= max_chars:
        return full
    counts = "\n".join(f"{n}{row_count(t)}" for n, t in zip(names, ordered))
    if len(counts) <= max_chars:
        return counts
    shown, size = [], 0
    for n in names:
        if size + len(n) + 2 > max_chars:
            break
        shown.append(n)
        size += len(n) + 2
    rest = len(names) - len(shown)
    return ", ".join(shown) + (f"\n... and {rest} more tables: use search_schema to find them."
                               if rest else "")
