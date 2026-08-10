"""Ordered operational-ownership record validation."""

from __future__ import annotations

from typing import Any

from ..document_shapes import _require_keys, _versioned
from ..findings import _add
from ..schemas import Finding
from .assignments import _validate_owner_assignments
from .escalation_path import _validate_escalation_path
from .support_readiness import _validate_incident_communication, _validate_support_coverage


def _validate_ownership(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
    _require_keys(
        document,
        {
            "schema_version",
            "record_kind",
            "record_status",
            "assignments",
            "incident_communication",
            "support_coverage",
            "escalation_path",
        },
        "ownership",
        findings,
    )
    if not _versioned(document):
        _add(
            findings,
            "invalid_schema_version",
            "ownership",
            "Ownership record phải có schema_version.",
        )
    if document.get("record_kind") != "internal_pilot_operational_ownership":
        _add(
            findings,
            "invalid_ownership_record_kind",
            "ownership.record_kind",
            "Ownership record kind không khớp internal-pilot contract.",
        )
    if document.get("record_status") != "approved":
        _add(
            findings,
            "ownership_record_not_approved",
            "ownership.record_status",
            "Ownership record chưa được approved.",
        )
    _validate_owner_assignments(document, findings)
    _validate_incident_communication(document, findings)
    _validate_support_coverage(document, findings)
    _validate_escalation_path(document, findings)
