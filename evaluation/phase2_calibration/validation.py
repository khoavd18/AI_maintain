"""Validate calibration artifacts without mutating prior benchmark checkpoints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluation.phase2_calibration.common import jsonl, sha256_file, write_json


def validate_calibration_dataset(dataset: Path, *, write_reports: bool = True) -> dict[str, Any]:
    cases, evidence, verification = (
        jsonl(dataset / "cases.jsonl"),
        jsonl(dataset / "evidence_chunks.jsonl"),
        jsonl(dataset / "evidence_verification.jsonl"),
    )
    errors: list[str] = []
    if len(cases) != 30:
        errors.append("expected exactly 30 cases")
    if len(evidence) != 152 or len(verification) != 152:
        errors.append("expected exactly 152 evidence rows")
    if len({row["chunk_id"] for row in evidence}) != 152:
        errors.append("evidence IDs must be unique")
    verified = {
        row["evidence_id"]
        for row in verification
        if row["semantic_verification_status"] == "MACHINE_VERIFIED"
    }
    for case in cases:
        if not case["required_evidence_ids"] and not case["manual_review_only"]:
            errors.append(f"missing evidence: {case['calibration_case_id']}")
        if case["calibration_status"] == "READY_FOR_SME" and not all(
            evidence_id in verified for evidence_id in case["required_evidence_ids"]
        ):
            errors.append(f"unverified ready claim evidence: {case['calibration_case_id']}")
        if case["promotion_eligible"] or case["sme_review_status"] != "pending":
            errors.append(f"governance drift: {case['calibration_case_id']}")
    checked = 0
    for line in (dataset / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        expected, name = line.split(maxsplit=1)
        checked += 1
        if sha256_file(dataset / name) != expected:
            errors.append(f"checksum mismatch: {name}")
    report = {
        "status": "PASS" if not errors else "FAIL",
        "error_count": len(errors),
        "errors": errors,
        "observed_counts": {
            "cases": len(cases),
            "evidence_reviews": len(verification),
            "checksums": checked,
        },
        "warning_count": 4,
        "warnings": [
            "document-derived only",
            "all SME review pending",
            "Grundfos and Generac currentness blocked",
            "no live LLM benchmark",
        ],
    }
    if write_reports:
        write_json(dataset / "validation_report.json", report)
        (dataset / "validation_report.md").write_text(
            f"# Calibration validation\n\nStatus: **{report['status']}**\n\nErrors: {report['error_count']}\n",
            encoding="utf-8",
            newline="\n",
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--no-write-report", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            validate_calibration_dataset(args.dataset, write_reports=not args.no_write_report),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
