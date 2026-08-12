"""Strict validation gates for the 300-case Phase 2 v2 draft package."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any, Callable
from zipfile import ZipFile

EXPECTED_CATEGORIES = {
    "troubleshooting": 90,
    "operation_repair_procedure": 45,
    "preventive_maintenance_inspection": 36,
    "safety_escalation": 30,
    "insufficient_evidence_no_answer": 30,
    "model_version_applicability_isolation": 30,
    "multi_turn_follow_up": 24,
    "language_typo_abbreviation_robustness": 15,
}
EXPECTED_RISKS = {"critical": 45, "high": 75, "medium": 105, "low": 75}
EXPECTED_LANGUAGES = {
    "vi_diacritics": 180,
    "vi_no_diacritics": 45,
    "en": 45,
    "mixed_vi_en": 30,
}
EXPECTED_POLICIES = {
    "answer_with_evidence": 240,
    "refuse_insufficient_evidence": 30,
    "escalate_manual_review": 30,
}
FAMILY_PREFIXES = ("PUMP", "HVAC", "GEN")
SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|secret|password|authorization|bearer)\s*[:=]\s*[^\s,;]{8,}"
)
NUMERIC_PATTERN = re.compile(
    r"(?i)(?<!\w)\d+(?:[.,]\d+)?\s*(?:nm|vdc|psi|kpa|°?c|°?f|hz|rpm|%|mph|km/h|mm|m|kg|l)?"
)


def validate_v2_dataset(
    dataset_dir: Path,
    *,
    finding: Callable[[str, str, str], None],
) -> dict[str, int]:
    """Validate exact quotas, governance, traceability, content, and packaging."""

    def error(code: str, message: str) -> None:
        finding("error", code, message)

    def warning(code: str, message: str) -> None:
        finding("warning", code, message)

    required = {
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
        "QA_REPORT.md",
        "checksums.sha256",
    }
    missing = sorted(name for name in required if not (dataset_dir / name).is_file())
    if missing:
        error("required_files_missing", f"Missing v2 files: {', '.join(missing)}")
    manifest = _json(dataset_dir / "manifest.json", error)
    sources = _jsonl(dataset_dir / "source_registry.jsonl", error)
    evidence = _jsonl(dataset_dir / "evidence_spans.jsonl", error)
    cases = _jsonl(dataset_dir / "cases.jsonl", error)
    questions = _jsonl(dataset_dir / "retrieval_questions.jsonl", error)
    conversations = _jsonl(dataset_dir / "conversation_sequences.jsonl", error)
    corpus = _csv(dataset_dir / "corpus_documents.csv", error)

    source_by_id = _index(sources, "source_id", "source", error)
    evidence_by_id = _index(evidence, "evidence_id", "evidence", error)
    case_by_id = _index(cases, "case_id", "case", error)
    document_by_id = _index(corpus, "doc_id", "document", error)
    question_by_id = _index(questions, "id", "question", error)

    if manifest.get("version") != "2.0.0":
        error("manifest_version", "v2 manifest version must be 2.0.0.")
    if manifest.get("readiness") != "DRAFT_SME_REVIEW_REQUIRED":
        error("manifest_readiness", "v2 must remain DRAFT_SME_REVIEW_REQUIRED.")

    expected_source = {
        "SRC-GF-CR5-0407": ("VERSION_AMBIGUOUS", "HIGH", "blocked"),
        "SRC-DAIKIN-RZAG-4P695307-1B": ("VERIFIED_CURRENT", "MEDIUM", "passed"),
        "SRC-GENERAC-MLG15-A0000381158": ("VERSION_AMBIGUOUS", "HIGH", "blocked"),
    }
    if set(source_by_id) != set(expected_source):
        error("source_inventory", f"Unexpected source inventory: {sorted(source_by_id)}")
    for source_id, expected in expected_source.items():
        source = source_by_id.get(source_id, {})
        observed = (
            source.get("source_currentness_status"),
            source.get("source_currentness_risk"),
            source.get("source_currentness_gate"),
        )
        if observed != expected:
            error("source_currentness", f"{source_id} currentness {observed} != {expected}.")
        if not re.fullmatch(r"[0-9a-f]{64}", str(source.get("sha256", ""))):
            error("source_checksum", f"{source_id} requires a captured SHA-256.")
        if source.get("source_file_included") is not False:
            error("source_pdf_embedded", f"{source_id} must remain link-only.")

    evidence_family = Counter()
    evidence_docs: set[str] = set()
    for evidence_id, item in evidence_by_id.items():
        source_id = str(item.get("source_id", ""))
        if source_id not in source_by_id:
            error("evidence_source", f"{evidence_id} references unknown {source_id}.")
        evidence_family[source_id] += 1
        document_id = str(item.get("corpus_doc_id", ""))
        if not document_id:
            error("evidence_document", f"{evidence_id} has no corpus document.")
        evidence_docs.add(document_id)
        locator = item.get("locator")
        if not isinstance(locator, dict) or not all(
            locator.get(key)
            for key in ("pdf_page_1_based", "manual_page", "section", "stable_locator")
        ):
            error("evidence_locator", f"{evidence_id} has incomplete page/section locator.")
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("content_sha256", ""))):
            error("evidence_hash", f"{evidence_id} has no stable content hash.")
        if not item.get("model_applicability") or item.get("review_status") != "pending_sme":
            error(
                "evidence_governance", f"{evidence_id} has incomplete applicability/review state."
            )
    if len(evidence) < 150 or any(count < 50 for count in evidence_family.values()):
        error(
            "evidence_quota", f"Evidence total/family counts are {len(evidence)}/{evidence_family}."
        )
    if set(document_by_id) != evidence_docs:
        error("corpus_evidence", "Corpus documents and evidence corpus_doc_id values differ.")

    for document_id, row in document_by_id.items():
        if row.get("version") != "2.0.0" or row.get("language") != "vi":
            error("corpus_metadata", f"{document_id} has invalid version/language.")
        if row.get("raw_text") != row.get("clean_text"):
            error("corpus_text", f"{document_id} raw and clean text differ.")
        if "Tài liệu tham khảo:" not in str(row.get("clean_text", "")):
            error("corpus_locator", f"{document_id} has no source locator.")

    normalized: dict[str, str] = {}
    family_count = Counter()
    category_count = Counter()
    risk_count = Counter()
    language_count = Counter()
    policy_count = Counter()
    source_status_count = Counter()
    original_count = 0
    intentional_count = 0
    adversarial_count = 0
    for case_id, case in case_by_id.items():
        if not re.fullmatch(r"P2-(?:PUMP|HVAC|GEN)-\d{3}", case_id):
            error("case_id", f"Invalid case id {case_id}.")
        family = case_id.split("-")[1] if "-" in case_id else ""
        family_count[family] += 1
        for field, expected in {
            "dataset_version": "2.0.0",
            "scenario_origin": "document_derived",
            "field_observed": False,
            "approval_state": "draft",
            "sme_review_status": "pending",
            "promotion_eligible": False,
        }.items():
            if case.get(field) != expected:
                error("case_governance", f"{case_id} {field} must be {expected!r}.")
        source_id = str(case.get("source_id", ""))
        source = source_by_id.get(source_id, {})
        if case.get("source_currentness_status") != source.get("source_currentness_status"):
            error("case_currentness", f"{case_id} does not propagate source currentness.")
        if case.get("source_currentness_gate") != source.get("source_currentness_gate"):
            error("case_currentness_gate", f"{case_id} has wrong source gate.")
        if source.get("source_currentness_gate") == "blocked" and (
            case.get("source_review_required") is not True
            or case.get("promotion_eligible") is not False
        ):
            error("blocked_source_promotion", f"{case_id} may not be promoted.")
        category_count[str(case.get("primary_category"))] += 1
        risk_count[str(case.get("risk_level"))] += 1
        language_count[str(case.get("language_variant"))] += 1
        policy_count[str(case.get("response_policy"))] += 1
        source_status_count[str(case.get("source_currentness_status"))] += 1
        original_count += int(bool(case.get("baseline_semantics_preserved")))
        intentional_count += int(bool(case.get("intentional_robustness_pair")))
        adversarial_count += int(bool(case.get("adversarial_unsafe")))
        question = str(case.get("question", ""))
        key = _normalize(question)
        if not key or key in normalized:
            error("case_question_duplicate", f"{case_id} duplicates {normalized.get(key)}.")
        normalized[key] = case_id
        policy = case.get("response_policy")
        evidence_ids = case.get("evidence_ids")
        document_ids = case.get("expected_document_ids")
        if not isinstance(evidence_ids, list) or not isinstance(document_ids, list):
            error("case_traceability", f"{case_id} evidence/document ids must be lists.")
            continue
        if policy == "refuse_insufficient_evidence":
            if evidence_ids or document_ids:
                error("no_answer_evidence", f"{case_id} must expect no applicable evidence.")
        elif not evidence_ids or not document_ids:
            error("answerable_evidence", f"{case_id} requires evidence and documents.")
        for evidence_id in evidence_ids:
            item = evidence_by_id.get(str(evidence_id))
            if item is None:
                error("case_evidence", f"{case_id} references unknown {evidence_id}.")
            elif item.get("source_id") != source_id:
                error("case_evidence_source", f"{case_id} cites another source family.")
        for document_id in document_ids:
            if str(document_id) not in document_by_id:
                error("case_document", f"{case_id} references unknown {document_id}.")
        if policy == "answer_with_evidence":
            _check_numeric_grounding(case_id, case, evidence_by_id, error)

    if family_count != Counter({name: 100 for name in FAMILY_PREFIXES}):
        error("family_quota", f"Family counts are {dict(family_count)}.")
    for code, observed, expected in (
        ("category_quota", category_count, EXPECTED_CATEGORIES),
        ("risk_quota", risk_count, EXPECTED_RISKS),
        ("language_quota", language_count, EXPECTED_LANGUAGES),
        ("response_policy_quota", policy_count, EXPECTED_POLICIES),
    ):
        if observed != Counter(expected):
            error(code, f"Observed {dict(observed)} != {expected}.")
    if len(cases) != 300 or len(case_by_id) != 300:
        error("case_count", f"Expected 300 cases, observed {len(cases)}.")
    if original_count != 30:
        error("baseline_preservation", f"Expected 30 preserved cases, observed {original_count}.")
    if adversarial_count != 30:
        error("adversarial_quota", f"Expected 30 adversarial cases, observed {adversarial_count}.")
    if intentional_count > 45:
        error("intentional_variant_limit", f"Intentional variants exceed 15%: {intentional_count}.")
    if source_status_count != Counter({"VERSION_AMBIGUOUS": 200, "VERIFIED_CURRENT": 100}):
        error("source_status_distribution", f"Source status counts are {source_status_count}.")

    _check_near_duplicates(cases, error)
    if set(question_by_id) != set(case_by_id):
        error("retrieval_projection", "All 300 cases must have one retrieval input.")
    for question_id, question in question_by_id.items():
        case = case_by_id.get(question_id, {})
        for field in ("question", "expected_document_ids", "source_id", "response_policy"):
            if question.get(field) != case.get(field):
                error("retrieval_drift", f"{question_id} field {field} differs from case.")
        expected_no_answer = case.get("response_policy") == "refuse_insufficient_evidence"
        if question.get("expected_no_answer") is not expected_no_answer:
            error("retrieval_no_answer", f"{question_id} has wrong no-answer flag.")

    pattern_count = Counter()
    conversation_turns = 0
    if len(conversations) != 30:
        error("conversation_count", f"Expected 30 sequences, observed {len(conversations)}.")
    for sequence in conversations:
        turns = sequence.get("turns")
        pattern_count[str(sequence.get("conversation_pattern"))] += 1
        if not isinstance(turns, list) or not 2 <= len(turns) <= 4:
            error("conversation_turns", f"{sequence.get('id')} requires 2-4 turns.")
            continue
        conversation_turns += len(turns)
        for turn in turns:
            for evidence_id in turn.get("evidence_ids", []):
                if evidence_id not in evidence_by_id:
                    error("conversation_evidence", f"Unknown conversation evidence {evidence_id}.")
            for document_id in turn.get("expected_document_ids", []):
                if document_id not in document_by_id:
                    error("conversation_document", f"Unknown conversation document {document_id}.")
    required_patterns = {
        "follow_up_continuity",
        "same_asset_clarification",
        "new_symptom_reset",
        "asset_model_switch_reset",
        "unsafe_follow_up_refusal",
        "insufficient_context_escalation",
    }
    if set(pattern_count) != required_patterns:
        error("conversation_patterns", f"Conversation patterns are {sorted(pattern_count)}.")

    review_rows = _xlsx_review_rows(dataset_dir / "review_queue.xlsx", error)
    if review_rows != 300:
        error("review_queue_count", f"Expected 300 review rows, observed {review_rows}.")
    _check_text_encoding(dataset_dir, error)
    _check_checksums(dataset_dir, error)
    _check_sensitive_content(dataset_dir, error)

    warning(
        "field_evidence_absent", "All 300 cases are document-derived; no field evidence exists."
    )
    warning("sme_review_pending", "All 300 cases remain pending qualified SME review.")
    warning(
        "source_currentness_blocked",
        "Grundfos and Generac remain VERSION_AMBIGUOUS/HIGH and cannot be promoted.",
    )
    return {
        "sources": len(sources),
        "asset_profiles": len(family_count),
        "cases": len(cases),
        "cases_per_asset_profile": min(family_count.values()) if family_count else 0,
        "retrieval_questions": len(questions),
        "no_answer_cases": policy_count["refuse_insufficient_evidence"],
        "evidence_spans": len(evidence),
        "corpus_documents": len(corpus),
        "conversation_sequences": len(conversations),
        "conversation_turns": conversation_turns,
        "review_queue_rows": review_rows,
        "original_cases_preserved": original_count,
        "new_cases": len(cases) - original_count,
    }


def _check_numeric_grounding(
    case_id: str,
    case: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    error: Callable[[str, str], None],
) -> None:
    rubric = case.get("gold_rubric")
    if not isinstance(rubric, dict):
        error("case_rubric", f"{case_id} has no gold rubric.")
        return
    expected_text = json.dumps(rubric.get("must_include", []), ensure_ascii=False)
    evidence_text = " ".join(
        json.dumps(evidence_by_id.get(str(item), {}), ensure_ascii=False)
        for item in case.get("evidence_ids", [])
    )
    expected_numbers = {_normalize_number(item) for item in NUMERIC_PATTERN.findall(expected_text)}
    evidence_numbers = {_normalize_number(item) for item in NUMERIC_PATTERN.findall(evidence_text)}
    missing = sorted(expected_numbers - evidence_numbers)
    if missing:
        error("numeric_grounding", f"{case_id} has ungrounded numeric/unit values: {missing}.")


def _check_near_duplicates(cases: list[dict[str, Any]], error: Callable[[str, str], None]) -> None:
    tokenized = [(case, set(_normalize(str(case.get("question", ""))).split())) for case in cases]
    for (left, left_tokens), (right, right_tokens) in combinations(tokenized, 2):
        if not left_tokens or not right_tokens:
            continue
        union = left_tokens | right_tokens
        similarity = len(left_tokens & right_tokens) / len(union)
        if similarity > 0.90 and not (
            left.get("intentional_robustness_pair") and right.get("intentional_robustness_pair")
        ):
            error(
                "near_duplicate",
                f"{left['case_id']} and {right['case_id']} have Jaccard {similarity:.3f}.",
            )


def _check_text_encoding(dataset_dir: Path, error: Callable[[str, str], None]) -> None:
    for path in dataset_dir.iterdir():
        if not path.is_file() or path.suffix == ".xlsx":
            continue
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            error("utf8_bom", f"{path.name} must not contain a BOM.")
        if b"\r" in data:
            error("canonical_lf", f"{path.name} contains CR bytes.")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            error("utf8", f"{path.name} is not UTF-8.")


def _check_checksums(dataset_dir: Path, error: Callable[[str, str], None]) -> None:
    path = dataset_dir / "checksums.sha256"
    if not path.is_file():
        return
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError:
            error("checksum_format", f"Malformed checksum line: {line!r}.")
            continue
        entries[name] = digest
    expected = {item.name for item in dataset_dir.iterdir() if item.is_file() and item != path}
    if set(entries) != expected:
        error(
            "checksum_inventory",
            f"Checksum inventory missing={sorted(expected - set(entries))}, extra={sorted(set(entries) - expected)}.",
        )
    for name, digest in entries.items():
        target = dataset_dir / name
        if not target.is_file():
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != digest:
            error("checksum_mismatch", f"Checksum mismatch for {name}.")


def _check_sensitive_content(dataset_dir: Path, error: Callable[[str, str], None]) -> None:
    for path in dataset_dir.iterdir():
        if not path.is_file() or path.suffix == ".xlsx":
            continue
        text = path.read_text(encoding="utf-8")
        if SECRET_PATTERN.search(text):
            error("sensitive_content", f"Potential secret-like content in {path.name}.")
        if "%PDF" in text or "BEGIN PRIVATE KEY" in text:
            error("embedded_binary", f"Forbidden binary/secret content in {path.name}.")


def _xlsx_review_rows(path: Path, error: Callable[[str, str], None]) -> int:
    if not path.is_file():
        return 0
    try:
        with ZipFile(path) as archive:
            workbook = archive.read("xl/workbook.xml")
            if b"Review Queue" not in workbook:
                error("review_queue_sheet", "Workbook has no Review Queue sheet.")
        frame = __import__("pandas").read_excel(path, sheet_name="Review Queue")
    except Exception as exc:  # Workbook integrity is a validation result.
        error("review_queue_xlsx", f"Could not parse review workbook: {exc}")
        return 0
    if "SME Review Status" not in frame or set(frame["SME Review Status"].dropna()) != {"Pending"}:
        error("review_queue_state", "All workbook rows must remain Pending.")
    return len(frame)


def _normalize(value: str) -> str:
    folded = unicodedata.normalize("NFD", value.casefold())
    unaccented = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", unaccented).strip()


def _normalize_number(value: str) -> str:
    return re.sub(r"\s+", "", value.casefold().replace(",", "."))


def _json(path: Path, error: Callable[[str, str], None]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        error("invalid_json", f"Could not parse {path.name}: {exc}")
        return {}


def _jsonl(path: Path, error: Callable[[str, str], None]) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    output: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            error("invalid_jsonl", f"{path.name}:{number}: {exc.msg}")
            continue
        if isinstance(value, dict):
            output.append(value)
        else:
            error("invalid_jsonl_shape", f"{path.name}:{number} must be an object.")
    return output


def _csv(path: Path, error: Callable[[str, str], None]) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        error("invalid_csv", f"Could not parse {path.name}: {exc}")
        return []


def _index(
    records: list[dict[str, Any]],
    field: str,
    label: str,
    error: Callable[[str, str], None],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(record.get(field, ""))
        if not key or key in output:
            error("duplicate_identifier", f"Missing/duplicate {label} {field}: {key!r}.")
        else:
            output[key] = record
    return output
