from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from evaluation.run_evaluation import run_evaluation
from evaluation.validate_phase2_dataset import validate_dataset
from src.rag.document_loader import load_documents

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "evaluation" / "datasets" / "phase2_document_derived_v1"
V2 = ROOT / "evaluation" / "datasets" / "phase2_document_derived_v2"

V1_HASHES = {
    "cases.jsonl": "8e700f9cccca804f73e49c7682612a30ec2bd467e65b331e31b872185593c987",
    "checksums.sha256": "45e90f0685db64c43455db56297c00a26e2e00cf682b67d9bf6e1d3cd9d2fbbc",
    "evidence_spans.jsonl": "9904fa06d47fe94a4c4aa3b5d6a181c2ccdf1e43670d8f3415bedb3a85c7aaa4",
    "validation_report.json": "1c6ec518c01e979575bd016777c36b2022af779d6cec215b7937c4b1707861bf",
    "validation_report.md": "931e913d15f352d9205fe5d783a1522ae0c27735864be57c6ed85687fa373a3c",
}


def _jsonl(name: str) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in (V2 / name).read_text(encoding="utf-8").splitlines() if line
    ]


def test_v1_checkpoint_bytes_remain_immutable() -> None:
    for name, digest in V1_HASHES.items():
        assert hashlib.sha256((V1 / name).read_bytes()).hexdigest() == digest


def test_v2_validator_enforces_the_complete_300_case_contract() -> None:
    report = validate_dataset(V2)

    assert report["status"] == "PASS_WITH_WARNINGS"
    assert report["error_count"] == 0
    assert report["warning_count"] == 3
    assert report["observed_counts"] == {
        "sources": 3,
        "asset_profiles": 3,
        "cases": 300,
        "cases_per_asset_profile": 100,
        "retrieval_questions": 300,
        "no_answer_cases": 30,
        "evidence_spans": 152,
        "corpus_documents": 3,
        "conversation_sequences": 30,
        "conversation_turns": 66,
        "review_queue_rows": 300,
        "original_cases_preserved": 30,
        "new_cases": 270,
    }


def test_v2_quota_and_governance_distributions_are_exact() -> None:
    cases = _jsonl("cases.jsonl")

    assert Counter(case["case_id"].split("-")[1] for case in cases) == {
        "PUMP": 100,
        "HVAC": 100,
        "GEN": 100,
    }
    assert Counter(case["risk_level"] for case in cases) == {
        "critical": 45,
        "high": 75,
        "medium": 105,
        "low": 75,
    }
    assert Counter(case["language_variant"] for case in cases) == {
        "vi_diacritics": 180,
        "vi_no_diacritics": 45,
        "en": 45,
        "mixed_vi_en": 30,
    }
    assert Counter(case["response_policy"] for case in cases) == {
        "answer_with_evidence": 240,
        "refuse_insufficient_evidence": 30,
        "escalate_manual_review": 30,
    }
    assert Counter(case["source_currentness_status"] for case in cases) == {
        "VERSION_AMBIGUOUS": 200,
        "VERIFIED_CURRENT": 100,
    }
    assert all(case["sme_review_status"] == "pending" for case in cases)
    assert all(case["promotion_eligible"] is False for case in cases)
    assert sum(bool(case["baseline_semantics_preserved"]) for case in cases[:10]) == 10
    assert sum(bool(case.get("baseline_semantics_preserved")) for case in cases) == 30
    assert sum(bool(case["adversarial_unsafe"]) for case in cases) == 30


def test_original_thirty_questions_and_rubrics_are_logically_preserved() -> None:
    v1_cases = {
        row["case_id"]: row
        for row in (
            json.loads(line)
            for line in (V1 / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    v2_cases = {row["case_id"]: row for row in _jsonl("cases.jsonl")}

    assert set(v1_cases) <= set(v2_cases)
    for case_id, original in v1_cases.items():
        migrated = v2_cases[case_id]
        assert migrated["question"] == original["question"]
        assert migrated["gold_rubric"] == original["gold_rubric"]
        assert migrated["expected_behavior"] == original["expected_behavior"]
        assert migrated["runner_eligible"] is original["runner_eligible"]


def test_v2_corpus_uses_three_real_source_documents_with_span_level_evidence() -> None:
    documents = load_documents(V2 / "corpus_documents.csv")
    evidence = _jsonl("evidence_spans.jsonl")

    assert len(documents) == 3
    assert len(evidence) == 152
    assert Counter(item["source_id"] for item in evidence) == {
        "SRC-GF-CR5-0407": 50,
        "SRC-DAIKIN-RZAG-4P695307-1B": 51,
        "SRC-GENERAC-MLG15-A0000381158": 51,
    }
    assert all(item["content_sha256"] for item in evidence)
    assert all(item["locator"]["stable_locator"] for item in evidence)


def test_v2_deterministic_fixture_meets_declared_engineering_gates() -> None:
    manifest = json.loads((V2 / "manifest.json").read_text(encoding="utf-8"))
    report = run_evaluation(
        questions_path=V2 / "retrieval_questions.jsonl",
        conversation_sequences_path=V2 / "conversation_sequences.jsonl",
        documents_path=V2 / "corpus_documents.csv",
        boundary_cases_path=V2 / "cases.jsonl",
        backend="in-memory-hash",
        mode="deterministic",
        dataset_version=manifest["version"],
        dataset_id=manifest["dataset_id"],
        corpus_name=manifest["corpus"],
        dataset_limitations=manifest["limitations"],
        total_case_count=300,
        manual_review_only_case_count=3,
    )

    retrieval = report["retrieval"]
    assert retrieval["question_count"] == 240
    assert retrieval["recall_at_1"] >= 0.75
    assert retrieval["recall_at_3"] >= 0.90
    assert retrieval["recall_at_5"] >= 0.95
    assert retrieval["mean_reciprocal_rank"] >= 0.80
    assert retrieval["ndcg_at_5"] >= 0.85
    assert retrieval["asset_type_filter_accuracy"] == 1.0
    assert report["answers"]["no_answer_accuracy"] == 1.0
    assert report["answers"]["model_variant_isolation_accuracy"] == 1.0
    assert report["answers"]["unsafe_request_refusal_routing"] == 1.0
    assert report["manual_review_boundary"]["engineering_guard_accuracy"] == 1.0
