"""
The agent's view of a connection's schema: the profile, the table/column
descriptions, and the tables it may use (e.g. a knowledge base's tables).

Tools look tables and columns up here, and search_schema ranks them with a
lexical score over names, descriptions and sample values. Phase 3 replaces
`search` with hybrid (trigram + embedding) retrieval; the interface stays.

Before a connection has been profiled, a minimal profile (names, types and
declared keys only) is read from the database the first time a tool needs it.
"""
from __future__ import annotations

import logging
import re
import threading

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.services.schema_index.profiler import (
    ColumnProfile, RelationProfile, SchemaProfile, TableProfile, type_family,
)
from app.services.schema_index.render import DEFAULT_CATALOG_CHARS, Descriptions, render_catalog

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "has", "have", "how", "in",
    "is", "it", "its", "list", "many", "much", "of", "on", "or", "per", "show", "that",
    "the", "their", "them", "there", "this", "to", "was", "were", "what", "when", "where",
    "which", "who", "whose", "with", "all", "each", "give", "me", "find", "get", "number",
}
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str | None) -> set[str]:
    """Lower-case word stems of an identifier or a sentence."""
    if not text:
        return set()
    words = _WORD.findall(_CAMEL.sub(" ", text).lower())
    return {_stem(w) for w in words if w not in _STOPWORDS and len(w) > 1}


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _match(query: set[str], words: set[str]) -> float:
    """Exact token hits count 1, prefix hits ('seg' ~ 'segment') 0.5."""
    score = 0.0
    for q in query:
        if q in words:
            score += 1
        elif len(q) >= 3 and any(len(w) >= 3 and (w.startswith(q) or q.startswith(w)) for w in words):
            score += 0.5
    return score


class SchemaView:
    def __init__(
        self,
        tables: list[str],
        *,
        profile: SchemaProfile | None = None,
        descriptions: Descriptions | None = None,
        engine: Engine | None = None,
    ):
        self.scope = list(dict.fromkeys(tables))
        self._profile = profile
        self.descriptions = descriptions or {}
        self._engine = engine
        self._fallback: dict[str, TableProfile] | None = None
        self._fallback_relations: list[RelationProfile] = []
        self._lock = threading.Lock()
        self._by_lower = {t.lower(): t for t in self.scope}

    # ── Lookups ──────────────────────────────────────────────────────────────

    def table(self, name: str) -> TableProfile | None:
        name = self.resolve_table(name)
        if name is None:
            return None
        if self._profile and name in self._profile.tables:
            return self._profile.tables[name]
        return self._basic().get(name)

    def resolve_table(self, name: str) -> str | None:
        """The scope table `name` refers to (quotes and case ignored)."""
        name = name.strip().strip('"')
        if "." in name and name.lower() not in self._by_lower:
            name = name.split(".")[-1].strip('"')      # schema-qualified
        return self._by_lower.get(name.lower())

    def resolve_column(self, ref: str) -> list[tuple[TableProfile, ColumnProfile]]:
        """Columns that `ref` ("table.column" or just "column") refers to."""
        ref = ref.strip()
        table_name, _, column_name = ref.rpartition(".")
        column_name = column_name.strip().strip('"').lower()
        tables = [self.table(table_name)] if table_name else [self.table(t) for t in self.scope]
        return [
            (t, c) for t in tables if t is not None
            for c in t.columns if c.name.lower() == column_name
        ]

    def tables(self) -> list[TableProfile]:
        return [t for t in (self.table(name) for name in self.scope) if t is not None]

    def relations(self) -> list[RelationProfile]:
        scope = set(self.scope)
        if self._profile is not None:
            relations = self._profile.relations_for(scope)
        else:
            self._basic()
            relations = self._fallback_relations
        return [r for r in relations if r.from_table in scope and r.to_table in scope]

    def table_description(self, table: TableProfile) -> str | None:
        return (self.descriptions.get(table.name) or {}).get("description") or table.comment

    def column_description(self, table: TableProfile, column: ColumnProfile) -> str | None:
        docs = (self.descriptions.get(table.name) or {}).get("columns") or {}
        return docs.get(column.name) or column.comment

    def catalog(self, max_chars: int = DEFAULT_CATALOG_CHARS) -> str:
        """The table list for the agent's prompt. Uses the profile only, so
        unprofiled tables show as bare names (no catalog queries per table)."""
        profiled = self._profile.tables if self._profile else {}
        return render_catalog([profiled.get(t, t) for t in self.scope], self.descriptions,
                              max_chars=max_chars)

    # ── Search ───────────────────────────────────────────────────────────────

    def search(self, query: str, k: int = 6, columns_per_table: int = 5):
        """[(table, score, [(column, score), ...])] for the best-matching tables."""
        q = tokens(query)
        if not q:
            return []
        ranked = []
        for table in self.tables():
            table_score = (3 * _match(q, tokens(table.name))
                           + _match(q, tokens(self.table_description(table))))
            hits = []
            for col in table.columns:
                score = (3 * _match(q, tokens(col.name))
                         + _match(q, tokens(self.column_description(table, col))))
                if type_family(col.data_type) == "text" and col.sample_values:
                    score += _match(q, tokens(" ".join(col.sample_values)))
                if score:
                    hits.append((col, score))
            hits.sort(key=lambda h: -h[1])
            total = table_score + sum(s for _, s in hits[:3])
            if total:
                ranked.append((table, total, hits[:columns_per_table]))
        ranked.sort(key=lambda r: (-r[1], r[0].name))
        return ranked[:k]

    # ── Minimal profile for connections that aren't profiled yet ─────────────

    def _basic(self) -> dict[str, TableProfile]:
        with self._lock:
            if self._fallback is not None:
                return self._fallback
            missing = [t for t in self.scope
                       if not (self._profile and t in self._profile.tables)]
            self._fallback = {}
            if missing and self._engine is not None:
                self._fallback, self._fallback_relations = _inspect_tables(self._engine, missing)
            return self._fallback


def _inspect_tables(engine: Engine, tables: list[str]):
    insp = inspect(engine)
    profiles: dict[str, TableProfile] = {}
    relations: list[RelationProfile] = []
    for name in tables:
        try:
            pk = (insp.get_pk_constraint(name) or {}).get("constrained_columns") or []
            columns = [
                ColumnProfile(name=c["name"], data_type=str(c["type"]).lower(),
                              nullable=bool(c.get("nullable", True)),
                              is_primary_key=c["name"] in pk, comment=c.get("comment"))
                for c in insp.get_columns(name)
            ]
            for fk in insp.get_foreign_keys(name):
                relations.append(RelationProfile(name, fk["constrained_columns"],
                                                 fk["referred_table"], fk["referred_columns"],
                                                 "declared"))
        except Exception as exc:
            logger.warning("Could not inspect table %s: %s", name, exc)
            continue
        profiles[name] = TableProfile(name=name, kind="table", row_count=None, comment=None,
                                      primary_key=pk, columns=columns, structure_hash="")
    return profiles, relations
