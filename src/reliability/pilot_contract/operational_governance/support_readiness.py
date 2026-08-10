"""Incident communication and support-coverage validation."""

from __future__ import annotations

from typing import Any

from ..document_shapes import _mapping
from ..document_values import _non_placeholder_text, _valid_iana_timezone
from ..evidence_values import _valid_evidence_links
from ..findings import _add
from ..schemas import Finding


def _validate_incident_communication(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
    incident = _mapping(document.get("incident_communication"))
    if (
        incident.get("status") != "configured"
        or not _non_placeholder_text(incident.get("primary_internal_channel"))
        or not _non_placeholder_text(incident.get("fallback_internal_channel"))
    ):
        _add(
            findings,
            "incident_path_missing",
            "ownership.incident_communication",
            "Incident communication path chưa được cấu hình.",
        )
    elif not _valid_evidence_links(incident.get("approval_evidence_links")):
        _add(
            findings,
            "incident_path_evidence_missing",
            "ownership.incident_communication",
            "Incident communication path thiếu approval evidence link.",
        )


def _validate_support_coverage(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
    coverage = _mapping(document.get("support_coverage"))
    if (
        coverage.get("status") != "confirmed"
        or not _non_placeholder_text(coverage.get("support_hours"))
        or not _non_placeholder_text(coverage.get("after_hours_assumption"))
        or not _non_placeholder_text(coverage.get("timezone"))
    ):
        _add(
            findings,
            "support_coverage_unconfirmed",
            "ownership.support_coverage",
            "Support hours hoặc coverage assumptions chưa được xác nhận.",
        )
    elif not _valid_iana_timezone(coverage.get("timezone")):
        _add(
            findings,
            "support_timezone_invalid",
            "ownership.support_coverage.timezone",
            "Support coverage phải dùng timezone IANA hợp lệ.",
        )
    elif not _valid_evidence_links(coverage.get("approval_evidence_links")):
        _add(
            findings,
            "support_coverage_evidence_missing",
            "ownership.support_coverage",
            "Support coverage thiếu approval evidence link.",
        )
