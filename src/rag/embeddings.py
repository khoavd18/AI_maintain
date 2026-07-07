"""Embedding provider abstraction for maintenance RAG retrieval."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import blake2b
from typing import Protocol

import numpy as np

from src.config.settings import get_settings


QUERY_PREFIX = "query:"
PASSAGE_PREFIX = "passage:"


class EmbeddingDependencyError(RuntimeError):
    """Raised when the configured embedding provider is unavailable."""


class EmbeddingProvider(Protocol):
    """Protocol implemented by local or hosted embedding providers."""

    dimensions: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document chunks for indexing."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a user query for retrieval."""
        ...


class HashEmbeddingProvider:
    """Deterministic embeddings for local tests.

    This is not semantic search. Production indexing should use
    SentenceTransformerEmbeddingProvider.
    """

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Return deterministic passage vectors."""

        return self._embed([prefix_passage(text) for text in texts])

    def embed_query(self, text: str) -> list[float]:
        """Return a deterministic query vector."""

        return self._embed([prefix_query(text)])[0]

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = np.zeros(self.dimensions, dtype=float)
            for token in text.lower().split():
                digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest, "big") % self.dimensions
                vector[index] += 1.0
            norm = np.linalg.norm(vector)
            if norm > 0:
                vector = vector / norm
            vectors.append(vector.tolist())
        return vectors


class SentenceTransformerEmbeddingProvider:
    """Sentence-transformers embedding provider using E5-style prefixes."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or get_settings().embedding_model_name
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingDependencyError(
                "sentence-transformers is not installed. Install it with "
                'python -m pip install -e ".[rag]" or install sentence-transformers manually.'
            ) from exc

        try:
            self._model = SentenceTransformer(self.model_name)
            self.dimensions = int(self._model.get_sentence_embedding_dimension())
        except Exception as exc:
            raise EmbeddingDependencyError(
                f"Could not load embedding model '{self.model_name}': {exc}"
            ) from exc

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document chunks with the passage prefix."""

        return self._encode([prefix_passage(text) for text in texts])

    def embed_query(self, text: str) -> list[float]:
        """Embed a user query with the query prefix."""

        return self._encode([prefix_query(text)])[0]

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=float).tolist()


def prefix_passage(text: str) -> str:
    """Apply the E5 passage prefix."""

    return f"{PASSAGE_PREFIX} {text}"


def prefix_query(text: str) -> str:
    """Apply the E5 query prefix."""

    return f"{QUERY_PREFIX} {text}"


def create_embedding_provider(model_name: str | None = None) -> SentenceTransformerEmbeddingProvider:
    """Create the default embedding provider for indexing and retrieval."""

    return SentenceTransformerEmbeddingProvider(model_name=model_name)
