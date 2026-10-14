"""
The schema retrieval index, stored in the app database (pgvector + pg_trgm).

    schema_index_docs    one row per table / column document of an index
                         (lexical text with a trigram GIN index, embedding vector)
    schema_index_values  distinct values of low-cardinality text columns
                         (trigram GIN index)
    schema_index_state   per index: what it was built from, status

An index is identified by a key: "conn:<id>" for a user connection, or e.g.
"eval:bird" for the evaluation database. Searches are always limited to one
key and a set of allowed tables, so vector search is exact (a sequential scan
over one index's rows, a few thousand at most) rather than an approximate
HNSW scan whose post-filtering would lose rows of a small key among many.

Updates are incremental: only documents whose text changed are re-embedded,
and an embedding is reused from any index that already embedded the same
text with the same model (twin connections, re-runs).
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.engine import Engine
from sqlalchemy.types import Text

from app.config import get_settings
from app.services.schema_index.documents import IndexDoc, STOPWORDS, key_terms

logger = logging.getLogger(__name__)

RRF_K = 60                      # reciprocal rank fusion constant
_LIST_DEPTH = 40                # hits taken from each ranked list
_TERM_THRESHOLD = 0.6           # word_similarity(term, document) to count as a hit
# strict_word_similarity(value, question) to count as a mention: whole words
# only, so 'Super' doesn't match "superheroes".
_VALUE_THRESHOLD = 0.8
_MIN_VALUE_CHARS = 3
_MAX_TERMS = 16
_WRITE_BATCH = 500

_DDL = """
CREATE TABLE IF NOT EXISTS schema_index_docs (
    id bigserial PRIMARY KEY,
    index_key text NOT NULL,
    table_name text NOT NULL,
    column_name text NOT NULL DEFAULT '',
    kind text NOT NULL,
    lexical_text text NOT NULL,
    embed_text text NOT NULL,
    embed_hash text NOT NULL,
    content_hash text NOT NULL,
    embedding_model text,
    UNIQUE (index_key, table_name, column_name)
);
CREATE INDEX IF NOT EXISTS ix_schema_index_docs_lexical
    ON schema_index_docs USING gin (lexical_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_schema_index_docs_embed_hash
    ON schema_index_docs (embed_hash, embedding_model);

CREATE TABLE IF NOT EXISTS schema_index_values (
    index_key text NOT NULL,
    table_name text NOT NULL,
    column_name text NOT NULL,
    value text NOT NULL,
    PRIMARY KEY (index_key, table_name, column_name, value)
);
CREATE INDEX IF NOT EXISTS ix_schema_index_values_trgm
    ON schema_index_values USING gin (value gin_trgm_ops);

CREATE TABLE IF NOT EXISTS schema_index_state (
    index_key text PRIMARY KEY,
    docs_signature text,
    values_signature text,
    embedding_model text,
    status text NOT NULL DEFAULT 'pending',
    error text,
    doc_count integer NOT NULL DEFAULT 0,
    embedded_count integer NOT NULL DEFAULT 0,
    value_count integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in vector) + "]"


@dataclass
class DocHit:
    table_name: str
    column_name: str            # "" = the table document
    score: float                # fused RRF score
    sources: list[str] = field(default_factory=list)    # "vector" | "lexical" | "value"
    values: list[str] = field(default_factory=list)     # stored values the question mentions


class IndexStore:
    """Reads and writes the index tables. One per app engine."""

    def __init__(self, engine: Engine, dim: int):
        self.engine = engine
        self.dim = dim
        self._ready: bool | None = None
        self._error: str | None = None
        self._lock = threading.Lock()

    # ── Setup ────────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """True once the tables exist and pgvector + pg_trgm are installed."""
        with self._lock:
            if self._ready is None:
                try:
                    self._setup()
                    self._ready = True
                except Exception as exc:
                    self._ready, self._error = False, str(exc).splitlines()[0][:300]
                    logger.warning("Schema retrieval index unavailable (%s); agents fall back "
                                   "to keyword search over the profile", self._error)
            return self._ready

    @property
    def error(self) -> str | None:
        return self._error

    def _setup(self) -> None:
        with self.engine.begin() as conn:
            # Serialize setup across backend processes.
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('schema_index_setup'))"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            for statement in _DDL.split(";"):
                if statement.strip():
                    conn.execute(text(statement))
            current = conn.execute(text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = 'schema_index_docs'::regclass AND attname = 'embedding' "
                "AND NOT attisdropped")).scalar()
            wanted = f"vector({self.dim})"
            if current != wanted:
                if current is not None:
                    logger.info("Embedding size changed (%s -> %s); embeddings will be rebuilt",
                                current, wanted)
                    conn.execute(text("ALTER TABLE schema_index_docs DROP COLUMN embedding"))
                    conn.execute(text("UPDATE schema_index_docs SET embedding_model = NULL"))
                    conn.execute(text("UPDATE schema_index_state SET docs_signature = NULL"))
                conn.execute(text(f"ALTER TABLE schema_index_docs ADD COLUMN embedding {wanted}"))

    # ── State ────────────────────────────────────────────────────────────────

    def state(self, index_key: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM schema_index_state WHERE index_key = :k"),
                               {"k": index_key}).mappings().first()
        return dict(row) if row else None

    def set_state(self, index_key: str, **values) -> None:
        columns = ", ".join(values)
        placeholders = ", ".join(f":{c}" for c in values)
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in values)
        with self.engine.begin() as conn:
            conn.execute(text(
                f"INSERT INTO schema_index_state (index_key, {columns}, updated_at) "
                f"VALUES (:index_key, {placeholders}, now()) ON CONFLICT (index_key) "
                f"DO UPDATE SET {updates}, updated_at = now()"), {"index_key": index_key, **values})

    def delete(self, index_key: str) -> None:
        with self.engine.begin() as conn:
            for table in ("schema_index_docs", "schema_index_values", "schema_index_state"):
                conn.execute(text(f"DELETE FROM {table} WHERE index_key = :k"), {"k": index_key})

    # ── Writing documents ────────────────────────────────────────────────────

    def sync_documents(self, index_key: str, docs: list[IndexDoc], embedder) -> tuple[int, int]:
        """Make the stored documents of `index_key` equal `docs`. Returns
        (documents, documents with an embedding)."""
        model = embedder.model_id if embedder else None
        wanted = {(d.table_name, d.column_name): d for d in docs}
        with self.engine.connect() as conn:
            stored = {
                (r.table_name, r.column_name): r for r in conn.execute(text(
                    "SELECT table_name, column_name, content_hash, embed_hash, embedding_model, "
                    "embedding IS NOT NULL AS has_embedding "
                    "FROM schema_index_docs WHERE index_key = :k"), {"k": index_key})
            }

        removed = [k for k in stored if k not in wanted]
        changed = [d for k, d in wanted.items()
                   if k not in stored or stored[k].content_hash != d.content_hash]
        # Embeddings to (re)compute: new or edited text, or made by another model.
        to_embed = [d for k, d in wanted.items() if model and (
            k not in stored or stored[k].embed_hash != d.embed_hash
            or stored[k].embedding_model != model or not stored[k].has_embedding)]

        vectors = self._embeddings_for(to_embed, embedder) if to_embed else {}

        with self.engine.begin() as conn:
            if removed:
                conn.execute(text(
                    "DELETE FROM schema_index_docs WHERE index_key = :k "
                    "AND (table_name, column_name) IN (SELECT * FROM unnest(:t, :c))"
                ).bindparams(bindparam("t", type_=ARRAY(Text)), bindparam("c", type_=ARRAY(Text))),
                    {"k": index_key, "t": [k[0] for k in removed], "c": [k[1] for k in removed]})
            rows = []
            for d in {d.table_name + "\x1f" + d.column_name: d
                      for d in changed + to_embed}.values():
                vector = vectors.get(d.embed_hash)
                rows.append({
                    "k": index_key, "t": d.table_name, "c": d.column_name, "kind": d.kind,
                    "lex": d.lexical_text, "emb_text": d.embed_text, "eh": d.embed_hash,
                    "ch": d.content_hash, "model": model if vector is not None else None,
                    "vec": _vector_literal(vector) if vector is not None else None,
                })
            for start in range(0, len(rows), _WRITE_BATCH):
                conn.execute(text(
                    "INSERT INTO schema_index_docs (index_key, table_name, column_name, kind, "
                    "lexical_text, embed_text, embed_hash, content_hash, embedding_model, embedding) "
                    "VALUES (:k, :t, :c, :kind, :lex, :emb_text, :eh, :ch, :model, "
                    "CAST(:vec AS vector)) "
                    "ON CONFLICT (index_key, table_name, column_name) DO UPDATE SET "
                    "kind = EXCLUDED.kind, lexical_text = EXCLUDED.lexical_text, "
                    "embed_text = EXCLUDED.embed_text, content_hash = EXCLUDED.content_hash, "
                    # Keep the old vector when this update has none for unchanged text.
                    "embedding = CASE WHEN EXCLUDED.embedding IS NOT NULL THEN EXCLUDED.embedding "
                    "  WHEN schema_index_docs.embed_hash = EXCLUDED.embed_hash "
                    "  THEN schema_index_docs.embedding END, "
                    "embedding_model = CASE WHEN EXCLUDED.embedding IS NOT NULL "
                    "  THEN EXCLUDED.embedding_model "
                    "  WHEN schema_index_docs.embed_hash = EXCLUDED.embed_hash "
                    "  THEN schema_index_docs.embedding_model END, "
                    "embed_hash = EXCLUDED.embed_hash"), rows[start:start + _WRITE_BATCH])
            counts = conn.execute(text(
                "SELECT count(*), count(embedding) FROM schema_index_docs WHERE index_key = :k"),
                {"k": index_key}).one()
        return counts[0], counts[1]

    def _embeddings_for(self, docs: list[IndexDoc], embedder) -> dict[str, list[float]]:
        """{embed_hash: vector}: reused from any index where possible, the
        rest from the embedding API."""
        hashes = sorted({d.embed_hash for d in docs})
        vectors: dict[str, list[float]] = {}
        with self.engine.connect() as conn:
            for row in conn.execute(text(
                    "SELECT DISTINCT ON (embed_hash) embed_hash, embedding::text "
                    "FROM schema_index_docs WHERE embed_hash = ANY(:h) AND embedding_model = :m "
                    "AND embedding IS NOT NULL"
            ).bindparams(bindparam("h", type_=ARRAY(Text))), {"h": hashes, "m": embedder.model_id}):
                vectors[row[0]] = json.loads(row[1])
        missing = {}
        for d in docs:
            if d.embed_hash not in vectors:
                missing.setdefault(d.embed_hash, d.embed_text)
        if missing:
            logger.info("Embedding %d schema documents with %s", len(missing), embedder.model_id)
            for h, vector in zip(missing, embedder.embed_documents(list(missing.values()))):
                vectors[h] = vector
        return vectors

    def replace_values(self, index_key: str, rows: list[tuple[str, str, str]]) -> int:
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM schema_index_values WHERE index_key = :k"),
                         {"k": index_key})
            params = [{"k": index_key, "t": t, "c": c, "v": v} for t, c, v in rows]
            for start in range(0, len(params), _WRITE_BATCH):
                conn.execute(text(
                    "INSERT INTO schema_index_values (index_key, table_name, column_name, value) "
                    "VALUES (:k, :t, :c, :v) ON CONFLICT DO NOTHING"), params[start:start + _WRITE_BATCH])
        return len(rows)

    # ── Search ───────────────────────────────────────────────────────────────

    def search(self, index_key: str, question: str, tables: list[str],
               query_vector: list[float] | None, embedding_model: str | None,
               depth: int = _LIST_DEPTH) -> list[DocHit]:
        """Table and column documents ranked for `question`: the vector,
        trigram and value-mention rankings fused with RRF in one query."""
        terms = question_terms(question)
        use_vector = query_vector is not None and embedding_model is not None
        sql = text(f"""
WITH
vec AS (
    SELECT table_name, column_name,
           row_number() OVER (ORDER BY embedding <=> CAST(:qvec AS vector)) AS rnk
    FROM schema_index_docs
    WHERE :use_vec AND index_key = :k AND table_name = ANY(:tables)
      AND embedding_model = :model AND embedding IS NOT NULL
    ORDER BY embedding <=> CAST(:qvec AS vector)
    LIMIT :depth
),
lex AS (
    SELECT table_name, column_name, row_number() OVER (ORDER BY score DESC) AS rnk
    FROM (
        SELECT d.table_name, d.column_name,
               sum(word_similarity(t.term, d.lexical_text)) AS score
        FROM schema_index_docs d
        CROSS JOIN unnest(CAST(:terms AS text[])) AS t(term)
        WHERE d.index_key = :k AND d.table_name = ANY(:tables)
          AND t.term <% d.lexical_text
        GROUP BY d.table_name, d.column_name
    ) s
    ORDER BY score DESC
    LIMIT :depth
),
val AS (
    SELECT table_name, column_name, matched,
           row_number() OVER (ORDER BY score DESC) AS rnk
    FROM (
        SELECT v.table_name, v.column_name, max(s.sim) AS score,
               (array_agg(v.value ORDER BY s.sim DESC, length(v.value) DESC))[1:5] AS matched
        FROM schema_index_values v
        CROSS JOIN LATERAL (SELECT strict_word_similarity(v.value, :q) AS sim) s
        WHERE v.index_key = :k AND v.table_name = ANY(:tables)
          AND length(v.value) >= {_MIN_VALUE_CHARS}
          AND v.value <<% :q AND s.sim >= {_VALUE_THRESHOLD}
        GROUP BY v.table_name, v.column_name
    ) s
    ORDER BY score DESC
    LIMIT :depth
),
ranked AS (
    SELECT table_name, column_name, rnk, 'vector' AS source, NULL::text[] AS matched FROM vec
    UNION ALL
    SELECT table_name, column_name, rnk, 'lexical', NULL FROM lex
    UNION ALL
    SELECT table_name, column_name, rnk, 'value', matched FROM val
)
SELECT table_name, column_name,
       sum(1.0 / ({RRF_K} + rnk)) AS score,
       array_agg(source ORDER BY source) AS sources,
       max(matched) AS matched
FROM ranked
GROUP BY table_name, column_name
ORDER BY score DESC
""").bindparams(bindparam("tables", type_=ARRAY(Text)), bindparam("terms", type_=ARRAY(Text)))
        params = {
            "k": index_key, "tables": list(tables), "terms": terms, "q": question.lower(),
            "use_vec": use_vector, "model": embedding_model,
            "qvec": _vector_literal(query_vector) if use_vector else None, "depth": depth,
        }
        with self.engine.begin() as conn:
            conn.execute(text(f"SET LOCAL pg_trgm.word_similarity_threshold = {_TERM_THRESHOLD}"))
            conn.execute(text(
                f"SET LOCAL pg_trgm.strict_word_similarity_threshold = {_VALUE_THRESHOLD}"))
            rows = conn.execute(sql, params).all()
        return [DocHit(r.table_name, r.column_name, float(r.score), list(r.sources or []),
                       list(r.matched or [])) for r in rows]


    def find_values(self, index_key: str, needle: str, tables: list[str],
                    limit: int = 40) -> list[tuple[str, str, str]]:
        """Indexed values similar to `needle` (fuzzy, case-insensitive), as
        (table, column, value), most similar first."""
        pattern = "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql = text("""
