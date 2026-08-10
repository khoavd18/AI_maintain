"""Validate release governance summaries and rollback metadata."""

from __future__ import annotations

from typing import Any

from ..constants import REQUIRED_OWNERS
from ..document_shapes import _mapping
from ..evidence_values import _valid_evidence_links
from ..findings import _add
from ..operational_governance.state import _critical_limitations_accepted
from ..schemas import Finding


def _validate_release_record_governance(
    record: dict[str, Any],
    manifest: dict[str, Any],
    ownership: dict[str, Any],
    limitations: dict[str, Any],
    findings: list[Finding],
) -> None:
    if not _valid_evidence_links(record.get("evidence_links")):
        _add(
            findings,
            "release_evidence_links_missing",
            "release_record.evidence_links",
            "Release record phải có ít nhất một evidence-document link.",
        )
    if record.get("known_limitations_acceptance_status") != (
        "accepted" if _critical_limitations_accepted(limitations) else "pending"
    ):
        _add(
            findings,
            "limitation_summary_mismatch",
            "release_record.known_limitations_acceptance_status",
            "Known-limitations summary không khớp acceptance record.",
        )
    expected_incident = _mapping(ownership.get("incident_communication")).get("status")
    if record.get("incident_contact_status") != expected_incident:
        _add(
            findings,
            "incident_summary_mismatch",
            "release_record.incident_contact_status",
            "Incident-contact summary không khớp ownership record.",
        )
    assignments = _mapping(ownership.get("assignments"))
    expected_owner_status = {
        key: _mapping(assignments.get(key)).get("status", "unassigned") for key in REQUIRED_OWNERS
    }
    if record.get("ownership_status") != expected_owner_status:
        _add(
            findings,
            "ownership_summary_mismatch",
            "release_record.ownership_status",
            "Ownership summary không khớp operational ownership record.",
        )
    rollback_manifest = _mapping(manifest.get("rollback"))
    rollback_record = _mapping(record.get("rollback"))
    for key in (
        "target_release_id",
        "target_git_tag",
        "target_git_commit",
        "target_alembic_revision",
        "mode",
    ):
        if rollback_record.get(key) != rollback_manifest.get(key):
            _add(
                findings,
                "rollback_metadata_mismatch",
                f"release_record.rollback.{key}",
                "Rollback metadata không khớp deployment manifest.",
            )
