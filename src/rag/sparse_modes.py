"""Server-selected BM25 modes that preserve the Retriever contract."""

from __future__ import annotations

from collections import Counter
import logging
from typing import Protocol

from src.rag.retriever import RetrievalResult, Retriever
from src.rag.vector_store import VectorStoreError

logger = logging.getLogger("maintenance.rag.sparse_mode")


class SparseDiagnosticSource(Protocol):
    def diagnostics(self) -> dict[str, int | float | str | None]: ...


class ShadowSparseRetriever:
    """Run sparse retrieval after the primary path without changing its response."""

    def __init__(self, primary: Retriever, shadow: Retriever) -> None:
        self.primary = primary
        self.shadow = shadow
        self.minimum_relevance_score = getattr(primary, "minimum_relevance_score", 0.55)
        self._comparison_counts: Counter[str] = Counter()

    def search(self, query: str, limit: int = 5, **filters: str | None) -> list[RetrievalResult]:
        primary_results = self.primary.search(query, limit=limit, **filters)
        try:
            shadow_results = self.shadow.search(query, limit=limit, **filters)
            self._comparison_counts["shadow_queries"] += 1
            if [item.chunk_id for item in primary_results] == [
                item.chunk_id for item in shadow_results
            ]:
                self._comparison_counts["identical_rankings"] += 1
        except (VectorStoreError, RuntimeError):
            self._comparison_counts["shadow_unavailable"] += 1
        return primary_results

    def diagnostics(self) -> dict[str, int | float | str | None]:
        return {"mode": "shadow", **self._comparison_counts}


class FallbackSparseRetriever:
    """Use BM25 only while its authoritative snapshot is healthy."""

    def __init__(self, primary: Retriever, fallback: Retriever) -> None:
        self.primary = primary
        self.fallback = fallback
        self.minimum_relevance_score = getattr(fallback, "minimum_relevance_score", 0.55)
        self._fallback_count = 0

    def search(self, query: str, limit: int = 5, **filters: str | None) -> list[RetrievalResult]:
        try:
            return self.primary.search(query, limit=limit, **filters)
        except (VectorStoreError, RuntimeError):
            self._fallback_count += 1
            logger.warning("BM25 snapshot unavailable; using existing retriever fallback.")
            return self.fallback.search(query, limit=limit, **filters)

    def diagnostics(self) -> dict[str, int | float | str | None]:
        source = getattr(self.primary, "diagnostics", None)
        primary = source() if callable(source) else {}
        return {"mode": "bm25", "fallback_count": self._fallback_count, **primary}
