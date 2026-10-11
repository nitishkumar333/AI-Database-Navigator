"""
Schema-linking analysis: which tables and columns a query actually uses.

sqlglot's qualifier runs against the live BIRD schema, so aliases (T1, T2)
and unqualified columns resolve to real table names. Comparing the gold and
predicted references tells a schema-linking failure (wrong tables/columns)
apart from a SQL-logic failure (right tables, wrong filter/aggregate).

All names are lower-cased on both sides, so `"Academic Year"` and an
unquoted `CDSCode` compare consistently.
"""
import threading
from dataclasses import dataclass

import sqlglot
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope


@dataclass(frozen=True)
class SqlRefs:
    tables: frozenset[str]
    columns: frozenset[str] | None  # "table.column"; None if columns couldn't be resolved


class SchemaLinker:
    def __init__(self, schema: dict[str, dict[str, str]]):
        self.schema = schema
        self._cache: dict[str, SqlRefs | None] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_engine(cls, engine: Engine) -> "SchemaLinker":
        insp = inspect(engine)
        # The qualifier only needs column names; the type is a placeholder.
        return cls({
            table: {col["name"]: "TEXT" for col in insp.get_columns(table)}
            for table in insp.get_table_names()
        })

    def references(self, sql: str | None) -> SqlRefs | None:
        """Tables/columns used by `sql`, or None if it doesn't parse."""
        if not sql or not sql.strip():
            return None
        with self._lock:
            if sql in self._cache:
                return self._cache[sql]
        refs = self._extract(sql)
        with self._lock:
            self._cache[sql] = refs
        return refs

    def _extract(self, sql: str) -> SqlRefs | None:
        try:
            tree = sqlglot.parse_one(sql, read="postgres")
        except Exception:
            return None
        try:
            tree = qualify(tree, schema=self.schema, dialect="postgres",
                           validate_qualify_columns=False)
        except Exception:
            # Unresolvable (e.g. hallucinated) names: keep table-level info only.
            ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
            tables = {t.name.lower() for t in tree.find_all(exp.Table)} - ctes
            return SqlRefs(frozenset(tables), None)

        tables: set[str] = set()
        columns: set[str] = set()
        for scope in traverse_scope(tree):
            for source in scope.sources.values():
                if isinstance(source, exp.Table):
                    tables.add(source.name.lower())
            for col in scope.columns:
                source = scope.sources.get(col.table)
                if isinstance(source, exp.Table):
                    columns.add(f"{source.name.lower()}.{col.name.lower()}")
        return SqlRefs(frozenset(tables), frozenset(columns))

    def analyze(self, gold_sql: str, pred_sql: str | None,
                context_tables: list[str] | None) -> dict:
        """Per-question linking metrics (fractions in [0, 1]; None = not measurable).

        context_recall: share of the gold tables the agent had in its context.
          Trivially 1.0 while the agent gets the whole per-database schema; it
          becomes the key retrieval metric once schema is retrieved.
        table_* / column_*: predicted SQL vs gold SQL.
        """
        gold = self.references(gold_sql)
        pred = self.references(pred_sql)
        out = {
            "gold_tables": sorted(gold.tables) if gold else None,
            "pred_tables": sorted(pred.tables) if pred else None,
            "context_recall": None,
            "table_recall": None,
            "table_precision": None,
            "tables_exact": None,
            "column_recall": None,
            "column_precision": None,
        }
        if gold is None:
            return out
        if context_tables is not None:
            out["context_recall"] = _recall(gold.tables, {t.lower() for t in context_tables})
        if pred is None:
            return out
        out["table_recall"] = _recall(gold.tables, pred.tables)
        out["table_precision"] = _precision(gold.tables, pred.tables)
        out["tables_exact"] = gold.tables == pred.tables
        if gold.columns is not None and pred.columns is not None:
            out["column_recall"] = _recall(gold.columns, pred.columns)
            out["column_precision"] = _precision(gold.columns, pred.columns)
        return out


def _recall(gold: frozenset | set, pred: frozenset | set) -> float:
    return round(len(gold & pred) / len(gold), 4) if gold else 1.0


def _precision(gold: frozenset | set, pred: frozenset | set) -> float:
    if not pred:
        return 1.0 if not gold else 0.0
    return round(len(gold & pred) / len(pred), 4)


def failure_category(rec: dict) -> str | None:
    """Coarse, heuristic reason a question was missed (None if correct/unscorable).

    Checked in order, so each failure gets the earliest matching cause:
      extra_columns     right rows, but extra columns (passes column-tolerant EX)
      wrong_tables      used a different set of tables than gold (schema linking)
      wrong_columns     same tables, but missed a column gold uses
      wrong_projection  same tables/columns, different number of output columns
      wrong_row_count   same shape, different number of rows (filter/join/LIMIT)
      wrong_values      same shape and row count, different values (calc/aggregate/definition)
    Non-wrong_result statuses (no_sql, pred_error, ...) are their own category.
    """
    status = rec.get("status")
    if status in (None, "correct", "gold_error"):
        return None
    if status != "wrong_result":
        return status
    if (rec.get("metrics") or {}).get("ex_column_tolerant"):
        return "extra_columns"
    link = rec.get("linking") or {}
    if link.get("tables_exact") is False:
        return "wrong_tables"
    if link.get("column_recall") is not None and link["column_recall"] < 1:
        return "wrong_columns"
    if len(rec.get("pred_columns") or []) != len(rec.get("gold_columns") or []):
        return "wrong_projection"
    if rec.get("pred_row_count") != rec.get("gold_row_count"):
        return "wrong_row_count"
    return "wrong_values"
