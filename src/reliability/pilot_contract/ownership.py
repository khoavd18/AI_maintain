"""Operational ownership and limitation validation."""

from __future__ import annotations

from typing import Any

from .constants import (
    REQUIRED_OWNERS,
    REQUIRED_LIMITATIONS,
)

from .schemas import Finding
from .support import (
    _valid_evidence_links,
    _valid_utc_timestamp,
    _non_placeholder_text,
    _valid_iana_timezone,
    _versioned,
    _mapping,
    _list_of_mappings,
    _require_keys,
    _add,
)


def _validate_ownership(document: dict[str, Any], findings: list[Finding]) -> None:
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
    assignments = _mapping(document.get("assignments"))
    for key in REQUIRED_OWNERS:
        assignment = _mapping(assignments.get(key))
        if not assignment:
            _add(
                findings,
                "ownership_assignment_missing",
                f"ownership.assignments.{key}",
                f"Thiếu ownership assignment: {key}.",
            )
            continue
        if (
            assignment.get("status") != "assigned"
            or not _non_placeholder_text(assignment.get("assigned_role"))
            or not _non_placeholder_text(assignment.get("approved_internal_channel"))
        ):
            _add(
                findings,
                "ownership_placeholder",
                f"ownership.assignments.{key}",
                f"Ownership {key} chưa được gán rõ ràng.",
            )
        if assignment.get("status") == "assigned" and not _valid_evidence_links(
            assignment.get("approval_evidence_links")
        ):
            _add(
                findings,
                "ownership_evidence_missing",
                f"ownership.assignments.{key}",
                f"Ownership {key} thiếu approval evidence link.",
            )

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

    escalation = _mapping(document.get("escalation_path"))
    steps = _list_of_mappings(
        escalation.get("steps"),
        findings=findings,
        scope="ownership.escalation_path.steps",
    )
    if escalation.get("status") != "configured" or len(steps) < 2:
        _add(
            findings,
            "escalation_path_missing",
            "ownership.escalation_path",
            "Escalation path chưa được cấu hình đầy đủ.",
        )
    elif not _valid_evidence_links(escalation.get("approval_evidence_links")):
        _add(
            findings,
            "escalation_path_evidence_missing",
            "ownership.escalation_path",
            "Escalation path thiếu approval evidence link.",
        )
    seen_orders: set[int] = set()
    seen_owner_refs: set[str] = set()
    for step in steps:
        order = step.get("order")
        owner_ref = step.get("owner_ref")
        if (
            type(order) is not int
            or order < 1
            or owner_ref not in REQUIRED_OWNERS
            or not _non_placeholder_text(step.get("channel_ref"))
        ):
            _add(
                findings,
                "escalation_step_invalid",
                "ownership.escalation_path",
                "Escalation step phải tham chiếu owner và channel hợp lệ.",
            )
        if (
            isinstance(order, int)
            and not isinstance(order, bool)
            and isinstance(owner_ref, str)
            and (order in seen_orders or owner_ref in seen_owner_refs)
        ):
            _add(
                findings,
                "duplicate_escalation_step",
                "ownership.escalation_path",
                "Escalation path không được lặp order hoặc owner.",
            )
        if isinstance(order, int) and not isinstance(order, bool):
            seen_orders.add(order)
        if isinstance(owner_ref, str):
            seen_owner_refs.add(owner_ref)


def _validate_limitations(document: dict[str, Any], findings: list[Finding]) -> None:
    _require_keys(
        document,
        {"schema_version", "record_kind", "record_status", "limitations"},
        "limitations",
        findings,
    )
    if not _versioned(document):
        _add(
            findings,
            "invalid_schema_version",
            "limitations",
            "Known-limitations record phải có schema_version.",
        )
    if document.get("record_kind") != "internal_pilot_known_limitations_acceptance":
        _add(
            findings,
            "invalid_limitations_record_kind",
            "limitations.record_kind",
            "Known-limitations record kind không khớp internal-pilot contract.",
        )
    if document.get("record_status") != "accepted":
        _add(
            findings,
            "limitations_record_not_accepted",
            "limitations.record_status",
            "Known-limitations record chưa được accepted.",
        )
    rows = _list_of_mappings(
        document.get("limitations"),
        findings=findings,
        scope="limitations.limitations",
    )
    ids: set[str] = set()
    for row in rows:
        limitation_id = row.get("id")
        if not _non_placeholder_text(limitation_id):
            _add(
                findings,
                "limitation_id_missing",
                "limitations.limitations",
                "Mỗi limitation phải có id.",
            )
            continue
        if limitation_id in ids:
            _add(
                findings,
                "duplicate_limitation",
                f"limitations.{limitation_id}",
                "Known limitation bị khai báo trùng.",
            )
        ids.add(limitation_id)
        _require_keys(
            row,
            {
                "critical",
                "description",
                "operational_consequence",
                "mitigation",
                "owner_role",
                "acceptance_status",
                "review_trigger",
            },
            f"limitations.{limitation_id}",
            findings,
        )
        if type(row.get("critical")) is not bool:
            _add(
                findings,
                "limitation_criticality_invalid",
                f"limitations.{limitation_id}.critical",
                "Criticality của limitation phải là boolean.",
            )
        elif limitation_id in REQUIRED_LIMITATIONS and row.get("critical") is not True:
            _add(
                findings,
                "required_limitation_weakened",
                f"limitations.{limitation_id}.critical",
                "Known limitation bắt buộc không được hạ cấp khỏi critical.",
            )
        for key in (
            "description",
            "operational_consequence",
            "mitigation",
            "review_trigger",
        ):
            if not _non_placeholder_text(row.get(key)):
                _add(
                    findings,
                    "limitation_field_missing",
                    f"limitations.{limitation_id}.{key}",
                    "Limitation thiếu mô tả, hậu quả, mitigation hoặc review trigger.",
                )
        if not _non_placeholder_text(row.get("owner_role")):
            _add(
                findings,
                "limitation_owner_placeholder",
                f"limitations.{limitation_id}.owner_role",
                f"Limitation {limitation_id} chưa có owner role.",
            )
        status = row.get("acceptance_status")
        if not isinstance(status, str) or status not in {
            "accepted",
            "pending",
            "rejected",
        }:
            _add(
                findings,
                "limitation_acceptance_invalid",
                f"limitations.{limitation_id}.acceptance_status",
                "Acceptance status phải là accepted, pending hoặc rejected.",
            )
        if row.get("critical") is True and status != "accepted":
            _add(
                findings,
                "critical_limitation_unaccepted",
                f"limitations.{limitation_id}",
                f"Critical limitation chưa được chấp nhận: {limitation_id}.",
            )
        if status == "accepted":
            if (
                not _non_placeholder_text(row.get("accepted_by_role"))
                or not _valid_utc_timestamp(row.get("accepted_at_utc"))
                or not _valid_evidence_links(row.get("acceptance_evidence_links"))
            ):
                _add(
                    findings,
                    "limitation_acceptance_evidence_missing",
                    f"limitations.{limitation_id}",
                    "Acceptance phải có role, UTC timestamp và evidence link.",
                )
    for limitation_id in sorted(REQUIRED_LIMITATIONS - ids):
        _add(
            findings,
            "required_limitation_missing",
            f"limitations.{limitation_id}",
            f"Thiếu known limitation bắt buộc: {limitation_id}.",
        )


