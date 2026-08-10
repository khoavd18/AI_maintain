"""Closed scheduled-job catalog validation for deployment manifests.

This module validates in-memory deployment JSON only. The runtime catalog,
worker execution, durable leases, retries, and notifications remain owned by
the operations domain and PostgreSQL repository.
"""

from __future__ import annotations

from typing import Any

from ..constants import SUPPORTED_JOBS
from ..document_shapes import _list_of_mappings
from ..findings import _add
from ..schemas import Finding


def _validate_job_catalog(document: dict[str, Any], findings: list[Finding]) -> None:
    raw = document.get("scheduled_jobs")
    jobs = _list_of_mappings(
        raw,
        findings=findings,
        scope="manifest.scheduled_jobs",
    )
    if not isinstance(raw, list):
        _add(
            findings,
            "invalid_job_catalog",
            "manifest.scheduled_jobs",
            "scheduled_jobs phải là list.",
        )
    names: set[str] = set()
    for job in jobs:
        name = job.get("job_type")
        if not isinstance(name, str):
            _add(
                findings,
                "invalid_job_type",
                "manifest.scheduled_jobs",
                "Mỗi job phải có job_type.",
            )
            continue
        if name in names:
            _add(
                findings,
                "duplicate_job",
                f"manifest.scheduled_jobs.{name}",
                "Job bị khai báo trùng.",
            )
        names.add(name)
        if type(job.get("enabled")) is not bool:
            _add(
                findings,
                "job_enabled_not_explicit",
                f"manifest.scheduled_jobs.{name}",
                "Mỗi job phải có enabled kiểu boolean.",
            )
        if set(job) != {"job_type", "enabled"}:
            _add(
                findings,
                "job_configuration_not_closed",
                f"manifest.scheduled_jobs.{name}",
                "Deployment manifest không được nhận cấu hình executable tùy ý.",
            )
    for name in sorted(names - SUPPORTED_JOBS):
        _add(
            findings,
            "unsupported_job",
            f"manifest.scheduled_jobs.{name}",
            f"Job ngoài closed catalog: {name}.",
        )
    for name in sorted(SUPPORTED_JOBS - names):
        _add(
            findings,
            "supported_job_missing",
            f"manifest.scheduled_jobs.{name}",
            f"Closed catalog phải khai báo job {name} với enabled rõ ràng.",
        )
