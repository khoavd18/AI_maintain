"""Validate the source-traceable Phase 2 document-derived evaluation package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_SOURCE_HOSTS = frozenset(
    {
        "www.grundfos.com",
        "www.daikin.eu",
        "www.generac.com",
    }
)
ALLOWED_DATASET_SUFFIXES = frozenset({".json", ".jsonl", ".csv", ".xlsx", ".md", ".sha256"})
EXPECTED_ASSET_TYPES = (
    "Máy bơm nước",
    "Máy lạnh",
    "Máy phát điện dự phòng",
)
CASE_ID_PATTERN = re.compile(r"^P2-(PUMP|HVAC|GEN)-[0-9]{3}$")


@dataclass(frozen=True)
class ValidationFinding:
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


def validate_dataset(dataset_dir: Path) -> dict[str, object]:
    dataset_dir = dataset_dir.resolve()
    findings: list[ValidationFinding] = []

    def error(code: str, message: str) -> None:
        findings.append(ValidationFinding("error", code, message))

    def warning(code: str, message: str) -> None:
        findings.append(ValidationFinding("warning", code, message))

    required_names = {
        "manifest.json",
        "schema.json",
        "source_registry.jsonl",
        "evidence_spans.jsonl",
        "cases.jsonl",
        "retrieval_questions.jsonl",
        "conversation_sequences.jsonl",
        "corpus_documents.csv",
        "review_queue.xlsx",
        "README.md",
    }
    if not dataset_dir.is_dir():
        return _final_report(
            dataset_dir,
            [ValidationFinding("error", "dataset_missing", "Dataset directory does not exist.")],
            {},
        )
    missing = sorted(name for name in required_names if not (dataset_dir / name).is_file())
    if missing:
        error("required_files_missing", f"Missing required files: {', '.join(missing)}")

    for path in dataset_dir.iterdir():
        if path.is_symlink():
            error("symlink_forbidden", f"Symlink is not allowed: {path.name}")
        elif path.is_file() and path.suffix.casefold() not in ALLOWED_DATASET_SUFFIXES:
            error("unsupported_file_type", f"Unsupported file type: {path.name}")

    manifest = _load_json(dataset_dir / "manifest.json", error)
    sources = _load_jsonl(dataset_dir / "source_registry.jsonl", error)
    evidence = _load_jsonl(dataset_dir / "evidence_spans.jsonl", error)
    cases = _load_jsonl(dataset_dir / "cases.jsonl", error)
    questions = _load_jsonl(dataset_dir / "retrieval_questions.jsonl", error)
    conversations = _load_jsonl(dataset_dir / "conversation_sequences.jsonl", error)
    corpus_rows = _load_csv(dataset_dir / "corpus_documents.csv", error)

    source_by_id = _unique_index(sources, "source_id", "source", error)
    evidence_by_id = _unique_index(evidence, "evidence_id", "evidence", error)
    case_by_id = _unique_index(cases, "case_id", "case", error)
    corpus_by_id = _unique_index(corpus_rows, "doc_id", "corpus document", error)
    question_by_id = _unique_index(questions, "id", "retrieval question", error)

    for source_id, source in source_by_id.items():
        if source.get("provenance_type") != "document_derived":
            error("source_provenance", f"{source_id} must be document_derived.")
        if source.get("source_file_included") is not False:
            error("source_pdf_embedded", f"{source_id} must remain link-only.")
        if source.get("redistribution_mode") != "link_only":
            error("source_redistribution", f"{source_id} redistribution_mode must be link_only.")
        parsed = urlparse(str(source.get("official_url", "")))
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_SOURCE_HOSTS:
            error(
                "source_not_official_host",
                f"{source_id} does not use an allow-listed HTTPS manufacturer host.",
            )
        if source.get("sha256") is None:
            warning(
                "source_checksum_pending", f"{source_id} needs a SHA-256 after authorised download."
            )
        if source.get("review_status") != "pending_sme":
            error("source_review_state", f"{source_id} must remain pending_sme in this draft.")

    evidence_doc_ids: set[str] = set()
    for evidence_id, span in evidence_by_id.items():
        source_id = str(span.get("source_id", ""))
        if source_id not in source_by_id:
            error(
                "evidence_unknown_source", f"{evidence_id} references unknown source {source_id}."
            )
        corpus_doc_id = str(span.get("corpus_doc_id", ""))
        if not corpus_doc_id:
            error("evidence_missing_corpus_doc", f"{evidence_id} has no corpus_doc_id.")
        elif corpus_doc_id in evidence_doc_ids:
            error(
                "evidence_duplicate_corpus_doc",
                f"Corpus document {corpus_doc_id} is reused by evidence spans.",
            )
        evidence_doc_ids.add(corpus_doc_id)
        locator = span.get("locator")
        if (
            not isinstance(locator, dict)
            or not locator.get("manual_page")
            or not locator.get("section")
        ):
            error(
                "evidence_locator", f"{evidence_id} requires manual page and section traceability."
            )
        if not span.get("paraphrase_vi") or not span.get("facts"):
            error("evidence_content", f"{evidence_id} requires a Vietnamese paraphrase and facts.")
        if span.get("review_status") != "pending_sme":
            error("evidence_review_state", f"{evidence_id} must remain pending_sme.")

    asset_counts: Counter[str] = Counter()
    runner_ids: set[str] = set()
    normalized_questions: dict[str, str] = {}
    for case_id, case in case_by_id.items():
        if not CASE_ID_PATTERN.fullmatch(case_id):
            error("case_id_format", f"Invalid case id: {case_id}")
        if case.get("dataset_version") != "0.1.0":
            error("case_version", f"{case_id} has an unexpected dataset version.")
        if case.get("provenance_type") != "document_derived":
            error("case_provenance", f"{case_id} must be document_derived.")
        if case.get("approval_state") != "draft":
            error("case_approval_state", f"{case_id} must remain draft before SME review.")
        if case.get("citation_required") is not True:
            error("case_citation_gate", f"{case_id} must require citations.")
        asset_profile = case.get("asset_profile")
        asset_type = asset_profile.get("asset_type") if isinstance(asset_profile, dict) else None
        if asset_type not in EXPECTED_ASSET_TYPES:
            error("case_asset_type", f"{case_id} has an unsupported asset type.")
        else:
            asset_counts[str(asset_type)] += 1
        expected_document_ids = case.get("expected_document_ids")
        if not isinstance(expected_document_ids, list) or not expected_document_ids:
            error(
                "case_expected_documents", f"{case_id} must reference at least one corpus document."
            )
        else:
            for document_id in expected_document_ids:
                if document_id not in corpus_by_id:
                    error(
                        "case_unknown_document",
                        f"{case_id} references unknown corpus document {document_id}.",
                    )
        evidence_ids = case.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            error("case_evidence", f"{case_id} must reference at least one evidence span.")
        else:
            for evidence_id in evidence_ids:
                if evidence_id not in evidence_by_id:
                    error(
                        "case_unknown_evidence",
                        f"{case_id} references unknown evidence {evidence_id}.",
                    )
        rubric = case.get("gold_rubric")
        if not isinstance(rubric, dict):
            error("case_rubric", f"{case_id} has no gold rubric.")
        else:
            for field in ("must_include", "must_not_claim", "safety_requirements"):
                if not isinstance(rubric.get(field), list) or not rubric[field]:
                    error("case_rubric", f"{case_id} rubric field {field} must be non-empty.")
            if not rubric.get("answer_boundary"):
                error("case_rubric", f"{case_id} has no answer boundary.")
        sme_review = case.get("sme_review")
        if not isinstance(sme_review, dict) or sme_review.get("status") != "pending":
            error("case_sme_status", f"{case_id} must be pending SME review.")
        if case.get("runner_eligible") is True:
            runner_ids.add(case_id)
        question = str(case.get("question", ""))
        normalized = _normalize_question(question)
        if not normalized:
            error("case_question", f"{case_id} has an empty question.")
        elif normalized in normalized_questions:
            error(
                "case_question_duplicate",
                f"{case_id} duplicates {normalized_questions[normalized]} after normalization.",
            )
        normalized_questions[normalized] = case_id

    if asset_counts != Counter({asset_type: 10 for asset_type in EXPECTED_ASSET_TYPES}):
        error(
            "asset_distribution",
            f"Expected 10 cases per asset type, observed {dict(asset_counts)}.",
        )

    if set(question_by_id) != runner_ids:
        missing_projection = sorted(runner_ids - set(question_by_id))
        unexpected_projection = sorted(set(question_by_id) - runner_ids)
        error(
            "retrieval_projection_mismatch",
            f"Missing projection: {missing_projection}; unexpected projection: {unexpected_projection}.",
        )
    for question_id, question in question_by_id.items():
        case = case_by_id.get(question_id)
        if case is None:
            continue
        asset_profile = case.get("asset_profile") or {}
        if question.get("question") != case.get("question"):
            error("retrieval_question_drift", f"{question_id} question text differs from its case.")
        if question.get("asset_type") != asset_profile.get("asset_type"):
            error("retrieval_asset_drift", f"{question_id} asset_type differs from its case.")
        if question.get("expected_document_ids") != case.get("expected_document_ids"):
            error("retrieval_document_drift", f"{question_id} document ids differ from its case.")
        if question.get("expected_no_answer") is not False:
            error(
                "retrieval_no_answer_shape",
                f"{question_id} must be a supported retrieval projection.",
            )

    conversation_turns = 0
    conversation_ids: set[str] = set()
    for sequence in conversations:
        sequence_id = str(sequence.get("id", ""))
        if not sequence_id or sequence_id in conversation_ids:
            error("conversation_id", f"Invalid or duplicate conversation id {sequence_id!r}.")
        conversation_ids.add(sequence_id)
        turns = sequence.get("turns")
        if not isinstance(turns, list) or len(turns) < 2:
            error("conversation_turns", f"{sequence_id} requires at least two turns.")
            continue
        conversation_turns += len(turns)
        for turn in turns:
            for document_id in turn.get("expected_document_ids", []):
                if document_id not in corpus_by_id:
                    error(
                        "conversation_unknown_document", f"{sequence_id} references {document_id}."
                    )
            for evidence_id in turn.get("evidence_ids", []):
                if evidence_id not in evidence_by_id:
                    error(
                        "conversation_unknown_evidence", f"{sequence_id} references {evidence_id}."
                    )

    if set(corpus_by_id) != evidence_doc_ids:
        error(
            "corpus_evidence_mismatch",
            f"Corpus/evidence ids differ: corpus-only={sorted(set(corpus_by_id) - evidence_doc_ids)}, evidence-only={sorted(evidence_doc_ids - set(corpus_by_id))}.",
        )
    source_urls = {str(source.get("official_url")) for source in sources}
    for document_id, row in corpus_by_id.items():
        if row.get("source") not in source_urls:
            error("corpus_source", f"{document_id} does not link to a registered source.")
        if row.get("language") != "vi" or row.get("version") != "0.1.0":
            error("corpus_metadata", f"{document_id} has unexpected language or version.")
        if row.get("clean_text") != row.get("raw_text"):
            error("corpus_text_drift", f"{document_id} raw_text and clean_text differ.")
        if "Tài liệu tham khảo:" not in str(row.get("clean_text", "")):
            error("corpus_traceability", f"{document_id} has no source locator in its content.")

    all_corpus_text = "\n".join(str(row.get("clean_text", "")) for row in corpus_rows).casefold()
    for case_id, case in case_by_id.items():
        question = str(case.get("question", "")).strip().casefold()
        if question and question in all_corpus_text:
            error("question_answer_leakage", f"{case_id} question appears verbatim in the corpus.")

    expected_counts = manifest.get("counts") if isinstance(manifest, dict) else None
    observed_counts = {
        "sources": len(sources),
        "asset_profiles": len(asset_counts),
        "cases": len(cases),
        "cases_per_asset_profile": min(asset_counts.values()) if asset_counts else 0,
        "runner_eligible_cases": len(runner_ids),
        "manual_review_only_cases": len(cases) - len(runner_ids),
        "evidence_spans": len(evidence),
        "corpus_documents": len(corpus_rows),
        "conversation_sequences": len(conversations),
        "conversation_turns": conversation_turns,
    }
    if expected_counts != observed_counts:
        error(
            "manifest_count_drift",
            f"Manifest counts {expected_counts} differ from observed {observed_counts}.",
        )
    if manifest.get("provenance_type") != "document_derived":
        error("manifest_provenance", "Manifest must be document_derived.")
    if manifest.get("readiness") != "DRAFT_SME_REVIEW_REQUIRED":
        error("manifest_readiness", "Draft package must remain DRAFT_SME_REVIEW_REQUIRED.")

    if any(source.get("supersession_status") != "verified_current" for source in sources):
        warning(
            "supersession_pending", "One or more sources require a currentness/supersession check."
        )
    warning("sme_review_pending", "All 30 cases require domain-expert review before approval.")
    warning("field_evidence_absent", "No field-observed ticket or work-order evidence is present.")

    return _final_report(dataset_dir, findings, observed_counts)


def _write_canonical_report(path: Path, content: str) -> None:
    canonical_content = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(canonical_content.encode("utf-8"))


def write_reports(report: dict[str, object], dataset_dir: Path) -> None:
    json_path = dataset_dir / "validation_report.json"
    markdown_path = dataset_dir / "validation_report.md"
    _write_canonical_report(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    findings = report.get("findings") or []
    lines = [
        "# Phase 2 Dataset Validation Report",
        "",
        f"- Status: **{report['status']}**",
        f"- Errors: {report['error_count']}",
        f"- Warnings: {report['warning_count']}",
        "",
        "## Observed counts",
        "",
        "| Item | Count |",
        "|---|---:|",
    ]
    for key, value in (report.get("observed_counts") or {}).items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Findings", ""])
    if findings:
        for finding in findings:
            lines.append(
                f"- **{str(finding['severity']).upper()} — {finding['code']}**: {finding['message']}"
            )
    else:
        lines.append("- No findings.")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "This validation checks package structure, traceability, projection consistency, and obvious leakage. It does not approve maintenance content or establish field accuracy.",
        ]
    )
    _write_canonical_report(markdown_path, "\n".join(lines) + "\n")


ValidationErrorCallback = Callable[[str, str], None]


def _load_json(path: Path, error: ValidationErrorCallback) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        error("invalid_json", f"Could not parse {path.name}: {exc}")
        return {}
    if not isinstance(value, dict):
        error("invalid_json_shape", f"{path.name} must contain one JSON object.")
        return {}
    return value


def _load_jsonl(path: Path, error: ValidationErrorCallback) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            error("invalid_jsonl", f"{path.name}:{line_number} is invalid JSON: {exc.msg}.")
            continue
        if not isinstance(value, dict):
            error("invalid_jsonl_shape", f"{path.name}:{line_number} must be an object.")
            continue
        records.append(value)
    return records


def _load_csv(path: Path, error: ValidationErrorCallback) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        error("invalid_csv", f"Could not parse {path.name}: {exc}")
        return []


def _unique_index(
    records: list[dict[str, object]],
    key: str,
    label: str,
    error: ValidationErrorCallback,
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for record in records:
        identifier = str(record.get(key, ""))
        if not identifier:
            error("missing_identifier", f"A {label} has no {key}.")
        elif identifier in result:
            error("duplicate_identifier", f"Duplicate {label} identifier: {identifier}.")
        else:
            result[identifier] = record
    return result


def _normalize_question(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    unaccented = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", unaccented).strip()


def _final_report(
    dataset_dir: Path,
    findings: list[ValidationFinding],
    observed_counts: dict[str, int],
) -> dict[str, object]:
    ordered = sorted(findings, key=lambda item: (item.severity != "error", item.code, item.message))
    error_count = sum(item.severity == "error" for item in ordered)
    warning_count = sum(item.severity == "warning" for item in ordered)
    digest = hashlib.sha256(
        "\n".join(f"{item.severity}:{item.code}:{item.message}" for item in ordered).encode("utf-8")
    ).hexdigest()
    return {
        "status": "PASS_WITH_WARNINGS" if error_count == 0 else "FAIL",
        "dataset_directory": dataset_dir.name,
        "error_count": error_count,
        "warning_count": warning_count,
        "observed_counts": observed_counts,
        "findings_digest_sha256": digest,
        "findings": [item.to_dict() for item in ordered],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("--no-write-report", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = validate_dataset(args.dataset_dir)
    if not args.no_write_report:
        write_reports(report, args.dataset_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["error_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
