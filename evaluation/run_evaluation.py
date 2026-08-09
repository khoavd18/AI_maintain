"""Run small, reproducible retrieval and answer-safety evaluations."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
from typing import Any, Literal

from qdrant_client import QdrantClient

from src.config.settings import get_settings
from src.llm.base import LLMGenerationRequest, LLMGenerationResult, LLMProvider
from src.llm.provider_factory import create_llm_provider
from src.rag.chunking import chunk_documents
from src.rag.copilot import CopilotGenerationConfig, MaintenanceCopilot
from src.rag.document_loader import RAW_DOCUMENT_FILE, load_documents
from src.rag.embeddings import HashEmbeddingProvider, create_embedding_provider
from src.rag.hybrid_retriever import HybridRetrievalConfig, HybridRetriever
from src.rag.reranking import CrossEncoderReranker
from src.rag.retriever import QdrantRetriever, Retriever
from src.rag.retriever import RetrievalResult
from src.rag.sparse_search import BM25Index, QdrantBM25Retriever, tokenize
from src.rag.vector_store import QdrantVectorStore

DEFAULT_DATASET = Path("evaluation/rag_questions.jsonl")
DATASET_VERSION = "2.0.0"
EvaluationMode = Literal["retrieval", "deterministic", "rag-llm"]


@dataclass(frozen=True)
class EvaluationQuestion:
    id: str
    question: str
    asset_type: str | None
    expected_document_ids: tuple[str, ...]
    expected_no_answer: bool
    expected_status: str | None = None
    selected_asset_id: str | None = None
    selected_asset_type: str | None = None


def load_questions(path: Path = DEFAULT_DATASET) -> list[EvaluationQuestion]:
    questions: list[EvaluationQuestion] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            questions.append(
                EvaluationQuestion(
                    id=str(value["id"]),
                    question=str(value["question"]),
                    asset_type=value.get("asset_type"),
                    expected_document_ids=tuple(value.get("expected_document_ids", [])),
                    expected_no_answer=bool(value["expected_no_answer"]),
                    expected_status=value.get("expected_status"),
                    selected_asset_id=value.get("selected_asset_id"),
                    selected_asset_type=value.get("selected_asset_type"),
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid evaluation row at line {line_number}.") from exc
    if not questions:
        raise ValueError("Evaluation dataset is empty.")
    return questions


def build_in_memory_retrievers(documents_path: Path = RAW_DOCUMENT_FILE) -> dict[str, Retriever]:
    """Build a deterministic local retrieval fixture without external services."""

    documents = load_documents(documents_path)
    chunks = chunk_documents(documents)
    provider = HashEmbeddingProvider(dimensions=384)
    store = QdrantVectorStore(
        collection_name="maintenance_evaluation",
        client=QdrantClient(":memory:"),
    )
    store.create_collection(provider.dimensions, recreate=True)
    store.upsert_chunks(chunks, provider.embed_documents([chunk.text for chunk in chunks]))
    dense = QdrantRetriever(provider, store)
    corpus = [
        RetrievalResult(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            title=chunk.title,
            doc_type=chunk.doc_type,
            asset_type=chunk.asset_type,
            source=chunk.source,
            text=chunk.text,
            score=0.0,
            failure_category=chunk.failure_category,
            version=chunk.version,
            effective_date=chunk.effective_date,
            language=chunk.language,
            chunk_index=chunk.chunk_index,
        )
        for chunk in chunks
    ]
    sparse = BM25Index(corpus)
    config = HybridRetrievalConfig(relevance_threshold=0.15)
    return {
        "dense_only": dense,
        "sparse_only": sparse,  # type: ignore[dict-item]
        "hybrid": HybridRetriever(dense, sparse, _PassThroughReranker(), config),
        "hybrid_reranked": HybridRetriever(dense, sparse, _LexicalReranker(), config),
    }


def build_in_memory_retriever(documents_path: Path = RAW_DOCUMENT_FILE) -> Retriever:
    """Return the complete deterministic hybrid fixture used by answer evaluation."""

    return build_in_memory_retrievers(documents_path)["hybrid_reranked"]


def build_configured_retrievers() -> dict[str, Retriever]:
    settings = get_settings()
    store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
    )
    dense = QdrantRetriever(
        create_embedding_provider(settings.embedding_model_name),
        store,
        minimum_relevance_score=settings.rag_relevance_threshold,
    )
    sparse = QdrantBM25Retriever(store, max_chunks=settings.rag_sparse_max_chunks)
    config = HybridRetrievalConfig(
        dense_candidates=settings.rag_dense_candidates,
        sparse_candidates=settings.rag_sparse_candidates,
        fused_candidates=settings.rag_fused_candidates,
        final_top_k=settings.rag_final_top_k,
        dense_weight=settings.rag_dense_weight,
        sparse_weight=settings.rag_sparse_weight,
        retrieval_weight=settings.rag_retrieval_weight,
        reranker_weight=settings.rag_reranker_weight,
        metadata_weight=settings.rag_metadata_weight,
        relevance_threshold=settings.rag_relevance_threshold,
    )
    return {
        "dense_only": dense,
        "sparse_only": sparse,  # type: ignore[dict-item]
        "hybrid": HybridRetriever(dense, sparse, _PassThroughReranker(), config),
        "hybrid_reranked": HybridRetriever(
            dense,
            sparse,
            CrossEncoderReranker(
                settings.rag_reranker_model,
                device=settings.rag_reranker_device,
            ),
            config,
        ),
    }


def build_configured_retriever() -> Retriever:
    return build_configured_retrievers()["hybrid_reranked"]


def evaluate_retrieval(
    questions: list[EvaluationQuestion],
    retriever: Retriever,
) -> dict[str, Any]:
    supported = [question for question in questions if not question.expected_no_answer]
    reciprocal_ranks: list[float] = []
    recall_hits = {1: 0, 3: 0, 5: 0}
    filter_correct = 0
    cases: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    for question in supported:
        started = time.perf_counter()
        results = retriever.search(
            question.question,
            limit=5,
            asset_type=question.asset_type,
        )
        latencies_ms.append((time.perf_counter() - started) * 1000.0)
        ranked_ids = list(dict.fromkeys(result.doc_id for result in results if result.doc_id))
        expected = set(question.expected_document_ids)
        rank = next(
            (
                index
                for index, document_id in enumerate(ranked_ids, start=1)
                if document_id in expected
            ),
            None,
        )
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        for k in recall_hits:
            recall_hits[k] += int(bool(expected.intersection(ranked_ids[:k])))
        filter_ok = bool(results) and all(
            result.asset_type == question.asset_type for result in results
        )
        filter_correct += int(filter_ok)
        cases.append(
            {
                "id": question.id,
                "ranked_document_ids": ranked_ids,
                "expected_document_ids": list(question.expected_document_ids),
                "first_relevant_rank": rank,
                "asset_filter_correct": filter_ok,
            }
        )
    denominator = len(supported) or 1
    return {
        "question_count": len(supported),
        "recall_at_1": recall_hits[1] / denominator,
        "recall_at_3": recall_hits[3] / denominator,
        "recall_at_5": recall_hits[5] / denominator,
        "mean_reciprocal_rank": sum(reciprocal_ranks) / denominator,
        "asset_type_filter_accuracy": filter_correct / denominator,
        "latency_ms": _latency_summary(latencies_ms),
        "cases": cases,
    }


def evaluate_answers(
    questions: list[EvaluationQuestion],
    retriever: Retriever,
    *,
    mode: EvaluationMode,
) -> dict[str, Any]:
    settings = get_settings()
    configured_provider = create_llm_provider(settings) if mode == "rag-llm" else None
    if mode == "rag-llm" and configured_provider is None:
        raise ValueError("rag-llm mode requires LLM_ENABLED=true and explicit provider settings.")
    llm_provider = _CountingProvider(configured_provider) if configured_provider else None
    copilot = MaintenanceCopilot(
        _EvaluationAssetContextService(questions),
        retriever,
        llm_provider,
        CopilotGenerationConfig(
            enabled=mode == "rag-llm",
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_context_chars=settings.llm_max_context_chars,
            min_relevant_documents=settings.llm_min_relevant_documents,
        ),
    )
    supported_total = 0
    source_hits = 0
    no_answer_total = 0
    no_answer_hits = 0
    safety_hits = 0
    generated_total = 0
    valid_citation_total = 0
    response_modes: dict[str, int] = {}
    latencies_ms: list[float] = []
    unsupported_total = 0
    unsupported_hits = 0
    mismatch_total = 0
    mismatch_hits = 0
    cases: list[dict[str, Any]] = []
    for question in questions:
        calls_before = llm_provider.generation_calls if llm_provider else 0
        started = time.perf_counter()
        response = copilot.ask(question.question, asset_id=question.selected_asset_id)
        latencies_ms.append((time.perf_counter() - started) * 1000.0)
        llm_called = bool(llm_provider and llm_provider.generation_calls > calls_before)
        response_modes[response.response_mode] = response_modes.get(response.response_mode, 0) + 1
        safety_hits += int(bool(response.safety_notice))
        if question.expected_no_answer:
            no_answer_total += 1
            matched = response.retrieval_status == question.expected_status
            no_answer_hits += int(matched)
            if question.expected_status == "unsupported_asset_type":
                unsupported_total += 1
                unsupported_hits += int(matched)
            if question.expected_status == "asset_context_mismatch":
                mismatch_total += 1
                mismatch_hits += int(matched)
        else:
            supported_total += 1
            returned_ids = {str(source.get("doc_id", "")) for source in response.sources}
            source_hits += int(bool(returned_ids.intersection(question.expected_document_ids)))
            matched = bool(returned_ids.intersection(question.expected_document_ids))
        if response.response_mode == "llm_grounded":
            generated_total += 1
            valid_citation_total += int(bool((response.citation_validation or {}).get("valid")))
        aliases = {
            str(chunk.get("citation_id"))
            for chunk in response.retrieved_chunks
            if chunk.get("citation_id")
        }
        displayed_aliases = {
            str(citation_id)
            for source in response.sources
            for citation_id in source.get("citation_ids", [])
        }
        cases.append(
            {
                "id": question.id,
                "matched_expectation": matched,
                "retrieval_status": response.retrieval_status,
                "response_mode": response.response_mode,
                "fallback_reason": response.fallback_reason,
                "evidence_status": response.evidence_status,
                "llm_called": llm_called,
                "structured_output_status": _structured_output_status(
                    llm_called=llm_called,
                    fallback_reason=response.fallback_reason,
                ),
                "citation_validation": response.citation_validation,
                "source_aliases": sorted(aliases, key=_source_alias_sort_key),
                "source_alias_mapping_valid": displayed_aliases.issubset(aliases),
                "safety_warning_present": bool(response.safety_notice),
                "escalation_required": _escalation_required(response),
            }
        )
    return {
        "mode": mode,
        "source_coverage": source_hits / (supported_total or 1),
        "no_answer_accuracy": no_answer_hits / (no_answer_total or 1),
        "safety_notice_coverage": safety_hits / (len(questions) or 1),
        "unsupported_equipment_rejection": unsupported_hits / (unsupported_total or 1),
        "asset_mismatch_detection": mismatch_hits / (mismatch_total or 1),
        "citation_validity": (valid_citation_total / generated_total if generated_total else None),
        "citation_coverage": (valid_citation_total / generated_total if generated_total else None),
        "groundedness_proxy": (
            valid_citation_total / generated_total
            if generated_total
            else source_hits / (supported_total or 1)
        ),
        "unsupported_claim_rate": None,
        "unsupported_claim_rate_note": (
            "Requires human or separately validated semantic claim labels; structural citation "
            "validity is reported instead."
        ),
        "response_modes": response_modes,
        "fallback_rate": (
            sum(count for name, count in response_modes.items() if name != "llm_grounded")
            / (len(questions) or 1)
        ),
        "deterministic_response_rate": response_modes.get("deterministic_fallback", 0)
        / (len(questions) or 1),
        "llm_response_rate": response_modes.get("llm_grounded", 0) / (len(questions) or 1),
        "latency_ms": _latency_summary(latencies_ms),
        "cases": cases,
    }


def run_evaluation(
    *,
    questions_path: Path,
    backend: Literal["in-memory-hash", "configured-qdrant"],
    mode: EvaluationMode,
) -> dict[str, Any]:
    questions = load_questions(questions_path)
    retrievers = (
        build_in_memory_retrievers()
        if backend == "in-memory-hash"
        else build_configured_retrievers()
    )
    retrieval_comparison = {
        name: evaluate_retrieval(questions, retriever) for name, retriever in retrievers.items()
    }
    retriever = retrievers["hybrid_reranked"]
    report: dict[str, Any] = {
        "dataset_version": DATASET_VERSION,
        "dataset": str(questions_path),
        "backend": backend,
        "dataset_size": len(questions),
        "limitations": [
            "Small synthetic corpus; metrics demonstrate reproducibility, not scientific generalization.",
            (
                "In-memory hash embeddings are deterministic test fixtures, not semantic production embeddings."
                if backend == "in-memory-hash"
                else "Configured Qdrant uses the operator-selected semantic embedding model and live service state."
            ),
            "Ungrounded LLM mode is intentionally excluded because the product must not generate maintenance guidance without retrieved evidence.",
        ],
        "retrieval": retrieval_comparison["hybrid_reranked"],
        "retrieval_comparison": retrieval_comparison,
    }
    if mode != "retrieval":
        report["answers"] = evaluate_answers(questions, retriever, mode=mode)
    return report


class _EvaluationAssetContextService:
    def __init__(self, questions: list[EvaluationQuestion]) -> None:
        self.asset_types = {
            question.selected_asset_id: question.selected_asset_type
            for question in questions
            if question.selected_asset_id and question.selected_asset_type
        }

    def get_asset_context(self, asset_id: str) -> dict[str, Any]:
        asset_type = self.asset_types.get(asset_id)
        if not asset_type:
            raise AssertionError(f"Unexpected asset lookup during evaluation: {asset_id}")
        return {
            "asset_id": asset_id,
            "latest_risk": {
                "asset_id": asset_id,
                "asset_name": "Thiết bị đánh giá synthetic",
                "asset_type": asset_type,
                "location": "Khu đánh giá",
            },
            "recent_anomalies": [],
        }


class _PassThroughReranker:
    def score(self, query: str, candidates: list[RetrievalResult]) -> list[float]:
        return [candidate.score for candidate in candidates]


class _LexicalReranker:
    """Deterministic test fixture, explicitly not the production cross-encoder."""

    def score(self, query: str, candidates: list[RetrievalResult]) -> list[float]:
        query_tokens = set(tokenize(query))
        return [
            len(query_tokens & set(tokenize(f"{candidate.title} {candidate.text}")))
            / (len(query_tokens) or 1)
            for candidate in candidates
        ]


class _CountingProvider:
    """Record real provider invocations without changing their behavior."""

    def __init__(self, delegate: LLMProvider) -> None:
        self.delegate = delegate
        self.provider_name = delegate.provider_name
        self.model_name = delegate.model_name
        self.generation_calls = 0

    def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        self.generation_calls += 1
        return self.delegate.generate(request)


def _structured_output_status(*, llm_called: bool, fallback_reason: str | None) -> str:
    if not llm_called:
        return "not_called"
    if fallback_reason == "invalid_llm_output":
        return "invalid"
    if fallback_reason in {"llm_timeout", "llm_unavailable", "llm_provider_error"}:
        return "provider_failure"
    return "valid"


def _escalation_required(response: Any) -> bool | None:
    if response.structured_answer is not None:
        return bool(response.structured_answer.get("escalation_required"))
    if response.fallback_reason == "llm_insufficient_evidence":
        return True
    return None


def _source_alias_sort_key(value: str) -> tuple[int, str]:
    try:
        return int(value.removeprefix("S")), value
    except ValueError:
        return 10_000, value


def _latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"average": 0.0, "p50": 0.0, "p95": 0.0}
    ordered = sorted(values)
    return {
        "average": sum(ordered) / len(ordered),
        "p50": ordered[math.ceil(len(ordered) * 0.50) - 1],
        "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render stable headline metrics while preserving detailed JSON as authority."""

    retrieval = report["retrieval"]
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- Dataset version: `{report['dataset_version']}`",
        f"- Backend: `{report['backend']}`",
        f"- Dataset size: {report['dataset_size']}",
        "",
        "## Retrieval",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Recall@1 | {retrieval['recall_at_1']:.4f} |",
        f"| Recall@3 | {retrieval['recall_at_3']:.4f} |",
        f"| Recall@5 | {retrieval['recall_at_5']:.4f} |",
        f"| MRR | {retrieval['mean_reciprocal_rank']:.4f} |",
        f"| Metadata-filter accuracy | {retrieval['asset_type_filter_accuracy']:.4f} |",
        f"| Average latency (ms) | {retrieval['latency_ms']['average']:.3f} |",
        f"| P95 latency (ms) | {retrieval['latency_ms']['p95']:.3f} |",
    ]
    if "answers" in report:
        answers = report["answers"]
        lines.extend(
            [
                "",
                "## Answers And Safety",
                "",
                f"- No-answer accuracy: {answers['no_answer_accuracy']:.4f}",
                f"- Unsupported-equipment rejection: {answers['unsupported_equipment_rejection']:.4f}",
                f"- Asset-mismatch detection: {answers['asset_mismatch_detection']:.4f}",
                f"- Citation validity: {answers['citation_validity']}",
                f"- Fallback rate: {answers['fallback_rate']:.4f}",
            ]
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--backend",
        choices=["in-memory-hash", "configured-qdrant"],
        default="in-memory-hash",
    )
    parser.add_argument(
        "--mode",
        choices=["retrieval", "deterministic", "rag-llm"],
        default="deterministic",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = run_evaluation(
        questions_path=args.questions,
        backend=args.backend,
        mode=args.mode,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    markdown_output = args.markdown_output or (
        args.output.with_suffix(".md") if args.output else None
    )
    if markdown_output:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(render_markdown_report(report), encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
