"""Retrieval invocation and evidence-quality gates."""

from __future__ import annotations

from dataclasses import dataclass, field
import time

from src.rag.embeddings import EmbeddingDependencyError
from src.rag.applicability import ApplicabilityConstraint
from src.rag.evidence import has_significant_conflict
from src.rag.retriever import (
    SEMANTIC_RELEVANCE_THRESHOLD,
    RetrievalResult,
    RetrievalUnavailableError,
    Retriever,
)
from src.rag.vector_store import VectorStoreError
from src.llm.prompt_security import contains_unsafe_instruction
from src.rag.diagnostics import add_stage_latency, current_diagnostics


@dataclass(frozen=True)
class RetrievalDecision:
    """Result of retrieval plus the first applicable deterministic gate."""

    relevant: list[RetrievalResult] = field(default_factory=list)
    retrieval_status: str | None = None
    fallback_reason: str | None = None
    context_warnings: list[str] = field(default_factory=list)
    filters_applied: dict[str, str] = field(default_factory=dict)
    relaxation_steps: tuple[str, ...] = ()
    candidate_count: int = 0
    relevant_count: int = 0
    document_count: int = 0

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
        relaxable_filters: frozenset[str] = frozenset(),
        min_relevant_documents: int,
        applicability: ApplicabilityConstraint | None = None,
    ) -> RetrievalDecision:
        threshold = float(
            getattr(self.retriever, "minimum_relevance_score", SEMANTIC_RELEVANCE_THRESHOLD)
        )
        attempts = self._filter_attempts(filters, relaxable_filters)
        relaxation_steps: list[str] = []
        last_status = "empty"
        last_reason: str | None = None
        last_warnings: list[str] = []
        last_candidate_count = 0
        applied_filters = dict(filters)
        relevant: list[RetrievalResult] = []
        best_relevant: list[RetrievalResult] = []
        best_filters = dict(filters)
        best_relaxation_steps: tuple[str, ...] = ()
        best_candidate_count = 0
        applicability_warnings: list[str] = []
        best_applicability_warnings: list[str] = []
        best_quality: tuple[int, int, float] = (-1, -1, -1.0)
        for index, (attempt_filters, relaxed_filter) in enumerate(attempts):
            if relaxed_filter:
                relaxation_steps.append(relaxed_filter)
            applied_filters = attempt_filters
            optional_filters = {
                key: attempt_filters[key]
                for key in ["document_type", "failure_category", "version", "language"]
                if key in attempt_filters
            }
            try:
                diagnostics = current_diagnostics()
                recorded_before = (
                    diagnostics.latency_ms["retrieval"] if diagnostics is not None else 0.0
                )
                retrieval_started = time.perf_counter()
                retrievals = self.retriever.search(
                    query,
                    limit=top_k,
                    asset_type=attempt_filters.get("asset_type"),
                    **optional_filters,
                )
                if diagnostics is None or diagnostics.latency_ms["retrieval"] == recorded_before:
                    add_stage_latency(
                        "retrieval",
                        (time.perf_counter() - retrieval_started) * 1000.0,
                    )
            except (RetrievalUnavailableError, VectorStoreError, EmbeddingDependencyError):
                return RetrievalDecision(
                    retrieval_status="unavailable",
                    filters_applied=attempt_filters,
                    relaxation_steps=tuple(relaxation_steps),
                    context_warnings=self._relaxation_warnings(relaxation_steps),
                )

            last_candidate_count = len(retrievals)
            if not retrievals:
                last_status = "empty"
                last_reason = None
                last_warnings = []
            else:
                filtered_retrievals = [
                    result
                    for result in retrievals
                    if self._retrieval_matches_filters(result, attempt_filters)
                ]
                if not filtered_retrievals:
                    last_status = "empty"
                    last_reason = "retrieval_filter_mismatch"
                    last_warnings = ["retrieval_filter_mismatch_removed"]
                else:
                    applicable_retrievals = [
                        result
                        for result in filtered_retrievals
                        if applicability is None or applicability.allows(result)
                    ]
                    applicability_warnings = (
                        ["retrieval_model_mismatch_removed"]
                        if len(applicable_retrievals) != len(filtered_retrievals)
                        else []
                    )
                    if not applicable_retrievals:
                        last_status = "model_context_mismatch"
                        last_reason = "model_context_mismatch"
                        last_warnings = applicability_warnings
                        continue
                    relevant = [
                        result for result in applicable_retrievals if result.score >= threshold
                    ]
                    if relevant:
                        relevant_document_count = self._distinct_document_count(relevant)
                        quality = (
                            relevant_document_count,
                            len(relevant),
                            max(result.score for result in relevant),
                        )
                        if quality > best_quality:
                            best_relevant = relevant
                            best_filters = attempt_filters
                            best_relaxation_steps = tuple(relaxation_steps)
                            best_candidate_count = last_candidate_count
                            best_applicability_warnings = list(applicability_warnings)
                            best_quality = quality
                        if relevant_document_count >= min_relevant_documents:
                            break
                        last_status = "insufficient_evidence"
                        last_reason = "insufficient_evidence"
                        last_warnings = []
                    else:
                        last_status = "low_relevance"
                        last_reason = None
                        last_warnings = []

        if best_relevant and self._distinct_document_count(relevant) < min_relevant_documents:
            relevant = best_relevant
            applied_filters = best_filters
            relaxation_steps = list(best_relaxation_steps)
            last_candidate_count = best_candidate_count
            applicability_warnings = best_applicability_warnings
        if not relevant:
            return RetrievalDecision(
                retrieval_status=last_status,
                fallback_reason=last_reason,
                context_warnings=[
                    *self._relaxation_warnings(relaxation_steps),
                    *last_warnings,
                ],
                filters_applied=applied_filters,
                relaxation_steps=tuple(relaxation_steps),
                candidate_count=last_candidate_count,
            )

        safe_relevant = [
            result
            for result in relevant
            if not contains_unsafe_instruction(f"{result.title}\n{result.text}")
        ]
        context_warnings = [
            *self._relaxation_warnings(relaxation_steps),
            *applicability_warnings,
        ]
        unsafe_warnings = (
            ["unsafe_retrieved_context_removed"] if len(relevant) != len(safe_relevant) else []
        )
        context_warnings.extend(unsafe_warnings)
        if not safe_relevant:
            return RetrievalDecision(
                retrieval_status="unsafe_context",
                fallback_reason="unsafe_context",
                context_warnings=context_warnings,
                filters_applied=applied_filters,
                relaxation_steps=tuple(relaxation_steps),
                candidate_count=last_candidate_count,
                relevant_count=len(relevant),
            )
        if has_significant_conflict(safe_relevant):
            return RetrievalDecision(
                retrieval_status="conflicting_evidence",
                fallback_reason="conflicting_evidence",
                context_warnings=[*context_warnings, "conflicting_retrieved_evidence"],
                filters_applied=applied_filters,
                relaxation_steps=tuple(relaxation_steps),
                candidate_count=last_candidate_count,
                relevant_count=len(safe_relevant),
            )

        relevant_document_count = self._distinct_document_count(safe_relevant)
        if relevant_document_count < min_relevant_documents:
            return RetrievalDecision(
                retrieval_status="insufficient_evidence",
                fallback_reason="insufficient_evidence",
                context_warnings=context_warnings,
                filters_applied=applied_filters,
                relaxation_steps=tuple(relaxation_steps),
                candidate_count=last_candidate_count,
                relevant_count=len(safe_relevant),
                document_count=relevant_document_count,
            )
        return RetrievalDecision(
            relevant=safe_relevant,
            context_warnings=context_warnings,
            filters_applied=applied_filters,
            relaxation_steps=tuple(relaxation_steps),
            candidate_count=last_candidate_count,
            relevant_count=len(safe_relevant),
            document_count=relevant_document_count,
        )

    @staticmethod
    def _filter_attempts(
        filters: dict[str, str],
        relaxable_filters: frozenset[str],
    ) -> list[tuple[dict[str, str], str | None]]:
        attempts: list[tuple[dict[str, str], str | None]] = [(dict(filters), None)]
        current = dict(filters)
        for filter_name in ("failure_category", "document_type"):
            if filter_name not in relaxable_filters or filter_name not in current:
                continue
            current = {key: value for key, value in current.items() if key != filter_name}
            attempts.append((current, filter_name))
        return attempts

    @staticmethod
    def _relaxation_warnings(relaxation_steps: list[str]) -> list[str]:
        return [f"retrieval_filter_relaxed:{filter_name}" for filter_name in relaxation_steps]

    @staticmethod
    def _distinct_document_count(results: list[RetrievalResult]) -> int:
        return len({result.doc_id or result.source or result.title for result in results})

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
