"""Normalized dense + BM25 fusion with bounded metadata prior and reranking."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Protocol

from src.rag.reranking import Reranker, RerankerUnavailableError
from src.rag.retriever import RetrievalResult, Retriever
from src.rag.diagnostics import add_stage_latency


class SparseRetriever(Protocol):
    def search(self, query: str, *, limit: int, **filters: str | None) -> list[RetrievalResult]: ...


@dataclass(frozen=True)
class HybridRetrievalConfig:
    dense_candidates: int = 20
    sparse_candidates: int = 20
    fused_candidates: int = 20
    final_top_k: int = 5
    dense_weight: float = 0.5
    sparse_weight: float = 0.5
    retrieval_weight: float = 0.55
    reranker_weight: float = 0.40
    metadata_weight: float = 0.05
    relevance_threshold: float = 0.55

    def __post_init__(self) -> None:
        if (
            min(
                self.dense_candidates,
                self.sparse_candidates,
                self.fused_candidates,
                self.final_top_k,
            )
            <= 0
        ):
            raise ValueError("Hybrid candidate counts must be positive.")
        if self.fused_candidates < self.final_top_k:
            raise ValueError("fused_candidates must be at least final_top_k.")
        if not math.isclose(self.dense_weight + self.sparse_weight, 1.0, abs_tol=1e-9):
            raise ValueError("Dense and sparse weights must sum to 1.0.")
        if not math.isclose(
            self.retrieval_weight + self.reranker_weight + self.metadata_weight,
            1.0,
            abs_tol=1e-9,
        ):
            raise ValueError("Final hybrid weights must sum to 1.0.")
        if not 0 <= self.metadata_weight <= 0.1:
            raise ValueError("metadata_weight must remain bounded to at most 0.1.")
        if not 0 < self.relevance_threshold <= 1:
            raise ValueError("relevance_threshold must be within (0, 1].")


class HybridRetriever:
    """Retrieve broad candidates, normalize both channels, then cross-rerank."""

    def __init__(
        self,
        dense_retriever: Retriever,
        sparse_retriever: SparseRetriever,
        reranker: Reranker,
        config: HybridRetrievalConfig | None = None,
    ) -> None:
        self.dense_retriever = dense_retriever
        self.sparse_retriever = sparse_retriever
        self.reranker = reranker
        self.config = config or HybridRetrievalConfig()
        self.minimum_relevance_score = self.config.relevance_threshold

    def search(
        self,
        query: str,
        limit: int = 5,
        asset_type: str | None = None,
        document_type: str | None = None,
        failure_category: str | None = None,
        version: str | None = None,
        language: str | None = None,
    ) -> list[RetrievalResult]:
        filters = {
            "asset_type": asset_type,
            "document_type": document_type,
            "failure_category": failure_category,
            "version": version,
            "language": language,
        }
        retrieval_started = time.perf_counter()
        dense = self.dense_retriever.search(
            query,
            limit=max(limit, self.config.dense_candidates),
            **filters,
        )
        sparse = self.sparse_retriever.search(
            query,
            limit=max(limit, self.config.sparse_candidates),
            **filters,
        )
        fused = self._fuse(dense, sparse, filters)
        add_stage_latency("retrieval", (time.perf_counter() - retrieval_started) * 1000.0)
        rerank_candidates = fused[: self.config.fused_candidates]
        if not rerank_candidates:
            return []
        try:
            reranking_started = time.perf_counter()
            reranker_scores = self.reranker.score(query, rerank_candidates)
        except RerankerUnavailableError:
            # Retrieval-only fallback remains bounded and transparent in score components.
            reranker_scores = [candidate.score for candidate in rerank_candidates]
        finally:
            add_stage_latency("reranking", (time.perf_counter() - reranking_started) * 1000.0)
        if len(reranker_scores) != len(rerank_candidates):
            raise ValueError("Reranker returned an unexpected score count.")

        final: list[RetrievalResult] = []
        for candidate, reranker_score in zip(
            rerank_candidates,
            reranker_scores,
            strict=True,
        ):
            normalized_reranker = _bounded(reranker_score)
            final_score = (
                self.config.retrieval_weight * candidate.score
                + self.config.reranker_weight * normalized_reranker
                + self.config.metadata_weight * (candidate.metadata_prior or 0.0)
            )
            final.append(
                _copy_result(
                    candidate,
                    score=_bounded(final_score),
                    reranker_score=normalized_reranker,
                )
            )
        final.sort(key=lambda result: (-result.score, result.chunk_id))
        return final[: min(limit, self.config.final_top_k)]

    def _fuse(
        self,
        dense: list[RetrievalResult],
        sparse: list[RetrievalResult],
        filters: dict[str, str | None],
    ) -> list[RetrievalResult]:
        by_id: dict[str, RetrievalResult] = {}
        dense_scores: dict[str, float] = {}
        sparse_scores: dict[str, float] = {}
        for result in dense:
            key = _candidate_key(result)
            by_id.setdefault(key, result)
            raw_dense = result.dense_score if result.dense_score is not None else result.score
            dense_scores[key] = _normalize_cosine(raw_dense)
        maximum_sparse = max(
            (
                result.sparse_score if result.sparse_score is not None else result.score
                for result in sparse
            ),
            default=0.0,
        )
        for result in sparse:
            key = _candidate_key(result)
            by_id.setdefault(key, result)
            raw_sparse = result.sparse_score if result.sparse_score is not None else result.score
            sparse_scores[key] = _normalize_sparse(raw_sparse, maximum_sparse)

        fused: list[RetrievalResult] = []
        for key, result in by_id.items():
            dense_score = dense_scores.get(key, 0.0)
            sparse_score = sparse_scores.get(key, 0.0)
            retrieval_score = (
                self.config.dense_weight * dense_score + self.config.sparse_weight * sparse_score
            )
            prior = metadata_prior(result, filters)
            fused.append(
                _copy_result(
                    result,
                    score=retrieval_score,
                    dense_score=dense_score if key in dense_scores else None,
                    sparse_score=sparse_score if key in sparse_scores else None,
                    metadata_prior=prior,
                )
            )
        fused.sort(key=lambda result: (-result.score, result.chunk_id))
        return fused


def metadata_prior(result: RetrievalResult, filters: dict[str, str | None]) -> float:
    """Return a bounded match ratio; its contribution is capped by metadata_weight."""

    comparisons = {
        "asset_type": result.asset_type,
        "document_type": result.doc_type,
        "failure_category": result.failure_category,
        "version": result.version,
        "language": result.language,
    }
    requested = [(key, value) for key, value in filters.items() if value]
    if not requested:
        return 0.0
    matches = sum(comparisons.get(key) == value for key, value in requested)
    return _bounded(matches / len(requested))


def _candidate_key(result: RetrievalResult) -> str:
    return result.chunk_id or f"{result.doc_id}:{result.chunk_index}:{result.text}"


def _normalize_cosine(score: float) -> float:
    return _bounded((score + 1.0) / 2.0)


def _normalize_sparse(score: float, maximum: float) -> float:
    if score <= 0 or maximum <= 0:
        return 0.0
    return _bounded(math.log1p(score) / math.log1p(maximum))


def _bounded(score: float) -> float:
    return min(1.0, max(0.0, float(score)))


def _copy_result(
    result: RetrievalResult,
    *,
    score: float,
    dense_score: float | None = None,
    sparse_score: float | None = None,
    reranker_score: float | None = None,
    metadata_prior: float | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=result.chunk_id,
        doc_id=result.doc_id,
        title=result.title,
        doc_type=result.doc_type,
        asset_type=result.asset_type,
        source=result.source,
        text=result.text,
        score=score,
        failure_category=result.failure_category,
        version=result.version,
        effective_date=result.effective_date,
        language=result.language,
        chunk_index=result.chunk_index,
        dense_score=dense_score if dense_score is not None else result.dense_score,
        sparse_score=sparse_score if sparse_score is not None else result.sparse_score,
        reranker_score=(reranker_score if reranker_score is not None else result.reranker_score),
        metadata_prior=(metadata_prior if metadata_prior is not None else result.metadata_prior),
        equipment_model_identifiers=result.equipment_model_identifiers,
        document_revision_reference=result.document_revision_reference,
    )
