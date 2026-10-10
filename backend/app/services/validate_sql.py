from __future__ import annotations
 
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlglot import exp
from sqlglot.errors import SqlglotError
from app.utils.db_manager import refine_sql_from_markdown
import sqlglot

# --------------------------------------------------------------------------- #
# Policy
# --------------------------------------------------------------------------- #
 
# The only statement shapes allowed at the root of the parsed query.
# (WITH ... SELECT parses as a Select, so CTEs are covered.)
_ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)
 
# Node types that must not appear anywhere in the tree. This catches
# data-modifying CTEs (WITH d AS (DELETE ... RETURNING *) SELECT ...),
# SELECT ... INTO, and SELECT ... FOR UPDATE. Names are resolved with getattr
# because some of them differ between sqlglot versions.
_FORBIDDEN_NODES = tuple(
    getattr(exp, name)
    for name in (
        "Insert", "Update", "Delete", "Merge",
        "Create", "Drop", "Alter", "AlterTable", "TruncateTable",
        "Command", "Copy", "Set",
        "Into", "Lock",
    )
    if hasattr(exp, name)
)
 
# Functions that can sleep, touch the filesystem, run arbitrary SQL, or
# change server/session state.
_FORBIDDEN_FUNCTIONS = {
    "pg_sleep", "pg_sleep_for", "pg_sleep_until",
    "set_config", "nextval", "setval",
    "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf",
}
_FORBIDDEN_FUNCTION_PREFIXES = (
    "pg_read_", "pg_ls_", "pg_advisory_", "lo_", "dblink", "query_to_",
)
 
def _raw_sql(sql: str):
    """Wrap generated SQL for execution without bind-parameter parsing.

    text() treats ':name' as a bind parameter even inside string literals
    (e.g. LIKE '_:%:__.___'), which fails with "A value is required for bind
    parameter". Escaping every colon keeps literals and '::' casts intact.
    """
    return text(sql.replace(":", r"\:"))


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
 
@dataclass
class ValidationResult:
    sql: str                                  # cleaned SQL (markdown fences removed)
    is_valid: bool
    reason: str
    validation_query: Optional[str] = None    # the EXPLAIN statement, if reached
 
 
@dataclass
class QueryResult:
    sql: str
    success: bool
    columns: List[str] = field(default_factory=list)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    truncated: bool = False
    error: Optional[str] = None
 
    def to_llm_string(self) -> str:
        """Compact JSON the agent can read. Handles Decimal/datetime/UUID etc."""
        payload: Dict[str, Any] = {
            "columns": self.columns,
            "row_count": len(self.rows),
            "rows": self.rows,
        }
        if self.truncated:
            payload["note"] = (
                f"Only the first {len(self.rows)} rows are shown; the full "
                "result has more."
            )
        return json.dumps(payload, default=str, ensure_ascii=False)
 
 
# --------------------------------------------------------------------------- #
# Validator / executor
# --------------------------------------------------------------------------- #

class SafeSqlExecutor:
    """
    Validates and runs LLM-generated, read-only PostgreSQL queries.
 
    Layers of defence:
      1. AST check (sqlglot): exactly one statement, SELECT-like root, no
         forbidden nodes, no forbidden functions.
      2. EXPLAIN against the real database to catch bad tables/columns.
      3. Every database call runs in a READ ONLY transaction with a statement
         timeout, so a parser mistake in (1) still can't write anything.
 
    For production, also connect with a database role that only has SELECT.
    """

    def __init__(self, engine: Engine, *, max_rows: int = 50, timeout_ms: int = 10_000):
        self.engine = engine
        self.max_rows = max_rows
        self.timeout_ms = timeout_ms
    
    def validate(self, sql_query: str) -> ValidationResult:
        sql = refine_sql_from_markdown(sql_query).strip().rstrip(";").strip()
 
        error = self._check_structure(sql)
        if error:
            return ValidationResult(sql, False, error)
 
        validation_query = f"EXPLAIN {sql}"
        error = self._check_against_schema(validation_query)
        if error:
            return ValidationResult(sql, False, error, validation_query)
 
        return ValidationResult(sql, True, "Query is safe to execute", validation_query)

    def run(self, sql_query: str) -> QueryResult:
        """Validate, then execute. Never raises for bad SQL; check `.success`."""
        validation = self.validate(sql_query)
        if not validation.is_valid:
            return QueryResult(sql=validation.sql, success=False, error=validation.reason)
        return self._execute(validation.sql)

    @staticmethod
    def _check_structure(sql: str) -> Optional[str]:
        """Return an error message, or None if the query passes."""
        if not sql:
            return "Empty SQL query."
 
        try:
            statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
        except SqlglotError as exc:
            return f"Could not parse SQL: {exc}"
 
        if not statements:
            return "Empty or invalid SQL query."
        if len(statements) > 1:
            return "Only a single SQL statement is allowed."
 
        tree = statements[0]
 
        if not isinstance(tree, _ALLOWED_ROOTS):
            return (
                f"Statement type '{type(tree).__name__.upper()}' is not allowed. "
                "Only SELECT queries are permitted."
            )
 
        forbidden = tree.find(*_FORBIDDEN_NODES)
        if forbidden is not None:
            return (
                f"'{type(forbidden).__name__.upper()}' is not allowed. "
                "The query may modify data or take locks."
            )
 
        for func in tree.find_all(exp.Func):
            name = (func.name if isinstance(func, exp.Anonymous) else func.sql_name()).lower()
            if name in _FORBIDDEN_FUNCTIONS or name.startswith(_FORBIDDEN_FUNCTION_PREFIXES):
                return f"Function '{name}' is not allowed."
 
        return None

    def _check_against_schema(self, validation_query: str) -> Optional[str]:
        try:
            with self._read_only_connection() as conn:
                conn.execute(_raw_sql(validation_query))
        except Exception as exc:
            return f"Schema validation failed: {self._clean_error(exc)}"
        return None

    def _execute(self, sql: str) -> QueryResult:
        try:
            with self._read_only_connection() as conn:
                cursor = conn.execute(_raw_sql(sql))
                columns = list(cursor.keys())
                fetched = cursor.fetchmany(self.max_rows + 1)
        except Exception as exc:
            return QueryResult(sql=sql, success=False, error=self._clean_error(exc))
 
        truncated = len(fetched) > self.max_rows
        rows = [dict(zip(columns, row)) for row in fetched[: self.max_rows]]
        return QueryResult(sql=sql, success=True, columns=columns, rows=rows, truncated=truncated)
    
    @contextmanager
    def _read_only_connection(self) -> Iterator[Connection]:
        """One transaction, read-only, with a statement timeout."""
        with self.engine.begin() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f"SET LOCAL statement_timeout = {int(self.timeout_ms)}"))
            yield conn

    @staticmethod
    def _clean_error(exc: Exception) -> str:
        """Prefer the short driver message over SQLAlchemy's long wrapper."""
        return str(getattr(exc, "orig", exc)).strip()