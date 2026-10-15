"""
The documents the schema retrieval index holds, built from a profile and the
table/column descriptions:

- one per table: name, summary, comment, key and main column names;
- one per column: table and column name, type/format, description, comment,
  most common values;
- the distinct values of low-cardinality text columns, so a question that
  names a value ('CZK', 'California') finds its column without naming it.

Each document has two texts: `embed_text`, a sentence-like text for the
embedding model, and `lexical_text`, the identifiers (raw and split into
words), sample values and description key terms that trigram search matches.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.schema_index.profiler import (
    ColumnProfile, SchemaProfile, TableProfile, quote_ident, type_family,
)
from app.services.schema_index.render import Descriptions

logger = logging.getLogger(__name__)

_MAX_TABLE_COLUMNS = 40         # column names listed in a table document
_MAX_DOC_VALUES = 10            # sample values in a column document
MAX_VALUE_CHARS = 200           # longer values aren't indexed (they aren't categories)
_VALUE_FETCH_TIMEOUT_MS = 3_000

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_WORD = re.compile(r"[A-Za-z0-9]+")
# Words that carry no meaning for matching a question to a schema element.
STOPWORDS = frozenset("""
a an and are as at be been by can could did do does for from had has have how i if in into is it
its me my no not of on or our per show shows that the their them then there these this those to
was were what when where which who whom whose why will with would you your all any each every
give find get list many much number numbers total please tell than also only same such more most
""".split())


def split_identifier(name: str) -> str:
    """'cust_seg' -> 'cust seg', 'CustomerID' -> 'customer id'."""
    return " ".join(w.lower() for w in _WORD.findall(_CAMEL.sub(" ", name)))


def key_terms(text_: str | None, limit: int = 30) -> list[str]:
    """Distinct meaningful words of a description, in order."""
    seen: list[str] = []
    for word in _WORD.findall((text_ or "").lower()):
        if len(word) > 2 and word not in STOPWORDS and word not in seen:
            seen.append(word)
            if len(seen) == limit:
                break
    return seen


def _hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]


@dataclass(frozen=True)
class IndexDoc:
    table_name: str
    column_name: str            # "" for the table document
    lexical_text: str
    embed_text: str

    @property
    def kind(self) -> str:
        return "column" if self.column_name else "table"

    @property
    def embed_hash(self) -> str:
        return _hash(self.embed_text)

    @property
    def content_hash(self) -> str:
        return _hash(self.lexical_text, self.embed_text)


def _sentence(*parts: str | None) -> str:
    out = []
    for part in parts:
        part = " ".join((part or "").split()).rstrip(".")
        if part and part not in out:
            out.append(part)
    return ". ".join(out) + ("." if out else "")


def _docs_of(table: TableProfile, descriptions: Descriptions, fk_columns: set[str]) -> list[IndexDoc]:
    docs = (descriptions or {}).get(table.name) or {}
    column_docs = docs.get("columns") or {}
    table_split = split_identifier(table.name)
    summary = docs.get("description")

    # Keys first, then the rest, so a cut list still shows how the table joins.
    keys = [c.name for c in table.columns if c.is_primary_key or c.name in fk_columns]
    others = [c.name for c in table.columns if c.name not in keys]
    listed = (keys + others)[:_MAX_TABLE_COLUMNS]
    out = [IndexDoc(
        table_name=table.name,
        column_name="",
        lexical_text=" ".join(dict.fromkeys(
            [table.name, table_split, *key_terms(summary), *key_terms(table.comment)]
            + [n for c in listed for n in (c, split_identifier(c))])),
        embed_text=_sentence(
            f"Table {table.name} ({table_split})", summary, table.comment,
            "Columns: " + ", ".join(listed)),
    )]

    for col in table.columns:
        out.append(_column_doc(table, table_split, col, column_docs.get(col.name)))
    return out


def _column_doc(table: TableProfile, table_split: str, col: ColumnProfile,
                description: str | None) -> IndexDoc:
    col_split = split_identifier(col.name)
    family = type_family(col.data_type)
    values = [v for v in (col.sample_values or [])[:_MAX_DOC_VALUES] if v]
    kind = col.text_format or col.data_type
    values_text = ("Values: " + ", ".join(values)) if values and family in ("text", "bool") else (
        ("Examples: " + ", ".join(values[:5])) if values else "")
    return IndexDoc(
        table_name=table.name,
        column_name=col.name,
        lexical_text=" ".join(dict.fromkeys(
            [table.name, table_split, col.name, col_split, *key_terms(description),
             *key_terms(col.comment)]
            + (values if family == "text" else []))),
        embed_text=_sentence(
            f"Column {col.name} ({col_split}) of table {table.name} ({table_split})",
            f"Type {kind}", description, col.comment, values_text),
    )


def build_documents(profile: SchemaProfile, descriptions: Descriptions | None,
                    tables: list[str] | None = None) -> list[IndexDoc]:
    """Table and column documents of `tables` (default: every profiled table)."""
    names = [t for t in (tables or sorted(profile.tables)) if t in profile.tables]
    fk_columns: dict[str, set[str]] = {}
    for rel in profile.relations:
        fk_columns.setdefault(rel.from_table, set()).update(rel.from_columns)
        fk_columns.setdefault(rel.to_table, set()).update(rel.to_columns)
    docs: list[IndexDoc] = []
    for name in names:
        docs += _docs_of(profile.tables[name], descriptions or {}, fk_columns.get(name, set()))
    return docs


# ──────────────────────────────────────────────────────────────────────────────
# Values of low-cardinality text columns
# ──────────────────────────────────────────────────────────────────────────────

def value_columns(profile: SchemaProfile, max_distinct: int) -> list[tuple[TableProfile, ColumnProfile]]:
    """Text columns that look categorical: few distinct values, not keys,
    not dates/numbers stored as text. Unique columns of small lookup tables
    (colour.colour = 'Blue', 'Green', ...) count too."""
    out = []
    for table in profile.tables.values():
        for col in table.columns:
            if type_family(col.data_type) != "text" or col.is_primary_key or col.text_format:
                continue
            distinct = col.distinct_count
            if (col.is_unique or col.all_distinct) and table.row_count is not None:
                distinct = max(distinct or 0, table.row_count)
            if distinct is not None and distinct > max_distinct:
                continue
            out.append((table, col))
    return out


def _meaningful(value: str) -> bool:
    """Values made only of stopwords ('The List', 'All') would match the
    wording of almost any question."""
    return bool(key_terms(value, limit=1)) or len(value) <= 4 and value.isupper()


def collect_values(engine: Engine | None, profile: SchemaProfile,
                   max_distinct: int) -> list[tuple[str, str, str]]:
    """(table, column, value) for every value of the categorical text columns.
    Values come from the statistics when they cover the column, otherwise
    from a bounded `SELECT DISTINCT` (skipped if it finds too many or is slow)."""
    rows: list[tuple[str, str, str]] = []
    for table, col in value_columns(profile, max_distinct):
        values = list(col.sample_values or [])
        complete = (col.sample_coverage or 0) >= 0.999
        if not complete and engine is not None:
            fetched = _distinct_values(engine, table.name, col.name, max_distinct)
            if fetched is not None:
                values = fetched
        seen = set()
        for value in values:
            value = (value or "").strip()
            if (value and len(value) <= MAX_VALUE_CHARS and value not in seen
                    and _meaningful(value)):
                seen.add(value)
                rows.append((table.name, col.name, value))
    return rows


def _distinct_values(engine: Engine, table: str, column: str, limit: int) -> list[str] | None:
    sql = (f"SELECT DISTINCT {quote_ident(column)}::text FROM {quote_ident(table)} "
           f"WHERE {quote_ident(column)} IS NOT NULL LIMIT {int(limit) + 1}")
    try:
        with engine.begin() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f"SET LOCAL statement_timeout = {_VALUE_FETCH_TIMEOUT_MS}"))
            values = [r[0] for r in conn.execute(text(sql))]
    except Exception as exc:
        logger.info("Could not read values of %s.%s: %s", table, column, exc)
        return None
    return None if len(values) > limit else values
