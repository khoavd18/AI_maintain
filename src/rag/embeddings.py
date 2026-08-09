"""Embedding provider abstraction for maintenance RAG retrieval."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from hashlib import blake2b
from threading import Lock
from typing import Protocol

import numpy as np

from src.config.settings import get_settings

QUERY_PREFIX = "query:"
PASSAGE_PREFIX = "passage:"
logger = logging.getLogger("maintenance.rag.embeddings")


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
        if dimensions <= 0:
            raise ValueError("dimensions must be positive.")
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

    def __init__(
        self,
        model_name: str | None = None,
        *,
        device: str | None = None,
        batch_size: int | None = None,
        expected_dimensions: int | None = None,
    ) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model_name
        self.device = device or settings.embedding_device
        self.batch_size = batch_size or settings.embedding_batch_size
        configured_dimensions = expected_dimensions or settings.embedding_dimensions
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingDependencyError(
                "sentence-transformers is not installed. Install it with "
                'python -m pip install -e ".[rag]" or install sentence-transformers manually.'
            ) from exc

        try:
            model_device = None if self.device == "auto" else self.device
            self._model = SentenceTransformer(self.model_name, device=model_device)
            self.dimensions = int(self._model.get_sentence_embedding_dimension())
        except Exception as exc:
            if self.device not in {"auto", "cpu"}:
                logger.warning(
                    "Embedding device %s was unavailable; retrying on CPU.",
                    self.device,
                )
                try:
                    self._model = SentenceTransformer(self.model_name, device="cpu")
                    self.dimensions = int(self._model.get_sentence_embedding_dimension())
                    self.device = "cpu"
                except Exception as fallback_exc:
                    raise EmbeddingDependencyError(
                        f"Could not load embedding model '{self.model_name}' on the configured "
                        "device or CPU fallback."
                    ) from fallback_exc
            else:
                raise EmbeddingDependencyError(
                    f"Could not load embedding model '{self.model_name}'."
                ) from exc
        if self.dimensions != configured_dimensions:
            raise EmbeddingDependencyError(
                f"Embedding model dimension {self.dimensions} does not match configured "
                f"EMBEDDING_DIMENSIONS={configured_dimensions}."
            )
        logger.info(
            "Embedding model initialized: model=%s dimensions=%s device=%s batch_size=%s",
            self.model_name,
            self.dimensions,
            self.device,
            self.batch_size,
        )

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document chunks with the passage prefix."""

        return self._encode([prefix_passage(text) for text in texts])

    def embed_query(self, text: str) -> list[float]:
        """Embed a user query with the query prefix."""

        return self._encode([prefix_query(text)])[0]

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        array = np.asarray(vectors, dtype=float)
        if array.ndim != 2 or array.shape != (len(texts), self.dimensions):
            raise EmbeddingDependencyError("Embedding provider returned an invalid vector shape.")
        norms = np.linalg.norm(array, axis=1)
        if not np.all(np.isfinite(array)) or not np.allclose(norms, 1.0, atol=1e-4):
            raise EmbeddingDependencyError("Embedding vectors are not finite unit vectors.")
        return array.tolist()


class LazySentenceTransformerEmbeddingProvider:
    """Delay the heavyweight E5 model load until semantic retrieval is requested."""

    def __init__(
        self,
        model_name: str | None = None,
        *,
        device: str | None = None,
        batch_size: int | None = None,
        expected_dimensions: int | None = None,
    ) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model_name
        self.device = device or settings.embedding_device
        self.batch_size = batch_size or settings.embedding_batch_size
        self.dimensions = expected_dimensions or settings.embedding_dimensions
        self._provider: SentenceTransformerEmbeddingProvider | None = None
        self._lock = Lock()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Load E5 once, then embed document passages."""

        return self._get_provider().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """Load E5 once, then embed one retrieval query."""

        return self._get_provider().embed_query(text)

    def _get_provider(self) -> SentenceTransformerEmbeddingProvider:
        if self._provider is None:
            with self._lock:
                if self._provider is None:
                    self._provider = SentenceTransformerEmbeddingProvider(
                        model_name=self.model_name,
                        device=self.device,
                        batch_size=self.batch_size,
                        expected_dimensions=self.dimensions,
                    )
        return self._provider


def prefix_passage(text: str) -> str:
    """Apply the E5 passage prefix."""

    return f"{PASSAGE_PREFIX} {text}"


def prefix_query(text: str) -> str:
    """Apply the E5 query prefix."""

    return f"{QUERY_PREFIX} {text}"


def create_embedding_provider(
    model_name: str | None = None,
) -> SentenceTransformerEmbeddingProvider:
    """Create the default embedding provider for indexing and retrieval."""

    settings = get_settings()
    return SentenceTransformerEmbeddingProvider(
        model_name=model_name,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        expected_dimensions=settings.embedding_dimensions,
    )
