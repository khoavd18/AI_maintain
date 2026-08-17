"""Top-level orchestration for the Phase 2 v2 dataset builder."""

from __future__ import annotations

from pathlib import Path

from evaluation.phase2_v2.artifacts import (
    _build_corpus,
    _manifest,
    _qa_report,
    _readme,
    _schema,
    _write_csv,
    _write_json,
    _write_jsonl,
    _write_review_queue,
)
from evaluation.phase2_v2.baseline import _build_sources, load_v1_cases
from evaluation.phase2_v2.case_factory import _build_cases, _build_evidence, _build_questions
from evaluation.phase2_v2.conversations import _build_conversations
from evaluation.phase2_v2.dataset_spec import DEFAULT_OUTPUT
from evaluation.phase2_v2.integrity import _write_checksums, _write_text


def build_dataset(output: Path = DEFAULT_OUTPUT) -> None:
    """Generate all package artifacts deterministically into a new directory."""

    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing dataset: {output}")
    output.mkdir(parents=True)
    baseline = load_v1_cases()
    evidence = _build_evidence()
    cases = _build_cases(baseline, evidence)
    questions = _build_questions(cases)
    conversations = _build_conversations(cases)
    sources = _build_sources()
    corpus = _build_corpus(evidence)

    _write_jsonl(output / "source_registry.jsonl", sources)
    _write_jsonl(output / "evidence_spans.jsonl", evidence)
    _write_jsonl(output / "cases.jsonl", cases)
    _write_jsonl(output / "retrieval_questions.jsonl", questions)
    _write_jsonl(output / "conversation_sequences.jsonl", conversations)
    _write_csv(output / "corpus_documents.csv", corpus)
    _write_review_queue(output / "review_queue.xlsx", cases, sources, evidence)
    _write_json(output / "schema.json", _schema())
    _write_json(output / "manifest.json", _manifest(cases, evidence, conversations))
    _write_text(output / "README.md", _readme())
    _write_text(output / "QA_REPORT.md", _qa_report(cases, evidence))
    _write_checksums(output)
