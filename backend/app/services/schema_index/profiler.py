"""
Schema profiler: everything the agent should know about a database that a
bare column list doesn't say.

Almost all of it comes from the catalogs, so profiling is cheap even on
large databases:

- pg_class / pg_attribute / pg_constraint: tables, columns, types, keys,
  row-count estimates, and COMMENTs.
- pg_stats: null fraction, distinct count, most common values and histogram
  bounds, which Postgres keeps up to date via (auto)ANALYZE. No table scans.

Only two things touch table data, and both are bounded:

- tables with no statistics yet get a `LIMIT n` sample;
- inferred foreign keys (common when the schema doesn't declare them) are
  confirmed with a containment check on the first rows of the source table.

Every query runs in a READ ONLY transaction with a statement timeout.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.agent.guardrails import is_credential_column

logger = logging.getLogger(__name__)

CATALOG_TIMEOUT_MS = 15_000
SAMPLE_TIMEOUT_MS = 5_000
INFERENCE_TIMEOUT_MS = 3_000
SAMPLE_ROWS = 500
MAX_SAMPLE_VALUES = 10
MAX_VALUE_CHARS = 60
MAX_INFERENCE_CHECKS = 150
INFERENCE_PROBE_ROWS = 1_000
INFERENCE_MIN_MATCH = 0.95

# Primary-key names too generic to match on name alone (`id` = `id` says nothing).
_GENERIC_KEYS = {"id", "code", "key", "name", "uuid", "pk"}


# ──────────────────────────────────────────────────────────────────────────────
# Profile model (plain dataclasses, JSON round-trippable)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ColumnProfile:
    name: str
    data_type: str
    nullable: bool
    is_primary_key: bool = False
    comment: str | None = None
    null_frac: float | None = None
    distinct_count: int | None = None      # estimated
    is_unique: bool = False                # declared UNIQUE constraint
    all_distinct: bool = False             # observed: no repeated values (statistics/sample)
    sample_values: list[str] = field(default_factory=list)   # most common first
    sample_coverage: float | None = None   # share of rows holding one of sample_values
    min_value: str | None = None           # approximate (from statistics)
    max_value: str | None = None
    text_format: str | None = None         # e.g. "YYYYMM text" for text-encoded data


@dataclass
class TableProfile:
    name: str
    kind: str                              # "table" | "partitioned table"
    row_count: int | None
    comment: str | None
    primary_key: list[str]
    columns: list[ColumnProfile]
    structure_hash: str                    # changes when columns/types/keys change
    stats_source: str = "none"             # "pg_stats" | "sample" | "none"

    def column(self, name: str) -> ColumnProfile | None:
        return next((c for c in self.columns if c.name == name), None)

    def hide_credential_values(self) -> None:
        """Drops stored values of credential columns (passwords, tokens, keys):
        they would otherwise reach the prompt and the search index as examples."""
        for col in self.columns:
            if is_credential_column(col.name):
                col.sample_values, col.sample_coverage = [], None
                col.min_value = col.max_value = col.text_format = None


@dataclass
class RelationProfile:
    from_table: str
    from_columns: list[str]
    to_table: str
    to_columns: list[str]
    source: str                            # "declared" | "inferred"
    confidence: float = 1.0


@dataclass
class SchemaProfile:
    tables: dict[str, TableProfile]
    relations: list[RelationProfile]
    schema_hash: str
    profiled_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SchemaProfile":
        # Unknown keys are ignored so profiles stored by other versions still load.
        tables = {
            name: _build(TableProfile, {**t, "columns": [_build(ColumnProfile, c) for c in t["columns"]]})
            for name, t in data.get("tables", {}).items()
        }
        for table in tables.values():       # profiles stored before credentials were hidden
            table.hide_credential_values()
        return cls(
            tables=tables,
            relations=[_build(RelationProfile, r) for r in data.get("relations", [])],
            schema_hash=data.get("schema_hash", ""),
            profiled_at=data.get("profiled_at", ""),
        )

    def relations_for(self, tables: set[str]) -> list[RelationProfile]:
        return [r for r in self.relations if r.from_table in tables and r.to_table in tables]


def _build(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


# ──────────────────────────────────────────────────────────────────────────────
# Catalog queries (current schema only, matching inspector.get_table_names())
# ──────────────────────────────────────────────────────────────────────────────

_Q_TABLES = """
SELECT c.relname AS table_name, c.relkind, c.reltuples::bigint AS reltuples,
       obj_description(c.oid, 'pg_class') AS comment
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p') AND NOT c.relispartition
"""

_Q_COLUMNS = """
SELECT c.relname AS table_name, a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS data_type,
       NOT a.attnotnull AS nullable,
       col_description(a.attrelid, a.attnum) AS comment
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p') AND NOT c.relispartition
  AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname, a.attnum
