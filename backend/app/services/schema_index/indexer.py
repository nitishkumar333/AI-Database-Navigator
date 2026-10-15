"""
Builds and queries a schema retrieval index (see index_store.py).

    update_index("conn:7", profile, descriptions, source_engine=engine)
    index = HybridIndex.for_key("conn:7")          # None until it has been built
    hits = index.search("loans of czech clients", tables)

update_index is cheap to call often: it compares signatures of what the index
was built from and only re-embeds documents whose text changed. Category
values are re-read when the profile is re-made (not when only descriptions
change).
"""
from __future__ import annotations

import logging
import threading

from sqlalchemy.engine import Engine

from app.config import get_settings
from app.services.embeddings import EmbeddingError, get_embedder
from app.services.schema_index.documents import build_documents, collect_values
from app.services.schema_index.index_store import DocHit, IndexStore, get_store, signature
from app.services.schema_index.profiler import SchemaProfile
from app.services.schema_index.render import Descriptions

logger = logging.getLogger(__name__)

_DOCS_VERSION = 1               # bump when documents.py changes what documents contain
_VALUES_VERSION = 2
_key_locks: dict[str, threading.Lock] = {}
_key_locks_lock = threading.Lock()

_UNSET = object()


def _key_lock(index_key: str) -> threading.Lock:
    with _key_locks_lock:
        return _key_locks.setdefault(index_key, threading.Lock())


def update_index(index_key: str, profile: SchemaProfile, descriptions: Descriptions | None, *,
                 source_engine: Engine | None, store: IndexStore | None = None,
                 embedder=_UNSET, force: bool = False) -> dict | None:
    """Bring the index up to date with the profile and descriptions. Returns
    the index state, or None when no index store is available."""
    store = store or get_store()
    if store is None:
        return None
    embedder = get_embedder() if embedder is _UNSET else embedder
    model = embedder.model_id if embedder else None
    max_distinct = get_settings().SCHEMA_VALUE_INDEX_MAX_DISTINCT

    with _key_lock(index_key):
        docs = build_documents(profile, descriptions)
        docs_sig = signature(_DOCS_VERSION, model, sorted(d.content_hash for d in docs))
        values_sig = signature(_VALUES_VERSION, max_distinct, profile.schema_hash,
                               profile.profiled_at)
        state = store.state(index_key) or {}
        docs_current = state.get("docs_signature") == docs_sig
        values_current = state.get("values_signature") == values_sig
        if not force and state.get("status") == "ready" and docs_current and values_current:
            return state

        store.set_state(index_key, status="running", error=None)
        error = None
        try:
            if force or not docs_current:
                try:
                    doc_count, embedded = store.sync_documents(index_key, docs, embedder)
                except EmbeddingError as exc:
                    # Keep the index usable (trigram + values); embeddings are retried next time.
                    logger.warning("Embedding schema documents for %s failed: %s", index_key, exc)
                    error = f"embeddings: {exc}"[:1000]
                    doc_count, embedded = store.sync_documents(index_key, docs, None)
                    docs_sig = None
            else:
                doc_count, embedded = state.get("doc_count", 0), state.get("embedded_count", 0)

            if force or not values_current:
                value_count = store.replace_values(
                    index_key, collect_values(source_engine, profile, max_distinct))
            else:
                value_count = state.get("value_count", 0)
        except Exception as exc:
            logger.exception("Indexing %s failed", index_key)
            store.set_state(index_key, status="failed", error=str(exc)[:1000])
            raise

        store.set_state(index_key, status="ready", error=error, docs_signature=docs_sig,
                        values_signature=values_sig, embedding_model=model if embedded else None,
                        doc_count=doc_count, embedded_count=embedded, value_count=value_count)
        logger.info("Schema index %s: %d documents (%d embedded), %d values",
                    index_key, doc_count, embedded, value_count)
        return store.state(index_key)


class HybridIndex:
    """Search handle for one index key, used by SchemaView."""

    def __init__(self, store: IndexStore, index_key: str, embedder, embedding_model: str | None):
        self.store = store
        self.index_key = index_key
        self.embedder = embedder
        # Vector search only when the stored vectors come from the current model.
        self.embedding_model = (embedding_model if embedder is not None
                                and embedding_model == embedder.model_id else None)

    @classmethod
    def for_key(cls, index_key: str, store: IndexStore | None = None,
                embedder=_UNSET) -> "HybridIndex | None":
        store = store or get_store()
        if store is None:
            return None
        try:
            state = store.state(index_key)
        except Exception as exc:
            logger.warning("Could not read schema index state of %s: %s", index_key, exc)
            return None
        if not state or not state.get("doc_count"):
            return None
        embedder = get_embedder() if embedder is _UNSET else embedder
        return cls(store, index_key, embedder, state.get("embedding_model"))

    @property
    def mode(self) -> str:
        return "hybrid" if self.embedding_model else "trigram"

    def find_values(self, needle: str, tables: list[str]) -> list[tuple[str, str, str]]:
        return self.store.find_values(self.index_key, needle, tables)

    def search(self, question: str, tables: list[str]) -> list[DocHit]:
        vector = None
        if self.embedding_model:
            try:
                vector = self.embedder.embed_query(question)
            except Exception as exc:
                logger.warning("Query embedding failed (%s); searching without vectors", exc)
        return self.store.search(self.index_key, question, tables, vector,
                                 self.embedding_model if vector is not None else None)
