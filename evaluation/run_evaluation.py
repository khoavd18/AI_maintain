"""Run small, reproducible retrieval and answer-safety evaluations."""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from qdrant_client import QdrantClient

from src.config.settings import get_settings
from src.llm.base import LLMGenerationRequest, LLMGenerationResult, LLMProvider
from src.llm.provider_factory import create_llm_provider
from src.rag.application.request_analysis import RequestAnalysisService
from src.rag.chunking import chunk_documents
from src.rag.copilot import CopilotGenerationConfig, MaintenanceCopilot
from src.rag.document_loader import RAW_DOCUMENT_FILE, load_documents
from src.rag.embeddings import HashEmbeddingProvider, create_embedding_provider
from src.rag.hybrid_retriever import HybridRetrievalConfig, HybridRetriever
from src.rag.query_analysis import QueryAnalyzer
from src.rag.reranking import CrossEncoderReranker
from src.rag.retriever import QdrantRetriever, RetrievalResult, Retriever
from src.rag.sparse_search import BM25Index, QdrantBM25Retriever, tokenize
from src.rag.vector_store import QdrantVectorStore

DEFAULT_DATASET = Path("evaluation/rag_questions.jsonl")
DEFAULT_CONVERSATION_DATASET = Path("evaluation/rag_conversation_sequences.jsonl")
DATASET_VERSION = "3.0.0"
EvaluationMode = Literal["retrieval", "deterministic", "rag-llm"]


@dataclass(frozen=True)
class EvaluationQuestion:
    id: str
    question: str
    asset_type: str | None
    expected_document_ids: tuple[str, ...]
    expected_no_answer: bool
    expected_status: str | None = None
    expected_intent: str | None = None
    selected_asset_id: str | None = None
    selected_asset_type: str | None = None
    document_type: str | None = None
    failure_category: str | None = None
    version: str | None = None
    language: str | None = None
    conversation_context: dict[str, Any] | None = None
    expected_relaxation: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationConversationTurn:
    question: str
    expected_document_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationConversationSequence:
    id: str
    turns: tuple[EvaluationConversationTurn, ...]


@dataclass(frozen=True)
class EvaluationBoundaryCase:
    """One manual-review case executed outside retrieval ranking metrics."""

    id: str
    question: str
    expected_status: str
    selected_asset_id: str
    selected_asset_type: str
    manufacturer: str
    model_scope: str


_BOUNDARY_STATUS_BY_BEHAVIOR = {
    "clarify_before_answer": "parameter_confirmation_required",
    "refuse_model_mismatch_and_request_source": "model_context_mismatch",
    "insufficient_evidence_request_engine_manual": "parameter_confirmation_required",
}


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
                    expected_intent=value.get("expected_intent"),
                    selected_asset_id=value.get("selected_asset_id"),
                    selected_asset_type=value.get("selected_asset_type"),
                    document_type=value.get("document_type"),
                    failure_category=value.get("failure_category"),
                    version=value.get("version"),
                    language=value.get("language"),
                    conversation_context=value.get("conversation_context"),
                    expected_relaxation=tuple(value.get("expected_relaxation", [])),
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid evaluation row at line {line_number}.") from exc
    if not questions:
        raise ValueError("Evaluation dataset is empty.")
    return questions


