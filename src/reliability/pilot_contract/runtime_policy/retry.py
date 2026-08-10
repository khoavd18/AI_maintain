"""Closed job-catalog retry, outbox, and dead-letter policy validation."""

from __future__ import annotations

from typing import Any

from ..constants import SUPPORTED_JOBS
from ..document_shapes import _mapping
from ..findings import _add
from ..schemas import Finding


def _validate_retry_and_dead_letter(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
    retry = _mapping(document.get("retry_and_dead_letter"))
    jobs = _mapping(retry.get("jobs"))
    if set(jobs) != SUPPORTED_JOBS:
        _add(
            findings,
            "retry_job_catalog_mismatch",
            "manifest.retry_and_dead_letter.jobs",
            "Retry settings phải khớp đúng closed four-job catalog.",
        )
    for name, row_value in jobs.items():
        row = _mapping(row_value)
        for key in ("max_attempts", "lease_seconds", "retry_backoff_seconds"):
            if type(row.get(key)) is not int or row.get(key) <= 0:
                _add(
                    findings,
                    "invalid_retry_setting",
                    f"manifest.retry_and_dead_letter.jobs.{name}.{key}",
                    "Retry setting phải là số nguyên dương.",
                )
    outbox = _mapping(retry.get("outbox"))
    for key in ("max_attempts", "retry_backoff_seconds"):
        if type(outbox.get(key)) is not int or outbox.get(key) <= 0:
            _add(
                findings,
                "invalid_outbox_retry_setting",
                f"manifest.retry_and_dead_letter.outbox.{key}",
                "Outbox retry setting phải là số nguyên dương.",
            )
    if (
        retry.get("dead_letter_operator_visible") is not True
        or retry.get("manual_redrive_only") is not True
    ):
        _add(
            findings,
            "dead_letter_contract_weakened",
            "manifest.retry_and_dead_letter",
            "Dead letter phải operator-visible và chỉ redrive bằng action rõ ràng.",
        )
