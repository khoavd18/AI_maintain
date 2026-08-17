"""Artifact serialization for the Phase 2 v2 benchmark package."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pandas as pd

from evaluation.phase2_v2.case_text import _normalize_question
from evaluation.phase2_v2.dataset_spec import CATEGORY_QUOTA, DATASET_VERSION, FAMILIES
from evaluation.phase2_v2.integrity import _write_text


def _build_corpus(evidence: list[dict[str, Any]]) -> list[dict[str, str]]:
    family_by_source = {family.source_id: family for family in FAMILIES}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        grouped.setdefault(str(item["corpus_doc_id"]), []).append(item)
    rows: list[dict[str, str]] = []
    for document_id, items in grouped.items():
        family = family_by_source[items[0]["source_id"]]
        evidence_text = "\n".join(
            f"- {item['title_vi']}: {item['paraphrase_vi']}" for item in items
        )
        locators = " | ".join(
            f"{item['evidence_id']} PDF {item['locator']['pdf_page_1_based']} "
            f"printed {item['locator']['manual_page']} {item['locator']['section']}"
            for item in items
        )
        safety_tags = sorted({tag for item in items for tag in item["safety_tags"]})
        text = (
            f"Phạm vi: {family.model_scope}\n"
            f"Các đơn vị bằng chứng:\n{evidence_text}\n"
            f"An toàn: {', '.join(safety_tags) or 'không có tag riêng'}\n"
            f"Giới hạn: {family.currentness}; SME pending; không tự động quyết định bảo trì.\n"
            f"Tài liệu tham khảo: {family.source_id}; {locators}"
        )
        rows.append(
            {
                "doc_id": document_id,
                "title": f"{family.manufacturer} — captured OEM manual evidence collection",
                "doc_type": str(items[0]["document_type"]),
                "asset_type": family.asset_type,
                "source": family.official_url,
                "raw_text": text,
                "created_at": "2026-08-12T00:00:00+07:00",
                "failure_category": "",
                "version": DATASET_VERSION,
                "effective_date": "2026-08-12",
                "clean_text": text,
                "language": "vi",
            }
        )
    return rows


def _write_review_queue(
    path: Path,
    cases: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> None:
    queue = [
        {
            "Case ID": case["case_id"],
            "Family": case["asset_profile"]["manufacturer"],
            "Model Scope": case["model_applicability"],
            "Primary Category": case["primary_category"],
            "Language": case["language_variant"],
            "Risk": case["risk_level"],
            "Response Policy": case["response_policy"],
            "Question": case["question"],
            "Source ID": case["source_id"],
            "Evidence IDs": ", ".join(case["evidence_ids"]),
            "Currentness Gate": case["source_currentness_gate"],
            "SME Review Status": "Pending",
            "Promotion Eligible": "No",
            "Reviewer": "",
            "Review Date": "",
            "Decision": "",
            "Notes": "",
        }
        for case in cases
    ]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        writer.book.properties.creator = "openpyxl"
        fixed_timestamp = datetime(2026, 8, 12, 15, 20, 18, tzinfo=timezone.utc)
        writer.book.properties.created = fixed_timestamp
        writer.book.properties.modified = fixed_timestamp
        pd.DataFrame(queue).to_excel(writer, sheet_name="Review Queue", index=False)
        pd.DataFrame(sources).to_excel(writer, sheet_name="Sources", index=False)
        pd.DataFrame(evidence).to_excel(writer, sheet_name="Evidence", index=False)
        pd.DataFrame(
            [
                {"Metric": "Cases", "Value": len(cases)},
                {"Metric": "Evidence spans", "Value": len(evidence)},
                {"Metric": "Review status", "Value": "DRAFT_SME_REVIEW_REQUIRED"},
            ]
        ).to_excel(writer, sheet_name="Summary", index=False)
    _canonicalize_xlsx(
        path,
        core_created="2026-08-12T15:20:18Z",
        core_modified="2026-08-12T15:20:18Z",
        entry_timestamp=(2026, 8, 12, 22, 20, 18),
    )


def _manifest(
    cases: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    conversations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "dataset_id": "phase2-document-derived-v2-draft",
        "version": DATASET_VERSION,
        "provenance_type": "document_derived",
        "scenario_origin": "document_derived",
        "field_observed": False,
        "approval_state": "draft",
        "readiness": "DRAFT_SME_REVIEW_REQUIRED",
        "corpus": "official-oem-paraphrase-fixture-v2.0",
        "created_at": "2026-08-12T00:00:00+07:00",
        "counts": {
            "sources": 3,
            "asset_profiles": 3,
            "cases": len(cases),
            "cases_per_asset_profile": 100,
            "retrieval_questions": 300,
            "no_answer_cases": 30,
            "evidence_spans": len(evidence),
            "corpus_documents": len({item["corpus_doc_id"] for item in evidence}),
            "conversation_sequences": len(conversations),
            "conversation_turns": sum(len(row["turns"]) for row in conversations),
            "review_queue_rows": 300,
            "original_cases_preserved": 30,
            "new_cases": 270,
        },
        "quotas": {
            "primary_categories_per_family": dict(CATEGORY_QUOTA),
            "risk_per_family": {"critical": 15, "high": 25, "medium": 35, "low": 25},
            "language_total": {
                "vi_diacritics": 180,
                "vi_no_diacritics": 45,
                "en": 45,
                "mixed_vi_en": 30,
            },
            "response_policy_total": {
                "answer_with_evidence": 240,
                "refuse_insufficient_evidence": 30,
                "escalate_manual_review": 30,
            },
            "adversarial_unsafe": 30,
        },
        "files": {
            "sources": "source_registry.jsonl",
            "evidence": "evidence_spans.jsonl",
            "cases": "cases.jsonl",
            "questions": "retrieval_questions.jsonl",
            "conversations": "conversation_sequences.jsonl",
            "documents": "corpus_documents.csv",
            "review_queue": "review_queue.xlsx",
        },
        "limitations": [
            "All cases are document-derived drafts, not field-observed tickets or work orders.",
            "Grundfos and Generac source currentness remains VERSION_AMBIGUOUS and blocks promotion.",
            "Daikin source currentness passed, but every case remains pending qualified SME review.",
            "Deterministic hash retrieval is an integration fixture, not semantic or production accuracy.",
        ],
    }


def _schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Phase 2 v2 document-derived evaluation case",
        "type": "object",
        "required": [
            "case_id",
            "dataset_version",
            "scenario_origin",
            "field_observed",
            "source_id",
            "model_applicability",
            "source_currentness_status",
            "sme_review_status",
            "promotion_eligible",
            "risk_level",
            "response_policy",
            "question",
            "evidence_ids",
            "expected_document_ids",
        ],
        "properties": {
            "dataset_version": {"const": DATASET_VERSION},
            "scenario_origin": {"const": "document_derived"},
            "field_observed": {"const": False},
            "promotion_eligible": {"const": False},
            "sme_review_status": {"const": "pending"},
            "risk_level": {"enum": ["critical", "high", "medium", "low"]},
            "response_policy": {
                "enum": [
                    "answer_with_evidence",
                    "refuse_insufficient_evidence",
                    "escalate_manual_review",
                ]
            },
        },
    }


def _readme() -> str:
    return """# Phase 2 Document-Derived Evaluation — Draft v2.0.0

