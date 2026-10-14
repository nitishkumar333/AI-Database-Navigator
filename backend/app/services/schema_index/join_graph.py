"""
Join paths between tables, found on the foreign-key graph (declared and
inferred relations). A schema has at most a few thousand FK edges, so a plain
breadth-first search is enough; no graph library or graph database is needed.
"""
from __future__ import annotations

from collections import deque
from itertools import combinations

from app.services.schema_index.profiler import RelationProfile
from app.services.schema_index.render import sql_ident


class JoinGraph:
    def __init__(self, relations: list[RelationProfile], tables: set[str] | None = None):
        """`tables` limits the graph (e.g. to a knowledge base's tables)."""
        self._edges: dict[str, list[tuple[str, RelationProfile]]] = {}
        for rel in relations:
            if tables is not None and not {rel.from_table, rel.to_table} <= tables:
                continue
            if rel.from_table == rel.to_table:
                continue   # self-references never connect two different tables
            self._edges.setdefault(rel.from_table, []).append((rel.to_table, rel))
            self._edges.setdefault(rel.to_table, []).append((rel.from_table, rel))
        for neighbours in self._edges.values():
            # Declared keys first, so ties between paths prefer them.
            neighbours.sort(key=lambda e: (e[1].source != "declared", e[0]))

    def shortest_path(self, start: str, goal: str, max_hops: int = 4) -> list[RelationProfile] | None:
        """Relations joining `start` to `goal` in order, [] if they are the
        same table, None if they aren't connected within `max_hops`."""
        if start == goal:
            return []
        previous: dict[str, tuple[str, RelationProfile]] = {}
        seen, queue = {start}, deque([(start, 0)])
        while queue:
            table, hops = queue.popleft()
            if hops == max_hops:
                continue
            for neighbour, rel in self._edges.get(table, []):
                if neighbour in seen:
                    continue
                seen.add(neighbour)
                previous[neighbour] = (table, rel)
                if neighbour == goal:
                    path = []
                    while neighbour != start:
                        neighbour, rel = previous[neighbour]
                        path.append(rel)
                    return path[::-1]
                queue.append((neighbour, hops + 1))
        return None

    def bridge_tables(self, tables: list[str], max_hops: int = 3) -> list[str]:
        """Tables that connect `tables` to each other on the foreign-key graph
        (an approximate Steiner tree): each table, in order, joins the tree
        built so far by its shortest path to any table already in it."""
        tree: list[str] = tables[:1]
        bridges: list[str] = []
        for table in tables[1:]:
            if table in tree:
                continue
            best = None
            for node in tree:
                path = self.shortest_path(table, node, max_hops)
                if path is not None and (best is None or len(path) < len(best)):
                    best = path
            tree.append(table)
            for rel in best or []:
                for t in (rel.from_table, rel.to_table):
                    if t not in tree:
                        tree.append(t)
                        bridges.append(t)
        return bridges

    def describe_paths(self, tables: list[str], max_pairs: int = 15) -> list[str]:
        """One line per pair of `tables`: the join conditions that connect
        them, including any bridge tables on the way."""
        lines = []
        for a, b in list(combinations(tables, 2))[:max_pairs]:
            path = self.shortest_path(a, b)
            if path is None:
                lines.append(f"{sql_ident(a)} - {sql_ident(b)}: no foreign-key path")
                continue
            bridges = _bridge_tables(a, b, path)
            text = " AND ".join(_condition(rel) for rel in path)
            if bridges:
                text += "  (via " + ", ".join(sql_ident(t) for t in bridges) + ")"
            if any(rel.source == "inferred" for rel in path):
                text += "  [inferred]"
            lines.append(f"{sql_ident(a)} - {sql_ident(b)}: {text}")
        return lines


def _condition(rel: RelationProfile) -> str:
    return " AND ".join(
        f"{sql_ident(rel.from_table)}.{sql_ident(f)} = {sql_ident(rel.to_table)}.{sql_ident(t)}"
        for f, t in zip(rel.from_columns, rel.to_columns)
    )


def _bridge_tables(a: str, b: str, path: list[RelationProfile]) -> list[str]:
    seen = []
    for rel in path:
        for t in (rel.from_table, rel.to_table):
            if t not in (a, b) and t not in seen:
                seen.append(t)
    return seen
