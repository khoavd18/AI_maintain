from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from evaluation.run_evaluation import load_questions, run_evaluation
from evaluation.validate_phase2_dataset import (
    _write_canonical_report,
    validate_dataset,
    write_reports,
)
from src.rag.document_loader import load_documents

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "datasets" / "phase2_document_derived_v1"


def test_phase2_reports_are_canonical_lf_and_no_write_is_read_only(tmp_path: Path) -> None:
    probe = tmp_path / "newline-probe.txt"
    _write_canonical_report(probe, "alpha\r\nbeta\rgamma\n")
    assert probe.read_bytes() == b"alpha\nbeta\ngamma\n"

    report = validate_dataset(DATASET)
    output_dataset = tmp_path / "output-dataset"
    output_dataset.mkdir()
    write_reports(report, output_dataset)

    canonical_json = (DATASET / "validation_report.json").read_bytes()
    canonical_markdown = (DATASET / "validation_report.md").read_bytes()
    generated_json = (output_dataset / "validation_report.json").read_bytes()
    generated_markdown = (output_dataset / "validation_report.md").read_bytes()
    assert b"\r" not in generated_json
    assert b"\r" not in generated_markdown
    assert generated_json == canonical_json
    assert generated_markdown == canonical_markdown
    assert hashlib.sha256(generated_json).hexdigest() == (
        "1c6ec518c01e979575bd016777c36b2022af779d6cec215b7937c4b1707861bf"
    )
    assert hashlib.sha256(generated_markdown).hexdigest() == (
        "931e913d15f352d9205fe5d783a1522ae0c27735864be57c6ed85687fa373a3c"
    )

    no_write_dataset = tmp_path / "no-write-dataset"
    shutil.copytree(DATASET, no_write_dataset)
    before_json = (no_write_dataset / "validation_report.json").read_bytes()
    before_markdown = (no_write_dataset / "validation_report.md").read_bytes()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "evaluation.validate_phase2_dataset",
            str(no_write_dataset),
            "--no-write-report",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert (no_write_dataset / "validation_report.json").read_bytes() == before_json
    assert (no_write_dataset / "validation_report.md").read_bytes() == before_markdown


def test_phase2_document_dataset_is_traceable_and_still_draft() -> None:
    report = validate_dataset(DATASET)

    assert report["status"] == "PASS_WITH_WARNINGS"
    assert report["error_count"] == 0
    assert report["observed_counts"] == {
        "sources": 3,
        "asset_profiles": 3,
        "cases": 30,
        "cases_per_asset_profile": 10,
        "runner_eligible_cases": 27,
        "manual_review_only_cases": 3,
        "evidence_spans": 26,
        "corpus_documents": 26,
        "conversation_sequences": 3,
        "conversation_turns": 6,
    }


def test_phase2_corpus_uses_existing_controlled_document_contract() -> None:
    documents = load_documents(DATASET / "corpus_documents.csv")

    assert len(documents) == 26
    assert {document.asset_type for document in documents} == {
        "Máy bơm nước",
        "Máy lạnh",
        "Máy phát điện dự phòng",
    }
    assert all(document.version == "0.1.0" for document in documents)
    assert all(document.language == "vi" for document in documents)
    assert all(document.source.startswith("https://www.") for document in documents)
    assert all("Tài liệu tham khảo:" in document.content for document in documents)


def test_phase2_retrieval_projection_contains_only_runner_eligible_cases() -> None:
    questions = load_questions(DATASET / "retrieval_questions.jsonl")
    cases = [
        json.loads(line)
        for line in (DATASET / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(questions) == 27
    assert {question.id for question in questions} == {
        case["case_id"] for case in cases if case["runner_eligible"]
    }
    assert all(not question.expected_no_answer for question in questions)


def test_phase2_custom_corpus_runs_without_changing_phase1_defaults() -> None:
    manifest = json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))
    report = run_evaluation(
        questions_path=DATASET / "retrieval_questions.jsonl",
        conversation_sequences_path=DATASET / "conversation_sequences.jsonl",
        documents_path=DATASET / "corpus_documents.csv",
        backend="in-memory-hash",
        mode="deterministic",
        dataset_version=manifest["version"],
        dataset_id=manifest["dataset_id"],
        corpus_name=manifest["corpus"],
        dataset_limitations=manifest["limitations"],
    )

    assert report["dataset_version"] == "0.1.0"
    assert report["dataset_id"] == "phase2-document-derived-v1-draft"
    assert report["corpus"] == "official-manual-paraphrase-fixture-v0.1"
    assert report["dataset_size"] == 27
    assert report["retrieval"]["question_count"] == 27
    assert report["documents"].endswith("corpus_documents.csv")
    assert report["answers"]["no_answer_accuracy"] is None
    assert report["answers"]["multi_turn_resolution_accuracy"] == 1.0