This additive package contains exactly 300 source-traceable draft cases: 100 each for Grundfos CR 1/3/5 Model A, Daikin RZAG71-140N, and Generac Mobile MLG15 SN 3004595385+.

The wording is synthetic but grounded in concise paraphrases of captured official OEM documents. It is not field-observed history, an approved SOP, or an automatic maintenance decision. The original 30 v1 questions and rubrics are logically preserved; 270 cases are new.

Grundfos and Generac remain `VERSION_AMBIGUOUS` and source-currentness blocked. Daikin is `VERIFIED_CURRENT`, but all 300 cases remain `pending` SME review and `promotion_eligible: false`.

Full copyrighted PDFs are not included. Validate with:

```bash
python -m evaluation.validate_phase2_dataset evaluation/datasets/phase2_document_derived_v2
```

The deterministic in-memory evaluation is a wiring and retrieval fixture, not semantic, field, production, or SME-approved accuracy.
"""


def _qa_report(cases: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> str:
    questions = [str(case["question"]) for case in cases]
    normalized = [_normalize_question(item) for item in questions]
    return f"""# Phase 2 v2 Dataset — QA Report

Status: **DRAFT_SME_REVIEW_REQUIRED**

## Construction summary

- Cases: {len(cases)} (30 logically preserved from v1; 270 new).
- Families: 100 pump, 100 HVAC, 100 generator.
- Evidence spans/corpus documents: {len(evidence)} ({dict(Counter(item["source_id"] for item in evidence))}).
- Review rows: 300, all Pending.
- Field-observed cases: 0.

