"""Build the bounded 30-case calibration dataset without touching v1 or v2."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.phase2_calibration.common import (
    jsonl,
    sha256_file,
    write_csv,
    write_json,
    write_jsonl,
)
from evaluation.phase2_calibration.verification import (
    evidence_verification_rows,
    verify_vault_checksums,
)

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "evaluation/datasets/phase2_document_derived_v1"
V2 = ROOT / "evaluation/datasets/phase2_document_derived_v2"
DEFAULT_OUTPUT = ROOT / "evaluation/datasets/phase2_semantic_calibration_v1"


def build_calibration_dataset(output: Path = DEFAULT_OUTPUT) -> None:
    """Write the calibration package once; refuse overwrite to protect reproducibility."""

    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing calibration dataset: {output}")
    if verify_vault_checksums() != 20:
        raise ValueError("External evidence vault did not verify.")
    output.mkdir(parents=True)
    v1_cases, v2_cases, evidence, sources = (
        jsonl(V1 / "cases.jsonl"),
        jsonl(V2 / "cases.jsonl"),
        jsonl(V2 / "evidence_spans.jsonl"),
        jsonl(V2 / "source_registry.jsonl"),
    )
    verification = evidence_verification_rows(evidence)
    verified = {
        row["evidence_id"]
        for row in verification
        if row["semantic_verification_status"] == "MACHINE_VERIFIED"
    }
    cases = _calibration_cases(v1_cases, v2_cases, verified)
    chunks = _chunks(evidence, verification)
    questions = _questions(cases)
    write_jsonl(output / "source_registry.jsonl", sources)
    write_csv(
        output / "corpus_documents.csv",
        _corpus_rows(chunks),
        [
            "doc_id",
            "title",
            "doc_type",
            "asset_type",
            "source",
            "clean_text",
            "created_at",
            "failure_category",
            "version",
            "effective_date",
            "language",
        ],
    )
    write_jsonl(output / "evidence_verification.jsonl", verification)
    write_jsonl(output / "evidence_chunks.jsonl", chunks)
    write_jsonl(output / "cases.jsonl", cases)
    write_jsonl(output / "retrieval_questions.jsonl", questions)
    _review_queue(output, cases)
    write_json(output / "manifest.json", _manifest(cases, chunks, verification))
    write_json(output / "schema.json", _schema())
    (output / "README.md").write_text(_readme(), encoding="utf-8", newline="\n")
    (output / "QA_REPORT.md").write_text(
        _qa_report(cases, verification), encoding="utf-8", newline="\n"
    )
    _write_checksums(output)


def _calibration_cases(
    v1_cases: list[dict[str, Any]], v2_cases: list[dict[str, Any]], verified: set[str]
) -> list[dict[str, Any]]:
    v2_by_id = {row["case_id"]: row for row in v2_cases}
    rows: list[dict[str, Any]] = []
    for original in v1_cases:
        v2 = v2_by_id[original["case_id"]]
        evidence_ids = v2["evidence_ids"]
        state = (
            "READY_FOR_SME"
            if all(item in verified for item in evidence_ids)
            else "BLOCKED_EVIDENCE_REVIEW"
        )
        rubric = original["gold_rubric"]
        rows.append(
            {
                "calibration_case_id": f"CAL-{original['case_id']}",
                "dataset_version": "1.0.0-draft",
                "original_v1_case_id": original["case_id"],
                "original_v2_case_id": v2["case_id"],
                "question": original["question"],
                "intent": original["intent"],
                "expected_behavior": original["expected_behavior"],
                "asset_profile": original["asset_profile"],
                "source_id": v2["source_id"],
                "model_applicability": v2["model_applicability"],
                "source_currentness_status": v2["source_currentness_status"],
                "source_currentness_gate": v2["source_currentness_gate"],
                "field_observed": False,
                "scenario_origin": "document_derived",
                "sme_review_status": "pending",
                "promotion_eligible": False,
                "manual_review_only": not bool(original["runner_eligible"]),
                "calibration_status": state,
                "required_evidence_ids": evidence_ids,
                "acceptable_evidence_alternatives": [],
                "atomic_required_claims": [
                    {"claim": claim, "evidence_ids": evidence_ids}
                    for claim in rubric["must_include"]
                ],
                "atomic_prohibited_claims": rubric["must_not_claim"],
                "required_applicability_statements": [v2["model_applicability"]],
                "required_safety_statements": rubric["safety_requirements"],
                "required_refusal_or_escalation_behavior": original["expected_behavior"]
                if not original["runner_eligible"]
                else None,
                "numeric_unit_tolerance": "exact stated value and unit"
                if any("Nm" in claim or "VDC" in claim for claim in rubric["must_include"])
                else None,
                "citation_required": True,
                "measurable_pass_fail_rubric": "Pass only if every required claim and safety/applicability statement is present, no prohibited claim is made, and required evidence is cited.",
                "critical_failure_conditions": [
                    "unsupported numeric value",
                    "wrong-model guidance",
                    "unsafe action recommendation",
                    "missing required refusal",
                ],
            }
        )
    return rows


def _chunks(
    evidence: list[dict[str, Any]], verification: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {row["evidence_id"]: row for row in verification}
    rows = []
    for index, item in enumerate(evidence, start=1):
        review = by_id[item["evidence_id"]]
        rows.append(
            {
                "chunk_id": item["evidence_id"],
                "doc_id": item["corpus_doc_id"],
                "title": item["title_vi"],
                "doc_type": item["document_type"],
                "asset_type": _asset_type(item["source_id"]),
                "source": item["source_id"],
                "text": item["paraphrase_vi"],
                "failure_category": item["failure_category"],
                "version": "1.0.0-draft",
                "effective_date": "",
                "language": "vi",
                "chunk_index": index,
                "verification_status": review["semantic_verification_status"],
            }
        )
    return rows


def _asset_type(source_id: str) -> str:
    return {
        "SRC-GF-CR5-0407": "Máy bơm nước",
        "SRC-DAIKIN-RZAG-4P695307-1B": "Máy lạnh",
        "SRC-GENERAC-MLG15-A0000381158": "Máy phát điện dự phòng",
    }[source_id]


def _questions(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        policy = "answer_with_evidence" if not case["manual_review_only"] else "manual_review"
        rows.append(
            {
                "id": case["calibration_case_id"],
                "question": case["question"],
                "asset_type": case["asset_profile"]["asset_type"],
                "selected_asset_id": case["asset_profile"]["asset_profile_id"],
                "model_applicability": case["model_applicability"],
                "response_policy": policy,
                "expected_evidence_ids": case["required_evidence_ids"],
                "expected_status": case["required_refusal_or_escalation_behavior"],
                "manual_review_only": case["manual_review_only"],
            }
        )
    return rows


def _corpus_rows(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": row["chunk_id"],
            "title": row["title"],
            "doc_type": row["doc_type"],
            "asset_type": row["asset_type"],
            "source": row["source"],
            "clean_text": row["text"],
            "created_at": "2026-08-13",
            "failure_category": row["failure_category"],
            "version": "1.0.0-draft",
            "effective_date": "",
            "language": "vi",
        }
        for row in chunks
    ]


def _review_queue(output: Path, cases: list[dict[str, Any]]) -> None:
    rows = [
        {
            "Calibration Case ID": c["calibration_case_id"],
            "Original v1": c["original_v1_case_id"],
            "Original v2": c["original_v2_case_id"],
            "Status": "Pending",
            "Calibration status": c["calibration_status"],
            "Reviewer": "",
            "Decision": "",
            "Notes": "",
        }
        for c in cases
    ]
    with pd.ExcelWriter(output / "review_queue.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Review Queue", index=False)


def _manifest(
    cases: list[dict[str, Any]], chunks: list[dict[str, Any]], verification: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "dataset_id": "phase2-semantic-calibration-v1",
        "version": "1.0.0-draft",
        "readiness": "DRAFT_SME_REVIEW_REQUIRED",
        "provenance_type": "document_derived",
        "counts": {
            "cases": len(cases),
            "pump_cases": 10,
            "hvac_cases": 10,
            "generator_cases": 10,
            "evidence_reviews": len(verification),
            "evidence_chunks": len(chunks),
            "review_queue_rows": 30,
            "machine_verified_evidence": sum(
                row["semantic_verification_status"] == "MACHINE_VERIFIED" for row in verification
            ),
            "rendered_page_remediations": sum(
                row.get("remediation") is not None for row in verification
            ),
        },
        "limitations": [
            "The v2 270 generated cases are not remediated.",
            "No case is SME-approved and machine verification is not SME verification.",
            "No live generation benchmark was run.",
            "Grundfos and Generac remain source-currentness blocked.",
        ],
    }


def _schema() -> dict[str, Any]:
    return {
        "version": "1.0.0-draft",
        "case_required": [
            "calibration_case_id",
            "original_v1_case_id",
            "original_v2_case_id",
            "required_evidence_ids",
            "atomic_required_claims",
            "promotion_eligible",
        ],
        "evidence_review_required": [
            "evidence_id",
            "source_anchor_max_12_words",
            "normalized_source_fragment_sha256",
            "semantic_verification_status",
        ],
    }


def _readme() -> str:
    return "# Phase 2 semantic calibration v1\n\nA 30-case, document-derived draft calibration set. Five previous locator-extraction gaps were resolved by automated rendered-page verification of the captured OEM PDFs; this is not human or SME approval. The set does not validate the remaining 270 generated v2 cases, constitute SME approval, or report live-LLM results. Grundfos and Generac remain promotion-blocked.\n"


def _qa_report(cases: list[dict[str, Any]], verification: list[dict[str, Any]]) -> str:
    ready = sum(c["calibration_status"] == "READY_FOR_SME" for c in cases)
    verified = sum(r["semantic_verification_status"] == "MACHINE_VERIFIED" for r in verification)
    remediated = sum(r.get("remediation") is not None for r in verification)
    return f"# QA report\n\n- Calibration cases: {len(cases)}\n- Ready for SME review: {ready}\n- Machine-verified evidence rows: {verified}/{len(verification)}\n- Rendered-page evidence remediations: {remediated}\n- No live LLM ran.\n"


def _write_checksums(output: Path) -> None:
    files = sorted(
        path for path in output.iterdir() if path.is_file() and path.name != "checksums.sha256"
    )
    (output / "checksums.sha256").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in files),
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build_calibration_dataset(args.output)


if __name__ == "__main__":
    main()
