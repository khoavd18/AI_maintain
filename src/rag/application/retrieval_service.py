"""Retrieval invocation and evidence-quality gates."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.rag.embeddings import EmbeddingDependencyError
from src.rag.evidence import has_significant_conflict
from src.rag.retriever import (
    SEMANTIC_RELEVANCE_THRESHOLD,
    RetrievalResult,
    RetrievalUnavailableError,
    Retriever,
)
from src.rag.vector_store import VectorStoreError
from src.llm.prompt_security import contains_unsafe_instruction


@dataclass(frozen=True)
class RetrievalDecision:
    """Result of retrieval plus the first applicable deterministic gate."""

    relevant: list[RetrievalResult] = field(default_factory=list)
    retrieval_status: str | None = None
    fallback_reason: str | None = None
    context_warnings: list[str] = field(default_factory=list)

    @property
    def requires_fallback(self) -> bool:
        return self.retrieval_status is not None


class RetrievalService:
    """Own candidate retrieval, metadata filtering, safety, and evidence gates."""

    def __init__(self, retriever: Retriever) -> None:
        self.retriever = retriever

    def retrieve(
        self,
        *,
        query: str,
        top_k: int,
        filters: dict[str, str],
        min_relevant_documents: int,
    ) -> RetrievalDecision:
        optional_filters = {
            key: filters[key]
            for key in ["document_type", "failure_category", "version", "language"]
            if key in filters
        }
        try:
            retrievals = self.retriever.search(
                query,
                limit=top_k,
                asset_type=filters.get("asset_type"),
                **optional_filters,
            )
        except (RetrievalUnavailableError, VectorStoreError, EmbeddingDependencyError):
            return RetrievalDecision(retrieval_status="unavailable")

        if not retrievals:
            return RetrievalDecision(retrieval_status="empty")
        filtered_retrievals = [
            result for result in retrievals if self._retrieval_matches_filters(result, filters)
        ]
        if not filtered_retrievals:
            return RetrievalDecision(
                retrieval_status="empty",
                fallback_reason="retrieval_filter_mismatch",
                context_warnings=["retrieval_filter_mismatch_removed"],
            )

        threshold = float(
            getattr(self.retriever, "minimum_relevance_score", SEMANTIC_RELEVANCE_THRESHOLD)
        )
        relevant = [result for result in filtered_retrievals if result.score >= threshold]
        if not relevant:
            return RetrievalDecision(retrieval_status="low_relevance")

        safe_relevant = [
            result
            for result in relevant
            if not contains_unsafe_instruction(f"{result.title}\n{result.text}")
        ]
        context_warnings = (
            ["unsafe_retrieved_context_removed"]
            if len(relevant) != len(safe_relevant)
            else []
        )
        if not safe_relevant:
            return RetrievalDecision(
                retrieval_status="unsafe_context",
                fallback_reason="unsafe_context",
                context_warnings=context_warnings,
            )
        if has_significant_conflict(safe_relevant):
            return RetrievalDecision(
                retrieval_status="conflicting_evidence",
                fallback_reason="conflicting_evidence",
                context_warnings=[*context_warnings, "conflicting_retrieved_evidence"],
            )

        relevant_document_count = len(
            {result.doc_id or result.source or result.title for result in safe_relevant}
        )
        if relevant_document_count < min_relevant_documents:
            return RetrievalDecision(
                retrieval_status="insufficient_evidence",
                fallback_reason="insufficient_evidence",
                context_warnings=context_warnings,
            )
        return RetrievalDecision(relevant=safe_relevant, context_warnings=context_warnings)

    @staticmethod
    def _retrieval_matches_filters(result: RetrievalResult, filters: dict[str, str]) -> bool:
        actual = {
            "asset_type": result.asset_type,
            "document_type": result.doc_type,
            "failure_category": result.failure_category,
            "version": result.version,
            "language": result.language,
        }
        return all(actual.get(key) == value for key, value in filters.items())
