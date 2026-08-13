"""Regression coverage for the bounded evidence-grounded calibration checkpoint."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from evaluation.phase2_calibration.retrieval import run_calibration_retrieval
from evaluation.phase2_calibration.validation import validate_calibration_dataset

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation/datasets/phase2_semantic_calibration_v1"


def _rows(name: str) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (DATASET / name).read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_calibration_has_bounded_traceable_cases_and_evidence() -> None:
    cases = _rows("cases.jsonl")
    verification = _rows("evidence_verification.jsonl")
    verified = {
        row["evidence_id"]
        for row in verification
        if row["semantic_verification_status"] == "MACHINE_VERIFIED"
    }
    assert len(cases) == 30
    assert len(verification) == 152
    assert len({row["evidence_id"] for row in verification}) == 152
    assert {str(row["original_v1_case_id"]) for row in cases} == {
        f"P2-{family}-{index:03d}" for family in ("PUMP", "HVAC", "GEN") for index in range(1, 11)
    }
    for case in cases:
        assert case["field_observed"] is False
        assert case["scenario_origin"] == "document_derived"
        assert case["sme_review_status"] == "pending"
        assert case["promotion_eligible"] is False
        if case["calibration_status"] == "READY_FOR_SME":
            assert set(case["required_evidence_ids"]).issubset(verified)


def test_calibration_validation_and_checksums_pass() -> None:
    report = validate_calibration_dataset(DATASET, write_reports=False)
    assert report["status"] == "PASS"
    for line in (DATASET / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        expected, name = line.split(maxsplit=1)
        assert hashlib.sha256((DATASET / name).read_bytes()).hexdigest() == expected


def test_v1_and_v2_checkpoint_bytes_are_unchanged_from_head() -> None:
    for dataset_name in ("phase2_document_derived_v1", "phase2_document_derived_v2"):
        root = ROOT / "evaluation/datasets" / dataset_name
        for path in sorted(file for file in root.rglob("*") if file.is_file()):
            repository_path = path.relative_to(ROOT).as_posix()
            committed = subprocess.check_output(
                ["git", "show", f"HEAD:{repository_path}"], cwd=ROOT
            )
            assert path.read_bytes() == committed


def test_chunk_evaluation_never_passes_gold_to_retriever_and_has_competition() -> None:
    report = run_calibration_retrieval(DATASET)
    assert all("EV2-" not in str(row["question"]) for row in _rows("retrieval_questions.jsonl"))
    assert report["candidate_pool_before_filter"] == 152
    assert all(
        value["candidate_pool_after_filter"] >= 50
        for value in report["answerable_retrieval"]["per_family"].values()
    )
    assert report["live_llm_called"] is False