def load_conversation_sequences(
    path: Path = DEFAULT_CONVERSATION_DATASET,
) -> list[EvaluationConversationSequence]:
    """Load real ordered turns whose state must come from the preceding backend response."""

    sequences: list[EvaluationConversationSequence] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            turns = tuple(
                EvaluationConversationTurn(
                    question=str(turn["question"]),
                    expected_document_ids=tuple(
                        dict.fromkeys(str(item) for item in turn["expected_document_ids"])
                    ),
                )
                for turn in value["turns"]
            )
            if len(turns) < 2 or any(not turn.expected_document_ids for turn in turns):
                raise ValueError("Conversation sequences require two grounded turns.")
            sequences.append(
                EvaluationConversationSequence(
                    id=str(value["id"]),
                    turns=turns,
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid conversation sequence at line {line_number}.") from exc
    if not sequences:
        raise ValueError("Conversation sequence dataset is empty.")
    return sequences


def load_boundary_cases(path: Path) -> list[EvaluationBoundaryCase]:
    """Load manual-only safety boundaries without adding them to retrieval recall."""

    cases: list[EvaluationBoundaryCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if bool(value["runner_eligible"]):
                continue
            profile = value["asset_profile"]
            expected_status = _BOUNDARY_STATUS_BY_BEHAVIOR[str(value["expected_behavior"])]
            cases.append(
                EvaluationBoundaryCase(
                    id=str(value["case_id"]),
                    question=str(value["question"]),
                    expected_status=expected_status,
                    selected_asset_id=str(profile["asset_profile_id"]),
                    selected_asset_type=str(profile["asset_type"]),
                    manufacturer=str(profile["manufacturer"]),
                    model_scope=str(profile["model_scope"]),
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid boundary evaluation row at line {line_number}.") from exc
    return cases


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
    sparse = QdrantBM25Retriever(
        store,
        max_chunks=settings.rag_sparse_max_chunks,
        refresh_interval_seconds=settings.rag_sparse_refresh_seconds,
    )
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
    ndcg_scores: list[float] = []
    recall_scores = {1: 0.0, 3: 0.0, 5: 0.0}
    filter_correct = 0
    cases: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    request_analysis = RequestAnalysisService(
        asset_context_provider=_EvaluationAssetContextService(questions),
        query_analyzer=QueryAnalyzer(),
    )
    for question in supported:
        prepared = request_analysis.prepare(
            question=question.question,
            asset_id=question.selected_asset_id,
            document_type=question.document_type,
            failure_category=question.failure_category,
            version=question.version,
            language=question.language,
            conversation_context=question.conversation_context,
        )
        if prepared.early_status is not None:
            raise AssertionError(
                f"Supported evaluation row {question.id} routed to {prepared.early_status}."
            )
        started = time.perf_counter()
        results = retriever.search(
            prepared.retrieval_query or question.question,
            limit=5,
            asset_type=prepared.filters.get("asset_type") or question.asset_type,
        )
        latencies_ms.append((time.perf_counter() - started) * 1000.0)
        ranked_ids = list(dict.fromkeys(result.doc_id for result in results if result.doc_id))
        expected = set(question.expected_document_ids)
        if not expected:
            raise ValueError(
                f"Supported evaluation row {question.id} requires relevant document IDs."
            )
        rank = next(
            (
                index
                for index, document_id in enumerate(ranked_ids, start=1)
                if document_id in expected
            ),
            None,
        )
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        gains = [1.0 if document_id in expected else 0.0 for document_id in ranked_ids[:5]]
        dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
        ideal_gains = [1.0] * min(len(expected), 5)
        ideal_dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(ideal_gains))
        ndcg_scores.append(dcg / ideal_dcg if ideal_dcg else 0.0)
        for k in recall_scores:
            recall_scores[k] += len(expected.intersection(ranked_ids[:k])) / len(expected)
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
        "recall_at_1": recall_scores[1] / denominator,
        "recall_at_3": recall_scores[3] / denominator,
        "recall_at_5": recall_scores[5] / denominator,
        "mean_reciprocal_rank": sum(reciprocal_ranks) / denominator,
        "ndcg_at_5": sum(ndcg_scores) / denominator,
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
    returned_source_count = 0
    relevant_source_count = 0
    no_answer_total = 0
    no_answer_hits = 0
    safety_hits = 0
    generated_total = 0
    valid_citation_total = 0
    response_modes: dict[str, int] = {}
    fallback_reasons: dict[str, int] = {}
    latencies_ms: list[float] = []
    stage_latencies: dict[str, list[float]] = {
        stage: [] for stage in ("routing", "retrieval", "reranking", "generation", "total")
    }
    unsupported_total = 0
    unsupported_hits = 0
    mismatch_total = 0
    mismatch_hits = 0
    intent_total = 0
    intent_hits = 0
    routing_hits = 0
    static_context_total = 0
    static_context_hits = 0
    relaxation_total = 0
    relaxation_hits = 0
    canonicalization_count = 0
    cases: list[dict[str, Any]] = []
    for question in questions:
        calls_before = llm_provider.generation_calls if llm_provider else 0
        started = time.perf_counter()
        response = copilot.ask(
            question.question,
            asset_id=question.selected_asset_id,
            document_type=question.document_type,
            failure_category=question.failure_category,
            version=question.version,
            language=question.language,
            conversation_context=question.conversation_context,
            request_id=f"evaluation-{question.id}",
        )
        latencies_ms.append((time.perf_counter() - started) * 1000.0)
        for stage, value in (response.diagnostics.get("latency_ms") or {}).items():
            if stage in stage_latencies and isinstance(value, (int, float)):
                stage_latencies[stage].append(float(value))
        llm_called = bool(llm_provider and llm_provider.generation_calls > calls_before)
        response_modes[response.response_mode] = response_modes.get(response.response_mode, 0) + 1
        if response.fallback_reason:
            fallback_reasons[response.fallback_reason] = (
                fallback_reasons.get(response.fallback_reason, 0) + 1
            )
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
            returned_source_count += len(returned_ids)
            relevant_source_count += len(returned_ids.intersection(question.expected_document_ids))
            source_hits += int(bool(returned_ids.intersection(question.expected_document_ids)))
            matched = bool(returned_ids.intersection(question.expected_document_ids))
        expected_route_status = question.expected_status or "success"
        routing_matched = response.retrieval_status == expected_route_status
        routing_hits += int(routing_matched)
        observed_intent = response.diagnostics.get("intent")
        if question.expected_intent:
            intent_total += 1
            intent_hits += int(observed_intent == question.expected_intent)
        if question.conversation_context is not None:
            static_context_total += 1
            static_context_hits += int(matched)
        if question.expected_relaxation:
            relaxation_total += 1
            relaxation_hits += int(
                tuple(response.diagnostics.get("relaxation_steps") or ())
                == question.expected_relaxation
                and matched
            )
        if response.response_mode == "llm_grounded":
            generated_total += 1
            valid_citation_total += int(bool((response.citation_validation or {}).get("valid")))
            canonicalization_count += int(
                bool((response.citation_validation or {}).get("source_ids_canonicalized"))
            )
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
                "routing_matched": routing_matched,
                "observed_intent": observed_intent,
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
                "relaxation_steps": response.diagnostics.get("relaxation_steps", []),
                "stage_latency_ms": response.diagnostics.get("latency_ms", {}),
            }
        )
    return {
        "mode": mode,
        "source_coverage": source_hits / (supported_total or 1),
        "source_precision": relevant_source_count / (returned_source_count or 1),
        "routing_status_accuracy": routing_hits / (len(questions) or 1),
        "intent_accuracy": _ratio_or_none(intent_hits, intent_total),
        "no_answer_accuracy": _ratio_or_none(no_answer_hits, no_answer_total),
        "safety_notice_coverage": safety_hits / (len(questions) or 1),
        "unsupported_equipment_rejection": _ratio_or_none(unsupported_hits, unsupported_total),
        "asset_mismatch_detection": _ratio_or_none(mismatch_hits, mismatch_total),
        "static_context_resolution_accuracy": _ratio_or_none(
            static_context_hits, static_context_total
        ),
        "filter_relaxation_accuracy": _ratio_or_none(relaxation_hits, relaxation_total),
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
        "fallback_reasons": fallback_reasons,
        "citation_canonicalization_count": canonicalization_count,
        "fallback_rate": (
            sum(count for name, count in response_modes.items() if name != "llm_grounded")
            / (len(questions) or 1)
        ),
        "deterministic_response_rate": response_modes.get("deterministic_fallback", 0)
        / (len(questions) or 1),
        "llm_response_rate": response_modes.get("llm_grounded", 0) / (len(questions) or 1),
        "latency_ms": _latency_summary(latencies_ms),
        "stage_latency_ms": {
            stage: _latency_summary(values) for stage, values in stage_latencies.items()
        },
        "cases": cases,
    }


def evaluate_conversation_sequences(
    sequences: list[EvaluationConversationSequence],
    retriever: Retriever,
    *,
    mode: EvaluationMode,
) -> dict[str, Any]:
    """Evaluate follow-ups using only state emitted by the preceding backend response."""

    settings = get_settings()
    provider = create_llm_provider(settings) if mode == "rag-llm" else None
    if mode == "rag-llm" and provider is None:
        raise ValueError("rag-llm mode requires LLM_ENABLED=true and explicit provider settings.")
    copilot = MaintenanceCopilot(
        _EvaluationAssetContextService([]),
        retriever,
        provider,
        CopilotGenerationConfig(
            enabled=mode == "rag-llm",
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_context_chars=settings.llm_max_context_chars,
            min_relevant_documents=settings.llm_min_relevant_documents,
        ),
    )
    follow_up_total = 0
    follow_up_hits = 0
    turn_total = 0
    cases: list[dict[str, Any]] = []
    for sequence in sequences:
        conversation_state: dict[str, Any] | None = None
        turns: list[dict[str, Any]] = []
        for turn_index, turn in enumerate(sequence.turns):
            supplied_state = conversation_state
            response = copilot.ask(
                turn.question,
                conversation_context=supplied_state,
                request_id=f"evaluation-sequence-{sequence.id}-{turn_index + 1}",
            )
            returned_ids = {str(source.get("doc_id", "")) for source in response.sources}
            matched = bool(returned_ids.intersection(turn.expected_document_ids))
            if turn_index > 0:
                follow_up_total += 1
                follow_up_hits += int(matched and supplied_state is not None)
            turn_total += 1
            turns.append(
                {
                    "turn": turn_index + 1,
                    "matched_expectation": matched,
                    "used_previous_backend_state": turn_index > 0 and supplied_state is not None,
                    "backend_state_emitted": response.conversation_state is not None,
                    "retrieval_status": response.retrieval_status,
                    "response_mode": response.response_mode,
                }
            )
            conversation_state = response.conversation_state
        cases.append({"id": sequence.id, "turns": turns})
    return {
        "sequence_count": len(sequences),
        "turn_count": turn_total,
        "follow_up_count": follow_up_total,
        "follow_up_accuracy": follow_up_hits / follow_up_total if follow_up_total else None,
        "cases": cases,
    }


def evaluate_boundary_cases(
    cases: list[EvaluationBoundaryCase],
    retriever: Retriever,
) -> dict[str, Any]:
    """Execute manual-review safety routes without changing retrieval denominators."""

    copilot = MaintenanceCopilot(
        _EvaluationBoundaryAssetContextService(cases),
        retriever,
        generation_config=CopilotGenerationConfig(enabled=False),
    )
    matched_total = 0
    isolated_total = 0
    results: list[dict[str, Any]] = []
    for case in cases:
        response = copilot.ask(
            case.question,
            asset_id=case.selected_asset_id,
            request_id=f"evaluation-boundary-{case.id}",
        )
        matched = response.retrieval_status == case.expected_status
        evidence_isolated = not response.sources and not response.retrieved_chunks
        matched_total += int(matched)
        isolated_total += int(evidence_isolated)
        results.append(
            {
                "id": case.id,
                "expected_status": case.expected_status,
                "observed_status": response.retrieval_status,
                "fallback_reason": response.fallback_reason,
                "matched_expectation": matched,
                "evidence_isolated": evidence_isolated,
                "safety_warning_present": bool(response.safety_notice),
            }
        )
    return {
        "case_count": len(cases),
        "engineering_guard_accuracy": _ratio_or_none(matched_total, len(cases)),
        "evidence_isolation_accuracy": _ratio_or_none(isolated_total, len(cases)),
        "sme_approval_accuracy": None,
        "sme_approval_reason": "All manual-review cases remain pending qualified SME review.",
        "cases": results,
    }


def run_evaluation(
    *,
    questions_path: Path,
    backend: Literal["in-memory-hash", "configured-qdrant"],
    mode: EvaluationMode,
    conversation_sequences_path: Path = DEFAULT_CONVERSATION_DATASET,
    documents_path: Path = RAW_DOCUMENT_FILE,
    dataset_version: str = DATASET_VERSION,
    dataset_id: str | None = None,
    corpus_name: str | None = None,
    dataset_limitations: list[str] | None = None,
    boundary_cases_path: Path | None = None,
    provenance_type: str | None = None,
    approval_state: str | None = None,
    readiness: str | None = None,
    total_case_count: int | None = None,
    manual_review_only_case_count: int | None = None,
) -> dict[str, Any]:
    questions = load_questions(questions_path)
    conversation_sequences = load_conversation_sequences(conversation_sequences_path)
    boundary_cases = load_boundary_cases(boundary_cases_path) if boundary_cases_path else []
    retrievers = (
        build_in_memory_retrievers(documents_path)
        if backend == "in-memory-hash"
        else build_configured_retrievers()
    )
    retrieval_comparison = {
        name: evaluate_retrieval(questions, retriever) for name, retriever in retrievers.items()
    }
    retriever = retrievers["hybrid_reranked"]
    limitations = list(
        dataset_limitations
        or [
            "Small synthetic corpus; metrics demonstrate reproducibility, not scientific generalization."
        ]
    )
    limitations.extend(
        [
            (
                "In-memory hash embeddings are deterministic test fixtures, not semantic production embeddings."
                if backend == "in-memory-hash"
                else "Configured Qdrant uses the operator-selected semantic embedding model and live service state."
            ),
            "Ungrounded LLM mode is intentionally excluded because the product must not generate maintenance guidance without retrieved evidence.",
        ]
    )
    report: dict[str, Any] = {
        "dataset_version": dataset_version,
        "dataset_id": dataset_id,
        "provenance_type": provenance_type,
        "approval_state": approval_state,
        "readiness": readiness,
        "corpus": corpus_name,
        "dataset": str(questions_path),
        "documents": str(documents_path) if backend == "in-memory-hash" else None,
        "backend": backend,
        "dataset_size": len(questions),
        "case_counts": {
            "total": total_case_count or len(questions) + len(boundary_cases),
            "retrieval_eligible": len(questions),
            "manual_review_only": manual_review_only_case_count or len(boundary_cases),
        },
        "conversation_sequence_count": len(conversation_sequences),
        "configuration": _evaluation_configuration(backend=backend, mode=mode),
        "limitations": list(dict.fromkeys(limitations)),
        "retrieval": retrieval_comparison["hybrid_reranked"],
        "retrieval_comparison": retrieval_comparison,
        "manual_review_boundary": evaluate_boundary_cases(boundary_cases, retriever)
        if boundary_cases
        else None,
        "skipped_metrics": _skipped_metrics(mode),
    }
    if mode != "retrieval":
        answers = evaluate_answers(questions, retriever, mode=mode)
        conversation_report = evaluate_conversation_sequences(
            conversation_sequences,
            retriever,
            mode=mode,
        )
        answers["multi_turn_resolution_accuracy"] = conversation_report["follow_up_accuracy"]
        report["answers"] = answers
        report["conversation_sequences"] = conversation_report
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


class _EvaluationBoundaryAssetContextService:
    def __init__(self, cases: list[EvaluationBoundaryCase]) -> None:
        self.cases = {case.selected_asset_id: case for case in cases}

    def get_asset_context(self, asset_id: str) -> dict[str, Any]:
        case = self.cases.get(asset_id)
        if case is None:
            raise AssertionError(f"Unexpected boundary asset lookup during evaluation: {asset_id}")
        return {
            "asset_id": asset_id,
            "asset_profile": {
                "asset_id": asset_id,
                "asset_type": case.selected_asset_type,
                "manufacturer": case.manufacturer,
                "model": case.model_scope,
            },
            "latest_risk": {
                "asset_id": asset_id,
                "asset_name": "Thiết bị đánh giá",
                "asset_type": case.selected_asset_type,
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


def _ratio_or_none(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _evaluation_configuration(
    *,
    backend: Literal["in-memory-hash", "configured-qdrant"],
    mode: EvaluationMode,
) -> dict[str, Any]:
    """Report effective non-secret evaluation settings."""

    settings = get_settings()
    return {
        "backend": backend,
        "mode": mode,
        "embedding": (
            "HashEmbeddingProvider(dimensions=384)"
            if backend == "in-memory-hash"
            else settings.embedding_model_name
        ),
        "reranker": (
            "deterministic_lexical_fixture"
            if backend == "in-memory-hash"
            else settings.rag_reranker_model
        ),
        "collection": settings.qdrant_collection if backend == "configured-qdrant" else None,
        "llm_provider": settings.llm_provider if mode == "rag-llm" else None,
        "llm_model": settings.llm_model if mode == "rag-llm" else None,
        "secrets_included": False,
    }


def _skipped_metrics(mode: EvaluationMode) -> dict[str, str]:
    skipped = {
        "unsupported_claim_rate": (
            "Requires SME-approved semantic claim labels; structural citation checks are separate."
        )
    }
    if mode == "retrieval":
        skipped.update(
            {
                "grounded_generation": "mode=retrieval does not invoke a generation provider.",
                "citation_validation": "No generated claims exist in mode=retrieval.",
                "multi_turn": "Conversation execution is reported only in deterministic or rag-llm mode.",
                "provider_unavailable_fallback": "No provider is configured or called in mode=retrieval.",
            }
        )
    elif mode == "deterministic":
        skipped.update(
            {
                "citation_validation": (
                    "Deterministic fallback exposes retrieved sources but creates no provider claims."
                ),
                "live_provider": "mode=deterministic does not call the configured LLM provider.",
            }
        )
    return skipped


def _format_optional_metric(value: object) -> str:
    return f"{value:.4f}" if isinstance(value, (int, float)) else "n/a"


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render stable headline metrics while preserving detailed JSON as authority."""

    retrieval = report["retrieval"]
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- Dataset version: `{report['dataset_version']}`",
        f"- Provenance: `{report.get('provenance_type') or 'not_declared'}`",
        f"- Approval state: `{report.get('approval_state') or 'not_declared'}`",
        f"- Readiness: `{report.get('readiness') or 'not_declared'}`",
        f"- Backend: `{report['backend']}`",
        f"- Total cases: {report['case_counts']['total']}",
        f"- Retrieval-eligible cases: {report['case_counts']['retrieval_eligible']}",
        f"- Manual-review-only cases: {report['case_counts']['manual_review_only']}",
        f"- Embedding: `{report['configuration']['embedding']}`",
        f"- Reranker: `{report['configuration']['reranker']}`",
        f"- LLM provider used: `{report['configuration']['llm_provider'] or 'none'}`",
        "",
        "## Retrieval",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Recall@1 | {retrieval['recall_at_1']:.4f} |",
        f"| Recall@3 | {retrieval['recall_at_3']:.4f} |",
        f"| Recall@5 | {retrieval['recall_at_5']:.4f} |",
        f"| MRR | {retrieval['mean_reciprocal_rank']:.4f} |",
        f"| NDCG@5 | {retrieval['ndcg_at_5']:.4f} |",
        f"| Metadata-filter accuracy | {retrieval['asset_type_filter_accuracy']:.4f} |",
        f"| Average latency (ms) | {retrieval['latency_ms']['average']:.3f} |",
        f"| P50 latency (ms) | {retrieval['latency_ms']['p50']:.3f} |",
        f"| P95 latency (ms) | {retrieval['latency_ms']['p95']:.3f} |",
    ]
    if "answers" in report:
        answers = report["answers"]
        lines.extend(
            [
                "",
                "## Answers And Safety",
                "",
                f"- No-answer accuracy: {_format_optional_metric(answers['no_answer_accuracy'])}",
                f"- Routing/status accuracy: {answers['routing_status_accuracy']:.4f}",
                f"- Intent accuracy: {_format_optional_metric(answers['intent_accuracy'])}",
                f"- Source precision: {answers['source_precision']:.4f}",
                f"- Source coverage: {answers['source_coverage']:.4f}",
                f"- Multi-turn resolution: {answers['multi_turn_resolution_accuracy']:.4f}",
                f"- Filter relaxation: {_format_optional_metric(answers['filter_relaxation_accuracy'])}",
                (
                    "- Unsupported-equipment rejection: "
                    f"{_format_optional_metric(answers['unsupported_equipment_rejection'])}"
                ),
                (
                    "- Asset-mismatch detection: "
                    f"{_format_optional_metric(answers['asset_mismatch_detection'])}"
                ),
                f"- Citation validity: {_format_optional_metric(answers['citation_validity'])}",
                f"- Fallback rate: {answers['fallback_rate']:.4f}",
            ]
        )
    boundary = report.get("manual_review_boundary")
    if boundary:
        lines.extend(
            [
                "",
                "## Manual Review Boundaries",
                "",
                (
                    "- Engineering guard accuracy: "
                    f"{_format_optional_metric(boundary['engineering_guard_accuracy'])}"
                ),
                (
                    "- Evidence isolation accuracy: "
                    f"{_format_optional_metric(boundary['evidence_isolation_accuracy'])}"
                ),
                "- SME approval accuracy: n/a",
                f"- SME gate: {boundary['sme_approval_reason']}",
            ]
        )
    lines.extend(["", "## Skipped Metrics", ""])
    lines.extend(f"- {name}: n/a — {reason}" for name, reason in report["skipped_metrics"].items())
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
    parser.add_argument(
        "--conversation-sequences",
        type=Path,
        default=DEFAULT_CONVERSATION_DATASET,
    )
    parser.add_argument("--documents", type=Path, default=RAW_DOCUMENT_FILE)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional dataset manifest providing version, identity, corpus, and limitations.",
    )
    parser.add_argument(
        "--boundary-cases",
        type=Path,
        help="Optional complete case file; manual-only cases are reported outside retrieval metrics.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    metadata = _load_dataset_metadata(args.manifest) if args.manifest else {}
    manifest_files = metadata.get("files") if isinstance(metadata.get("files"), dict) else {}
    manifest_counts = metadata.get("counts") if isinstance(metadata.get("counts"), dict) else {}
    boundary_cases_path = args.boundary_cases
    if boundary_cases_path is None and args.manifest and isinstance(manifest_files, dict):
        cases_name = _optional_text(manifest_files.get("cases"))
        if cases_name:
            boundary_cases_path = args.manifest.parent / cases_name
    report = run_evaluation(
        questions_path=args.questions,
        backend=args.backend,
        mode=args.mode,
        conversation_sequences_path=args.conversation_sequences,
        documents_path=args.documents,
        dataset_version=str(metadata.get("version") or DATASET_VERSION),
        dataset_id=_optional_text(metadata.get("dataset_id")),
        corpus_name=_optional_text(metadata.get("corpus")),
        dataset_limitations=_string_list(metadata.get("limitations")),
        boundary_cases_path=boundary_cases_path,
        provenance_type=_optional_text(metadata.get("provenance_type")),
        approval_state=_optional_text(metadata.get("approval_state")),
        readiness=_optional_text(metadata.get("readiness")),
        total_case_count=_optional_int(manifest_counts.get("cases")),
        manual_review_only_case_count=_optional_int(
            manifest_counts.get("manual_review_only_cases")
        ),
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


def _load_dataset_metadata(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load evaluation manifest: {path}") from exc
    if not isinstance(value, dict):
        raise TypeError("Evaluation manifest must be one JSON object.")
    if "version" in value and not isinstance(value["version"], str):
        raise TypeError("Evaluation manifest version must be a string.")
    if "limitations" in value:
        limitations = value["limitations"]
        if not isinstance(limitations, list) or not all(
            isinstance(item, str) and item.strip() for item in limitations
        ):
            raise TypeError("Evaluation manifest limitations must be a list of non-empty strings.")
    return value


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


if __name__ == "__main__":
    main()
