"""Embedding service using OpenAI-compatible API."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any

from app.configs.logger import logger


class EmbeddingService:
    """Encapsulates OpenAI-compatible embedding API calls.

    Reuses the project's existing OpenAI client instance.
    """

    def __init__(
        self,
        client: Any,
        model: str = "text-embedding-v3",
        *,
        cache_size: int = 256,
    ) -> None:
        self._client = client
        self._model = model
        self._cache_size = cache_size

    def embed(self, text: str) -> list[float] | None:
        """Generate an embedding vector for a single text.

        Returns None when the API call fails, so callers can fall back gracefully.
        """
        text = text.strip()
        if not text:
            return None
        results = self.embed_batch([text])
        return results[0] if results else None

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Generate embeddings for multiple texts in one API call."""
        non_empty: list[tuple[int, str]] = []
        cached_results: list[list[float] | None] = [None] * len(texts)

        for idx, text in enumerate(texts):
            text = text.strip()
            if not text:
                continue
            cached = self._get_cached(text)
            if cached is not None:
                cached_results[idx] = cached
            else:
                non_empty.append((idx, text))

        if not non_empty:
            return cached_results

        try:
            response = self._client.embeddings.create(
                model=self._model,
                input=[t for _, t in non_empty],
            )
            for (idx, text), emb_data in zip(non_empty, response.data):
                embedding = list(emb_data.embedding)
                cached_results[idx] = embedding
                self._set_cached(text, embedding)
        except Exception:
            logger.warning(
                "embedding_service event=api_failed model=%s",
                self._model,
                exc_info=True,
            )

        return cached_results

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _get_cached(self, text: str) -> list[float] | None:
        return _embedding_cache_get(self._cache_key(text))

    def _set_cached(self, text: str, embedding: list[float]) -> None:
        _embedding_cache_set(self._cache_key(text), tuple(embedding))


# Module-level LRU cache for embedding vectors.
# Using a tuple keyed by sha256 hash to avoid unbounded memory growth.
_embedding_cache: dict[str, tuple[float, ...]] = {}


def _embedding_cache_get(key: str) -> list[float] | None:
    val = _embedding_cache.get(key)
    return list(val) if val is not None else None


def _embedding_cache_set(key: str, embedding: tuple[float, ...]) -> None:
    if len(_embedding_cache) >= 256:
        # Simple FIFO eviction: remove the first inserted key.
        first_key = next(iter(_embedding_cache))
        del _embedding_cache[first_key]
    _embedding_cache[key] = embedding