SELECT table_name, column_name, value
FROM schema_index_values
WHERE index_key = :k AND table_name = ANY(:tables)
  AND (:n <% value OR value ILIKE :pattern)
ORDER BY greatest(word_similarity(:n, value), similarity(:n, value)) DESC, length(value)
LIMIT :limit
""").bindparams(bindparam("tables", type_=ARRAY(Text)))
        with self.engine.begin() as conn:
            conn.execute(text("SET LOCAL pg_trgm.word_similarity_threshold = 0.5"))
            rows = conn.execute(sql, {"k": index_key, "tables": list(tables), "n": needle,
                                      "pattern": pattern, "limit": limit}).all()
        return [(r[0], r[1], r[2]) for r in rows]


def question_terms(question: str) -> list[str]:
    """Words of the question worth matching against schema documents."""
    terms = [t for t in key_terms(question, limit=_MAX_TERMS * 2) if t not in STOPWORDS]
    return terms[:_MAX_TERMS]


def signature(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]


_store: IndexStore | None = None
_store_lock = threading.Lock()


def get_store() -> IndexStore | None:
    """The index store on the app database, or None when retrieval is
    disabled or the database lacks pgvector / pg_trgm."""
    settings = get_settings()
    if not settings.SCHEMA_RETRIEVAL_ENABLED or not settings.DATABASE_URL:
        return None
    global _store
    with _store_lock:
        if _store is None:
            from app.database import engine
            _store = IndexStore(engine, settings.EMBEDDING_DIM)
    return _store if _store.available else None
