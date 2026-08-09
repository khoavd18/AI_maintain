"""Tests for the small reproducible RAG/LLM evaluation harness."""

from pathlib import Path

from evaluation.run_evaluation import load_questions, render_markdown_report, run_evaluation


def test_evaluation_dataset_is_supported_by_the_repository_corpus() -> None:
    questions = load_questions()

    assert len(questions) == 11
    assert {document_id for row in questions for document_id in row.expected_document_ids} == {
        "DOC-001",
        "DOC-002",
        "DOC-003",
        "DOC-004",
        "DOC-005",
        "DOC-006",
    }


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
    assert first["dataset_version"] == "2.0.0"
    assert first["retrieval"]["question_count"] == 6
    assert first["retrieval"]["recall_at_5"] == 1.0
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
    assert first["answers"]["fallback_rate"] == 1.0
    assert first["answers"]["unsupported_claim_rate"] is None
    assert all(not case["llm_called"] for case in first["answers"]["cases"])
    assert all(
        case["structured_output_status"] == "not_called" for case in first["answers"]["cases"]
    )
    assert all(case["source_alias_mapping_valid"] for case in first["answers"]["cases"])
    assert any("In-memory hash embeddings" in item for item in first["limitations"])
    assert first["limitations"]
    assert "# RAG Evaluation Report" in render_markdown_report(first)


def _without_latency(value):
    if isinstance(value, dict):
        return {key: _without_latency(item) for key, item in value.items() if key != "latency_ms"}
    if isinstance(value, list):
        return [_without_latency(item) for item in value]
    return value
