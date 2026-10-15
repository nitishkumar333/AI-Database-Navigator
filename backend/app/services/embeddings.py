"""
Text embeddings for schema retrieval, from the Jina AI embeddings API.

    embedder = get_embedder()          # None when no JINA_API_KEY is set
    vectors = embedder.embed_documents(["Column consumption of table yearmonth ..."])
    query = embedder.embed_query("monthly gas consumption")

Documents and queries are embedded with different task adapters
(retrieval.passage / retrieval.query), as the Jina retrieval models expect.
Vectors are L2-normalized, so cosine distance is the natural metric.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx
from cachetools import LRUCache

from app.config import get_settings

logger = logging.getLogger(__name__)

JINA_URL = "https://api.jina.ai/v1/embeddings"
_BATCH = 64                 # inputs per request (Jina batches internally by tokens)
_MAX_ATTEMPTS = 6
_TIMEOUT_S = 60.0


class EmbeddingError(RuntimeError):
    pass


class JinaEmbedder:
    def __init__(self, api_key: str, model: str, dim: int):
        self.model = model
        self.dim = dim
        self._headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        self._client = httpx.Client(timeout=_TIMEOUT_S)
        self._query_cache: LRUCache = LRUCache(maxsize=2048)
        self._lock = threading.Lock()
        # Some models don't accept `task` / `dimensions`; dropped after the first rejection.
        self._send_task = True
        self._send_dimensions = True

    @property
    def model_id(self) -> str:
        """Identifies the vector space: vectors from different ids never mix."""
        return f"jina:{self.model}:{self.dim}"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            vectors += self._embed(texts[start:start + _BATCH], "retrieval.passage")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        with self._lock:
            cached = self._query_cache.get(text)
        if cached is None:
            cached = self._embed([text], "retrieval.query")[0]
            with self._lock:
                self._query_cache[text] = cached
        return cached

    # ── HTTP ─────────────────────────────────────────────────────────────────

    def _payload(self, texts: list[str], task: str) -> dict:
        payload: dict = {"model": self.model, "input": texts, "normalized": True, "truncate": True}
        if self._send_task:
            payload["task"] = task
        if self._send_dimensions:
            payload["dimensions"] = self.dim
        return payload

    def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        if not texts:
            return []
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = self._client.post(JINA_URL, headers=self._headers,
                                             json=self._payload(texts, task))
            except httpx.HTTPError as exc:
                if attempt == _MAX_ATTEMPTS - 1:
                    raise EmbeddingError(f"Jina request failed: {exc}") from exc
                time.sleep(min(2 ** attempt, 30))
                continue

            if response.status_code == 200:
                return self._parse(response.json(), len(texts))
            body = response.text[:500]
            if response.status_code in (400, 422) and self._drop_rejected_field(body):
                continue                     # retry without the rejected field
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == _MAX_ATTEMPTS - 1:
                    break
                retry_after = response.headers.get("retry-after")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
                logger.info("Jina returned %s; retrying in %.0fs", response.status_code, delay)
                time.sleep(min(delay, 60))
                continue
            raise EmbeddingError(f"Jina returned {response.status_code}: {body}")
        raise EmbeddingError(f"Jina kept failing (last status {response.status_code}): {body}")

    def _drop_rejected_field(self, body: str) -> bool:
        text = body.lower()
        if self._send_task and "task" in text:
            logger.warning("Jina rejected `task` for %s; embedding without it", self.model)
            self._send_task = False
            return True
        if self._send_dimensions and "dimension" in text:
            logger.warning("Jina rejected `dimensions` for %s; using its default size", self.model)
            self._send_dimensions = False
            return True
        return False

    def _parse(self, body: dict, expected: int) -> list[list[float]]:
        data = sorted(body.get("data") or [], key=lambda d: d.get("index", 0))
        vectors = [d.get("embedding") for d in data]
        if len(vectors) != expected or any(not isinstance(v, list) for v in vectors):
            raise EmbeddingError(f"Jina returned {len(vectors)} embeddings for {expected} inputs")
        if any(len(v) != self.dim for v in vectors):
            raise EmbeddingError(
                f"{self.model} returned {len(vectors[0])}-dimensional vectors; "
                f"set EMBEDDING_DIM={len(vectors[0])} or pick a model that supports {self.dim}")
        return vectors


_embedder: JinaEmbedder | None = None
_embedder_key: tuple | None = None
_embedder_lock = threading.Lock()


def get_embedder() -> JinaEmbedder | None:
    """The configured embedder, created once; None when no API key is set."""
    global _embedder, _embedder_key
    settings = get_settings()
    if not settings.JINA_API_KEY:
        return None
    key = (settings.JINA_API_KEY, settings.JINA_EMBEDDING_MODEL, settings.EMBEDDING_DIM)
    with _embedder_lock:
        if _embedder is None or _embedder_key != key:
            _embedder = JinaEmbedder(*key)
            _embedder_key = key
        return _embedder
