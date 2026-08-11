"""Tests for the small reproducible RAG/LLM evaluation harness."""

from pathlib import Path

import pytest

from evaluation.run_evaluation import (
    EvaluationQuestion,
    evaluate_retrieval,
    load_conversation_sequences,
    load_questions,
    render_markdown_report,
    run_evaluation,
)
from src.rag.retriever import RetrievalResult


def test_evaluation_dataset_is_supported_by_the_repository_corpus() -> None:
    questions = load_questions()
    sequences = load_conversation_sequences()

    assert len(questions) == 31
    assert {document_id for row in questions for document_id in row.expected_document_ids} == {
        "DOC-001",
        "DOC-002",
        "DOC-003",
        "DOC-004",
        "DOC-005",
        "DOC-006",
    }
    assert len(sequences) == 3
    assert sum(len(sequence.turns) for sequence in sequences) == 6


def test_in_memory_evaluation_is_reproducible_and_reports_limitations() -> None:
    first = run_evaluation(
        questions_path=Path("evaluation/rag_questions.jsonl"),
        backend="in-memory-hash",
        mode="deterministic",
    )
    second = run_evaluation(
        questions_path=Path("evaluation/rag_questions.jsonl"),
        backend="in-memory-hash",
        mode="deterministic",
    )

    assert _without_latency(first) == _without_latency(second)
    assert first["dataset_version"] == "3.0.0"
    assert first["retrieval"]["question_count"] == 21
    assert first["retrieval"]["recall_at_1"] >= 0.90
    assert first["retrieval"]["recall_at_5"] == 1.0
    assert first["retrieval"]["ndcg_at_5"] >= 0.95
    assert first["retrieval"]["asset_type_filter_accuracy"] == 1.0
    assert set(first["retrieval_comparison"]) == {
        "dense_only",
        "sparse_only",
        "hybrid",
        "hybrid_reranked",
    }
    assert first["retrieval"]["latency_ms"]["p95"] >= 0
    assert first["answers"]["no_answer_accuracy"] == 1.0
    assert first["answers"]["unsupported_equipment_rejection"] == 1.0
    assert first["answers"]["asset_mismatch_detection"] == 1.0
    assert first["answers"]["routing_status_accuracy"] == 1.0
    assert first["answers"]["intent_accuracy"] == 1.0
    assert first["answers"]["multi_turn_resolution_accuracy"] == 1.0
    assert first["answers"]["static_context_resolution_accuracy"] == 1.0
    assert first["answers"]["filter_relaxation_accuracy"] == 1.0
    assert first["answers"]["source_precision"] >= 0.95
    assert first["answers"]["fallback_rate"] == 1.0
    assert first["answers"]["unsupported_claim_rate"] is None
    assert all(not case["llm_called"] for case in first["answers"]["cases"])
    assert all(
        case["structured_output_status"] == "not_called" for case in first["answers"]["cases"]
    )
    assert all(case["source_alias_mapping_valid"] for case in first["answers"]["cases"])
    assert any("In-memory hash embeddings" in item for item in first["limitations"])
    assert first["limitations"]
    assert first["conversation_sequences"]["follow_up_count"] == 3
    assert all(
        turn["used_previous_backend_state"]
        for case in first["conversation_sequences"]["cases"]
        for turn in case["turns"][1:]
    )
    assert "# RAG Evaluation Report" in render_markdown_report(first)


def test_recall_at_k_uses_fractional_multi_relevant_denominator() -> None:
    question = EvaluationQuestion(
        id="multi-relevant",
        question="Checklist máy lạnh gồm những gì?",
        asset_type="Máy lạnh",
        expected_document_ids=("DOC-A", "DOC-B", "DOC-A"),
        expected_no_answer=False,
    )
    report = evaluate_retrieval(
        [question],
        _StaticRetriever(
            [
                _retrieval("DOC-A", "DOC-A-1"),
                _retrieval("DOC-A", "DOC-A-2"),
                _retrieval("DOC-B", "DOC-B-1"),
            ]
        ),
    )

    assert report["recall_at_1"] == 0.5
    assert report["recall_at_3"] == 1.0
    assert report["recall_at_5"] == 1.0


def test_supported_retrieval_case_requires_relevant_document_ids() -> None:
    question = EvaluationQuestion(
        id="invalid-empty-relevant",
        question="Checklist máy lạnh gồm những gì?",
        asset_type="Máy lạnh",
        expected_document_ids=(),
        expected_no_answer=False,
    )

    with pytest.raises(ValueError, match="requires relevant document IDs"):
        evaluate_retrieval([question], _StaticRetriever([]))


def test_multi_turn_metric_fails_when_backend_state_generation_is_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.rag.copilot.build_conversation_state", lambda **kwargs: None)

    report = run_evaluation(
        questions_path=Path("evaluation/rag_questions.jsonl"),
        backend="in-memory-hash",
        mode="deterministic",
    )

    assert report["answers"]["static_context_resolution_accuracy"] == 1.0
    assert report["answers"]["multi_turn_resolution_accuracy"] == 0.0
    assert all(
        not turn["used_previous_backend_state"]
        for case in report["conversation_sequences"]["cases"]
        for turn in case["turns"][1:]
    )


def _without_latency(value):
    if isinstance(value, dict):
        return {
            key: _without_latency(item)
            for key, item in value.items()
            if not key.endswith("latency_ms")
        }
    if isinstance(value, list):
        return [_without_latency(item) for item in value]
    return value


class _StaticRetriever:
    minimum_relevance_score = 0.1

    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results

    def search(self, query: str, limit: int = 5, **filters):
        return self.results[:limit]


def _retrieval(document_id: str, chunk_id: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        doc_id=document_id,
        title=f"Tài liệu {document_id}",
        doc_type="Danh sách kiểm tra",
        asset_type="Máy lạnh",
        source="Nguồn kiểm thử",
        text="Kiểm tra máy lạnh theo checklist.",
        score=0.9,
    )