## Duplicate analysis

- Unique case IDs: {len({case["case_id"] for case in cases})}/300.
- Unique normalized questions: {len(set(normalized))}/300.
- Exact duplicate normalized questions: {len(normalized) - len(set(normalized))}.
- Intentional robustness variants: {sum(bool(case["intentional_robustness_pair"]) for case in cases)} ({sum(bool(case["intentional_robustness_pair"]) for case in cases) / 300:.1%}; limit 15%).
- Near-duplicate gate: token-set Jaccard threshold 0.90; intentional robustness pairs are explicitly tagged and no untagged pair may exceed the threshold.

Cases vary by diagnostic goal, operational context, applicability condition, evidence need, response policy, or language. The validator is authoritative for quota, referential, numeric-grounding, UTF-8/LF, secret, checksum, and duplicate gates.

## Source promotion gates

- Daikin: VERIFIED_CURRENT / MEDIUM; source gate passed, SME pending.
- Grundfos: VERSION_AMBIGUOUS / HIGH; source gate blocked. Captured artifact identifies `96546866 03.2022` while the v1 registry named `96546866 0407 GB`; OEM resolution remains required.
- Generac: VERSION_AMBIGUOUS / HIGH; source gate blocked.

No deterministic fixture metric is a production, semantic, field, or SME-approved accuracy claim.
"""


def _canonicalize_xlsx(
    path: Path,
    *,
    core_created: str,
    core_modified: str,
    entry_timestamp: tuple[int, int, int, int, int, int],
) -> None:
    core_xml = (
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
        'core-properties"><dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">openpyxl'
        f'</dc:creator><dcterms:created xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xsi:type="dcterms:W3CDTF">{core_created}</dcterms:created>'
        f'<dcterms:modified xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xsi:type="dcterms:W3CDTF">{core_modified}</dcterms:modified></cp:coreProperties>'
    )
    original = path.read_bytes()
    with ZipFile(path, "r") as source:
        infos = source.infolist()
        payloads = {
            info.filename: (
                core_xml.encode("utf-8")
                if info.filename == "docProps/core.xml"
                else source.read(info.filename)
            )
            for info in infos
        }
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as target:
        for info in infos:
            data = payloads[info.filename]
            rewritten = ZipInfo(info.filename, date_time=entry_timestamp)
            rewritten.compress_type = ZIP_DEFLATED
            rewritten.comment = info.comment
            rewritten.extra = b""
            rewritten.create_system = info.create_system
            rewritten.create_version = info.create_version
            rewritten.extract_version = info.extract_version
            rewritten.flag_bits = info.flag_bits
            rewritten.internal_attr = info.internal_attr
            rewritten.external_attr = info.external_attr
            rewritten.volume = info.volume
            rewritten.compress_size = 0
            rewritten.file_size = len(data)
            target.writestr(rewritten, data)
    if path.read_bytes() == original:
        return


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    _write_text(
        path,
        "".join(
            json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in records
        ),
    )


def _write_json(path: Path, value: dict[str, Any]) -> None:
    _write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _write_csv(path: Path, records: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
