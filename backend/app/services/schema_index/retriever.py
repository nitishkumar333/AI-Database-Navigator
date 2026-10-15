"""
The agent's view of a connection's schema: the profile, the table/column
descriptions, and the tables it may use (e.g. a knowledge base's tables).

Tools look tables and columns up here. `search` ranks tables and columns for
a question: with the connection's retrieval index (indexer.HybridIndex:
embeddings + trigrams + stored values, fused with RRF) when it has been built,
otherwise with a keyword score over names, descriptions and sample values.
`link` picks the tables a question most likely needs, adds the tables they
reference and the bridge tables that join them, and renders them for the
agent's prompt.

Before a connection has been profiled, a minimal profile (names, types and
declared keys only) is read from the database the first time a tool needs it.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.services.schema_index.profiler import (
    ColumnProfile, RelationProfile, SchemaProfile, TableProfile, type_family,
)
from app.services.schema_index.index_store import RRF_K, DocHit
from app.services.schema_index.join_graph import JoinGraph
from app.services.schema_index.render import (
    DEFAULT_CATALOG_CHARS, Descriptions, render_catalog, render_table, sql_ident,
)

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


@dataclass
class TableMatch:
    table: TableProfile
    score: float
    columns: list[tuple[ColumnProfile, float]] = field(default_factory=list)
    values: dict[str, list[str]] = field(default_factory=dict)   # column -> stored values mentioned


@dataclass
class LinkResult:
    text: str                   # schema text for the prompt
    tables: list[str]           # retrieved tables (best first), then the tables they reference
    bridges: list[str]          # tables added to join them
    method: str                 # "hybrid" | "trigram" | "keyword"
    carried: list[str] = field(default_factory=list)  # kept from the conversation, rendered first

    @property
    def all_tables(self) -> list[str]:
        return self.carried + self.tables + self.bridges


_LINK_MIN_SHARE = 0.3           # tables scoring below this share of the best one are left out ...
_LINK_STRONG_SHARE = 0.6        # ... and those below this one must join the tables already picked
_LINK_JOIN_HOPS = 2
_LINK_MAX_BRIDGES = 3
# The tables the top retrieved tables reference (lookups such as a status or
# a category, the parent of a detail table) are linked too: on BIRD this took
# questions with every gold table linked from 93.4% to 96.9% (350 held-out
# questions, one 75-table catalog) for ~5% more prompt text.
_LINK_PARENTS_OF = 2
_LINK_MAX_PARENTS = 3
_LINK_MAX_CARRIED = 4


def _coherent(matches: list[TableMatch], graph: JoinGraph, max_tables: int) -> list[TableMatch]:
    """The tables to link, best first. A question is usually about one
    connected group of tables, so candidates are grouped by foreign-key
    distance and the group with the most evidence wins; it beats taking the
    single best table and its neighbours when that table is a false hit.
    Tables of other groups are kept only when they score nearly as high as
    the best table. A table holding a value the question mentions is kept
    when it joins the chosen tables at all (value boost)."""
    best = matches[0].score
    candidates = [m for m in matches if m.score >= _LINK_MIN_SHARE * best]

    # Union-find over candidates joined within _LINK_JOIN_HOPS foreign keys.
    parent = list(range(len(candidates)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(candidates):
        for j in range(i):
            if root(i) != root(j) and graph.shortest_path(
                    a.table.name, candidates[j].table.name, _LINK_JOIN_HOPS) is not None:
                parent[root(i)] = root(j)
    groups: dict[int, list[TableMatch]] = {}
    for i, m in enumerate(candidates):
        groups.setdefault(root(i), []).append(m)

    def evidence(group: list[TableMatch]) -> float:
        return sum(m.score for m in group[:4])

    winner = max(groups.values(), key=evidence)
    chosen = winner[:max_tables]
    for m in candidates:
        if len(chosen) >= max_tables:
            break
        if m not in chosen and m.score >= _LINK_STRONG_SHARE * best:
            chosen.append(m)

    def joins(match: TableMatch) -> bool:
        return any(graph.shortest_path(match.table.name, c.table.name, 4) is not None
                   for c in chosen)

    for m in matches:                  # value boost
        if len(chosen) >= max_tables:
            break
        if m.values and m not in chosen and joins(m):
            chosen.append(m)
    return sorted(chosen, key=lambda m: -m.score)


def _parents(chosen: list[TableMatch], matches: list[TableMatch], relations) -> list[str]:
    """Tables the top chosen tables reference by foreign key, best-scoring first."""
    names = {m.table.name for m in chosen}
    top = {m.table.name for m in chosen[:_LINK_PARENTS_OF]}
    score = {m.table.name: m.score for m in matches}
    parents = {r.to_table for r in relations
               if r.from_table in top and r.to_table not in names}
    return sorted(parents, key=lambda t: (-score.get(t, 0.0), t))[:_LINK_MAX_PARENTS]


class SchemaView:
    def __init__(
        self,
        tables: list[str],
        *,
        profile: SchemaProfile | None = None,
        descriptions: Descriptions | None = None,
        engine: Engine | None = None,
        index=None,
    ):
        """`index` is the connection's indexer.HybridIndex, if it has one."""
        self.scope = list(dict.fromkeys(tables))
        self._profile = profile
        self.descriptions = descriptions or {}
        self._engine = engine
        self.index = index
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

    @property
    def search_method(self) -> str:
        return self.index.mode if self.index is not None else "keyword"

    def search(self, query: str, k: int = 6, columns_per_table: int = 5) -> list[TableMatch]:
        """The best-matching tables, each with its best-matching columns."""
        if self.index is not None:
            try:
                return self._hybrid_search(query, k, columns_per_table)
            except Exception as exc:
                logger.warning("Schema index search failed (%s); using keyword search", exc)
        return self._keyword_search(query, k, columns_per_table)

    def _hybrid_search(self, query: str, k: int, columns_per_table: int) -> list[TableMatch]:
        hits = {(h.table_name, h.column_name): h for h in self.index.search(query, self.scope)}
        # The keyword ranking (identifier-aware, weights names over descriptions)
        # is a fourth RRF list next to the index's vector, trigram and value lists.
        for rank, (table_name, column_name) in enumerate(self._keyword_doc_ranking(query), 1):
            hit = hits.get((table_name, column_name))
            if hit is None:
                hit = hits[(table_name, column_name)] = DocHit(table_name, column_name, 0.0)
            hit.score += 1.0 / (RRF_K + rank)
            hit.sources.append("keyword")

        matches: dict[str, TableMatch] = {}
        table_scores: dict[str, float] = {}
        for hit in hits.values():
            table = self.table(hit.table_name)
            if table is None:
                continue
            match = matches.setdefault(table.name, TableMatch(table, 0.0))
            if not hit.column_name:
                table_scores[table.name] = hit.score
                continue
            col = table.column(hit.column_name)
            if col is None:
                continue
            match.columns.append((col, hit.score))
            if hit.values:
                match.values[col.name] = hit.values
        # A foreign-key column is about the table it references: a hit on
        # order_items.product_id is evidence for products, too. Without this,
        # every table with a product_id outranks products itself on "product".
        fk = {(r.from_table, c): r.to_table for r in self.relations()
              for c in r.from_columns if r.to_table != r.from_table}
        referenced: dict[str, float] = {}
        for name, match in list(matches.items()):
            for col, score in match.columns:
                target = self.table(fk.get((name, col.name), ""))
                if target is not None:
                    referenced[target.name] = max(referenced.get(target.name, 0.0), score)
                    matches.setdefault(target.name, TableMatch(target, 0.0))
        for name, match in matches.items():
            match.columns.sort(key=lambda c: -c[1])
            # A table ranks by its own document plus its two best columns (best
            # of 1-5 on BIRD: more lets wide tables win on many weak matches);
            # the best hit on a column referencing it counts as one of them.
            scores = sorted([s for _, s in match.columns]
                            + ([referenced[name]] if name in referenced else []), reverse=True)
            match.score = table_scores.get(name, 0.0) + sum(scores[:2])
            match.columns = match.columns[:columns_per_table]
        ranked = sorted(matches.values(), key=lambda m: (-m.score, m.table.name))
        return ranked[:k]

    def _keyword_scores(self, query: str):
        """[(table, table_score, [(column, score), ...] best first)] for every
        table with any keyword hit."""
        q = tokens(query)
        if not q:
            return []
        out = []
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
            if table_score or hits:
                out.append((table, table_score, hits))
        return out

    def _keyword_search(self, query: str, k: int, columns_per_table: int) -> list[TableMatch]:
        ranked = [TableMatch(table, table_score + sum(s for _, s in hits[:3]),
                             hits[:columns_per_table])
                  for table, table_score, hits in self._keyword_scores(query)]
        ranked.sort(key=lambda m: (-m.score, m.table.name))
        return ranked[:k]

    def _keyword_doc_ranking(self, query: str, depth: int = 40) -> list[tuple[str, str]]:
        """Table and column documents ranked by keyword score, as
        (table, column) with column "" for a table."""
        scored = []
        for table, table_score, hits in self._keyword_scores(query):
            if table_score:
                scored.append((table_score, table.name, ""))
            scored += [(score, table.name, col.name) for col, score in hits]
        scored.sort(key=lambda s: (-s[0], s[1], s[2]))
        return [(t, c) for _, t, c in scored[:depth]]

    # ── Schema linking ───────────────────────────────────────────────────────

    def link(self, question: str, max_tables: int = 8, max_chars: int = 24_000,
             carry: list[str] = ()) -> LinkResult | None:
        """The tables `question` most likely needs, the tables they reference
        and the bridge tables joining them, rendered in full (compact when
        needed to fit `max_chars`). `carry`: tables the conversation is about
        (a follow-up's previous answer), linked first whatever the search finds."""
        if max_tables <= 0:
            return None                # linking switched off
        carried = list(dict.fromkeys(
            t for t in (self.resolve_table(c) for c in carry) if t))[:_LINK_MAX_CARRIED]
        matches = self.search(question, k=max_tables * 3, columns_per_table=8)
        if not matches and not carried:
            return None
        relations = self.relations()
        graph = JoinGraph(relations)
        chosen = [m for m in (_coherent(matches, graph, max_tables) if matches else [])
                  if m.table.name not in carried]
        names = [m.table.name for m in chosen]
        names += [t for t in _parents(chosen, matches, relations)
                  if t not in names and t not in carried and self.table(t) is not None]
        bridges = [b for b in graph.bridge_tables(carried + names)
                   if b not in names and b not in carried
                   and self.table(b) is not None][:_LINK_MAX_BRIDGES]

        blocks = self._render_linked(carried + names + bridges, relations, max_chars)
        if not blocks:
            return None
        kept = {name for name, _ in blocks}
        mentioned = [
            f"  {sql_ident(m.table.name)}.{sql_ident(col)}: "
            + ", ".join("'" + v.replace("'", "''") + "'" for v in values)
            for m in chosen if m.table.name in kept for col, values in m.values.items()
        ]
        text = "\n\n".join(block for _, block in blocks)
        if mentioned:
            text += ("\n\nSTORED VALUES THAT MATCH WORDS OF THE QUESTION (use them only if "
                     "they are what the question means):\n" + "\n".join(mentioned))
        return LinkResult(text=text, tables=[t for t in names if t in kept],
                          bridges=[t for t in bridges if t in kept], method=self.search_method,
                          carried=[t for t in carried if t in kept])

    def _render_linked(self, tables: list[str], relations, max_chars: int) -> list[tuple[str, str]]:
        """(table, text) for `tables` (best first) within `max_chars`: as many
        tables as fit at the compact level (one too big for the space left is
        skipped, not the ones after it), then upgraded to full detail in
        rank order while that still fits."""
        compact = {n: render_table(self.table(n), relations, self.descriptions, level="compact")
                   for n in tables}
        kept, used = [], 0
        for name in tables:
            if used + len(compact[name]) + 2 <= max_chars:
                kept.append(name)
                used += len(compact[name]) + 2
        blocks = {n: compact[n] for n in kept}
        for name in kept:
            full = render_table(self.table(name), relations, self.descriptions, level="full")
            if used - len(compact[name]) + len(full) <= max_chars:
                blocks[name] = full
                used += len(full) - len(compact[name])
        return [(n, blocks[n]) for n in kept]

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