"""

_Q_CONSTRAINTS = """
SELECT con.contype, cl.relname AS table_name, fcl.relname AS ref_table,
       array_agg(a.attname ORDER BY k.ord) AS columns,
       array_agg(fa.attname ORDER BY k.ord) AS ref_columns
FROM pg_constraint con
JOIN pg_class cl ON cl.oid = con.conrelid
JOIN pg_namespace n ON n.oid = cl.relnamespace
CROSS JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
LEFT JOIN pg_class fcl ON fcl.oid = con.confrelid
LEFT JOIN pg_attribute fa ON fa.attrelid = con.confrelid AND fa.attnum = con.confkey[k.ord]
WHERE n.nspname = current_schema() AND con.contype IN ('p', 'f', 'u')
GROUP BY con.oid, con.contype, cl.relname, fcl.relname
"""

# Partitioned tables keep their statistics on the parent with inherited = true.
_Q_STATS = """
SELECT DISTINCT ON (tablename, attname)
       tablename, attname, null_frac, n_distinct,
       most_common_vals::text AS mcv, most_common_freqs AS mcf,
       histogram_bounds::text AS hist
FROM pg_stats
WHERE schemaname = current_schema()
ORDER BY tablename, attname, inherited DESC
"""


def _query(engine: Engine, sql: str, timeout_ms: int) -> list:
    with engine.begin() as conn:
        conn.execute(text(f"SET TRANSACTION READ ONLY; SET LOCAL statement_timeout = {int(timeout_ms)}"))
        # Escape colons so identifiers like "a:b" aren't read as bind params.
        return conn.execute(text(sql.replace(":", r"\:"))).mappings().all()


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


# ──────────────────────────────────────────────────────────────────────────────
# Fingerprint (cheap staleness check)
# ──────────────────────────────────────────────────────────────────────────────

def _structure_hashes(columns: list, constraints: list) -> dict[str, str]:
    parts: dict[str, list[str]] = {}
    for row in columns:
        parts.setdefault(row["table_name"], []).append(
            f"{row['column_name']}:{row['data_type']}:{row['nullable']}")
    for row in constraints:
        if row["table_name"] in parts:
            parts[row["table_name"]].append(
                f"{row['contype']}:{','.join(row['columns'])}>{row['ref_table'] or ''}")
    return {t: hashlib.md5("|".join(sorted(p)).encode()).hexdigest() for t, p in parts.items()}


def _schema_hash(table_hashes: dict[str, str]) -> str:
    joined = "|".join(f"{t}={h}" for t, h in sorted(table_hashes.items()))
    return hashlib.md5(joined.encode()).hexdigest()


def schema_fingerprint(engine: Engine) -> tuple[str, dict[str, str]]:
    """(schema hash, per-table structure hashes). Two catalog queries."""
    columns = _query(engine, _Q_COLUMNS, CATALOG_TIMEOUT_MS)
    constraints = _query(engine, _Q_CONSTRAINTS, CATALOG_TIMEOUT_MS)
    hashes = _structure_hashes(columns, constraints)
    return _schema_hash(hashes), hashes


# ──────────────────────────────────────────────────────────────────────────────
# Value helpers
# ──────────────────────────────────────────────────────────────────────────────

def parse_pg_array(literal: str | None) -> list[str | None] | None:
    """Parse a 1-D Postgres array literal ('{a,"b c",NULL}'). None if not 1-D."""
    if not literal or literal[0] != "{" or literal[-1] != "}":
        return None
    body = literal[1:-1]
    if not body:
        return []
    if body.startswith("{"):
        return None
    out: list[str | None] = []
    i, n = 0, len(body)
    while i < n:
        if body[i] == '"':
            i += 1
            buf = []
            while i < n and body[i] != '"':
                if body[i] == "\\" and i + 1 < n:
                    i += 1
                buf.append(body[i])
                i += 1
            i += 1
            out.append("".join(buf))
        else:
            j = body.find(",", i)
            j = n if j == -1 else j
            token = body[i:j]
            out.append(None if token == "NULL" else token)
            i = j
        if i < n and body[i] == ",":
            i += 1
    return out


def _to_str(value: Any) -> str | None:
    if value is None or isinstance(value, (bytes, bytearray, memoryview)):
        return None
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _clip(value: str) -> str:
    return value if len(value) <= MAX_VALUE_CHARS else value[: MAX_VALUE_CHARS - 1] + "…"


def type_family(data_type: str) -> str:
    t = data_type.lower()
    if t in ("smallint", "integer", "bigint"):
        return "int"
    if t.startswith(("numeric", "decimal")) or t in ("real", "double precision", "money"):
        return "num"
    if t.startswith(("text", "character", "varchar", "char", "citext", '"char"')):
        return "text"
    if t == "uuid":
        return "uuid"
    if t.startswith(("date", "timestamp", "time", "interval")):
        return "temporal"
    if t == "boolean":
        return "bool"
    return "other"


# Ordered: the first format that fits >= 90% of the sampled values wins.
_TEXT_FORMATS = (
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "date as text 'YYYY-MM-DD'"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}(:?\d{2})?|Z)?$"),
     "timestamp as text 'YYYY-MM-DD HH:MM:SS'"),
    (re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])$"), "year+month as text 'YYYYMM'"),
    (re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$"), "date as text 'YYYYMMDD'"),
    (re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$"), "date as text 'MM/DD/YYYY' or 'DD/MM/YYYY'"),
    (re.compile(r"^\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?$"), "time/duration as text 'MM:SS' or 'HH:MM:SS'"),
    (re.compile(r"^(19|20)\d{2}$"), "year as text 'YYYY'"),
    (re.compile(r"^-?\d+$"), "integer stored as text"),
    (re.compile(r"^-?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$"), "number stored as text"),
)
_BOOL_WORDS = {"t", "f", "true", "false", "y", "n", "yes", "no", "0", "1"}
_LEADING_ZERO = re.compile(r"^-?0\d")


def detect_text_format(values: list[str]) -> str | None:
    values = [v.strip() for v in values if v is not None and v.strip()]
    if len(values) < 2:
        return None
    lowered = {v.lower() for v in values}
    if len(lowered) <= 2 and lowered <= _BOOL_WORDS and not lowered <= {"0", "1"}:
        return "boolean-like text"
    if len(values) < 3:
        return None
    for pattern, label in _TEXT_FORMATS:
        if sum(bool(pattern.match(v)) for v in values) >= 0.9 * len(values):
            if label == "integer stored as text" and any(_LEADING_ZERO.match(v) for v in values):
                # Codes like '01100170109835': casting would drop the zeros.
                return "digit code as text with leading zeros (compare as text)"
            return label
    return None


def _numeric_bounds(values: list[str]) -> tuple[str, str] | None:
    try:
        nums = sorted((float(v), v) for v in values)
    except (TypeError, ValueError):
        return None
    return (nums[0][1], nums[-1][1]) if nums else None


# ──────────────────────────────────────────────────────────────────────────────
# Profiling
# ──────────────────────────────────────────────────────────────────────────────

def _apply_stats(col: ColumnProfile, stat: dict, row_count: int | None) -> None:
    col.null_frac = round(float(stat["null_frac"]), 4) if stat["null_frac"] is not None else None
    n_distinct = stat["n_distinct"]
    if n_distinct is not None:
        if n_distinct >= 0:
            col.distinct_count = int(n_distinct)
        elif row_count:
            col.distinct_count = max(1, round(-float(n_distinct) * row_count))
        col.all_distinct = float(n_distinct) <= -0.999
    family = type_family(col.data_type)
    mcv = [v for v in (parse_pg_array(stat["mcv"]) or []) if v is not None]
    if family != "other" or col.data_type.startswith("json"):
        col.sample_values = [_clip(v) for v in mcv[:MAX_SAMPLE_VALUES]]
    if stat["mcf"] and mcv:
        col.sample_coverage = round(float(sum(stat["mcf"][: MAX_SAMPLE_VALUES])), 4)
    hist = [v for v in (parse_pg_array(stat["hist"]) or []) if v is not None]
    if hist:
        col.min_value, col.max_value = _clip(hist[0]), _clip(hist[-1])
        if not col.sample_values and family == "text":
            # High-cardinality text: histogram bounds are real values too.
            step = max(1, len(hist) // 3)
            col.sample_values = [_clip(v) for v in hist[::step][:3]]
    elif mcv and col.sample_coverage and col.sample_coverage > 0.99:
        # Every value is a "most common" one, so their bounds are the real range.
        if family in ("int", "num"):
            bounds = _numeric_bounds(mcv)
            if bounds:
                col.min_value, col.max_value = bounds
        elif family == "temporal":
            col.min_value, col.max_value = min(mcv), max(mcv)   # ISO text sorts correctly
    if family == "text":
        col.text_format = detect_text_format(mcv or hist)


def _apply_sample(engine: Engine, table: TableProfile) -> None:
    """Fallback for tables without statistics: profile the first SAMPLE_ROWS rows."""
    try:
        rows = _query(engine, f"SELECT * FROM {quote_ident(table.name)} LIMIT {SAMPLE_ROWS}",
                      SAMPLE_TIMEOUT_MS)
    except Exception as exc:
        logger.info("Could not sample %s: %s", table.name, exc)
        return
    complete = len(rows) < SAMPLE_ROWS
    if complete:
        table.row_count = len(rows)
    for col in table.columns:
        raw = [r[col.name] for r in rows]
        if not raw:
            continue
        values = [s for s in (_to_str(v) for v in raw) if s is not None]
        col.null_frac = round(sum(v is None for v in raw) / len(raw), 4)
        counts = Counter(values)
        if complete:
            col.distinct_count = len(counts)
            col.all_distinct = len(counts) == len(values) and len(values) > 1
        family = type_family(col.data_type)
        if family != "other" or col.data_type.startswith("json"):
            col.sample_values = [_clip(v) for v, _ in counts.most_common(MAX_SAMPLE_VALUES)]
            covered = sum(n for _, n in counts.most_common(MAX_SAMPLE_VALUES))
            col.sample_coverage = round(covered / len(raw), 4)
        if family in ("int", "num"):
            bounds = _numeric_bounds(values)
            if bounds:
                col.min_value, col.max_value = bounds
        elif family == "temporal" and values:
            col.min_value, col.max_value = min(values), max(values)
        elif family == "text":
            col.text_format = detect_text_format(values[:200])
    table.stats_source = "sample"


def _exact_count(engine: Engine, table: str) -> int | None:
    try:
        return int(_query(engine, f"SELECT count(*) AS n FROM {quote_ident(table)}",
                          SAMPLE_TIMEOUT_MS)[0]["n"])
    except Exception:
        return None


def _singular(name: str) -> str:
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith(("ses", "xes")):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def _candidate_fk_names(target_table: str, pk: str) -> set[str]:
    pk_l = pk.lower()
    if pk_l not in _GENERIC_KEYS:
        return {pk_l}
    names = set()
    for t in {target_table.lower(), _singular(target_table.lower())}:
        names |= {f"{t}_{pk_l}", f"{t}{pk_l}"}
    return names


def _infer_relations(engine: Engine, tables: dict[str, TableProfile],
                     declared: list[RelationProfile]) -> list[RelationProfile]:
    """Name-matched foreign keys that the schema doesn't declare, kept only if
    >= 95% of the probed source values exist in the target key."""
    covered = {(r.from_table, c) for r in declared for c in r.from_columns}
    targets = [
        (t, t.primary_key[0]) for t in tables.values()
        if len(t.primary_key) == 1 and t.column(t.primary_key[0])
    ]
    candidates = []
    for source in tables.values():
        for col in source.columns:
            if (source.name, col.name) in covered:
                continue
            if source.primary_key == [col.name]:
                continue   # 1:1 links are too ambiguous to infer by name
            for target, pk in targets:
                if target.name == source.name or col.name.lower() not in _candidate_fk_names(target.name, pk):
                    continue
                target_family = type_family(target.column(pk).data_type)
                if target_family not in ("int", "text", "uuid") or type_family(col.data_type) != target_family:
                    continue
                candidates.append((source, col.name, target, pk))

    if len(candidates) > MAX_INFERENCE_CHECKS:
        logger.info("Checking %d of %d inferred-FK candidates", MAX_INFERENCE_CHECKS, len(candidates))
    inferred = []
    for source, col, target, pk in candidates[:MAX_INFERENCE_CHECKS]:
        sql = (
            "SELECT count(DISTINCT s.v) AS n, "
            f"count(DISTINCT s.v) FILTER (WHERE EXISTS (SELECT 1 FROM {quote_ident(target.name)} t "
            f"WHERE t.{quote_ident(pk)} = s.v)) AS matched "
            f"FROM (SELECT {quote_ident(col)} AS v FROM {quote_ident(source.name)} "
            f"WHERE {quote_ident(col)} IS NOT NULL LIMIT {INFERENCE_PROBE_ROWS}) s"
        )
        try:
            row = _query(engine, sql, INFERENCE_TIMEOUT_MS)[0]
        except Exception as exc:
            logger.debug("FK probe %s.%s -> %s failed: %s", source.name, col, target.name, exc)
            continue
        if row["n"] and row["matched"] / row["n"] >= INFERENCE_MIN_MATCH:
            inferred.append(RelationProfile(
                source.name, [col], target.name, [pk], "inferred",
                round(row["matched"] / row["n"], 3)))
    return inferred


def profile_database(engine: Engine, *, infer_relations: bool = True) -> SchemaProfile:
    """Profile every table in the connection's current schema."""
    table_rows = _query(engine, _Q_TABLES, CATALOG_TIMEOUT_MS)
    column_rows = _query(engine, _Q_COLUMNS, CATALOG_TIMEOUT_MS)
    constraint_rows = _query(engine, _Q_CONSTRAINTS, CATALOG_TIMEOUT_MS)
    try:
        stat_rows = _query(engine, _Q_STATS, CATALOG_TIMEOUT_MS)
    except Exception as exc:   # e.g. a column type whose stats can't be cast to text
        logger.warning("pg_stats unavailable, falling back to sampling: %s", exc)
        stat_rows = []

    hashes = _structure_hashes(column_rows, constraint_rows)
    pks = {r["table_name"]: list(r["columns"]) for r in constraint_rows if r["contype"] == "p"}
    tables: dict[str, TableProfile] = {}
    for row in table_rows:
        name = row["table_name"]
        tables[name] = TableProfile(
            name=name,
            kind="partitioned table" if row["relkind"] == "p" else "table",
            row_count=int(row["reltuples"]) if row["reltuples"] is not None and row["reltuples"] >= 0 else None,
            comment=row["comment"],
            primary_key=pks.get(name, []),
            columns=[],
            structure_hash=hashes.get(name, ""),
        )
    for row in column_rows:
        table = tables.get(row["table_name"])
        if table is not None:
            table.columns.append(ColumnProfile(
                name=row["column_name"],
                data_type=row["data_type"],
                nullable=bool(row["nullable"]),
                is_primary_key=row["column_name"] in table.primary_key,
                comment=row["comment"],
            ))
    for row in constraint_rows:
        table = tables.get(row["table_name"])
        if table is not None and row["contype"] == "u" and len(row["columns"]) == 1:
            col = table.column(row["columns"][0])
            if col:
                col.is_unique = True

    stats: dict[str, dict[str, dict]] = {}
    for row in stat_rows:
        stats.setdefault(row["tablename"], {})[row["attname"]] = row
    for table in tables.values():
        table_stats = stats.get(table.name)
        if table_stats:
            for col in table.columns:
                if col.name in table_stats:
                    _apply_stats(col, table_stats[col.name], table.row_count)
            table.stats_source = "pg_stats"
        else:
            _apply_sample(engine, table)
        table.hide_credential_values()
        if table.row_count is None:
            table.row_count = _exact_count(engine, table.name)

    declared = [
        RelationProfile(r["table_name"], list(r["columns"]), r["ref_table"],
                        list(r["ref_columns"]), "declared")
        for r in constraint_rows
        if r["contype"] == "f" and r["table_name"] in tables and r["ref_table"] in tables
    ]
    relations = declared + (_infer_relations(engine, tables, declared) if infer_relations else [])

    return SchemaProfile(
        tables=tables,
        relations=relations,
        schema_hash=_schema_hash(hashes),
        profiled_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
