"""Readiness predicates for ownership, limitations, and bounded conditions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..constants import REQUIRED_LIMITATIONS, REQUIRED_OWNERS
from ..document_shapes import _mapping
from ..document_values import _non_placeholder_text, _valid_iana_timezone
from ..evidence_values import _valid_evidence_links, _valid_utc_timestamp


def _ownership_ready(document: dict[str, Any]) -> bool:
    if (
        document.get("record_kind") != "internal_pilot_operational_ownership"
        or document.get("record_status") != "approved"
    ):
        return False
    assignments = _mapping(document.get("assignments"))
    for key in REQUIRED_OWNERS:
        assignment = _mapping(assignments.get(key))
        if (
            assignment.get("status") != "assigned"
            or not _non_placeholder_text(assignment.get("assigned_role"))
            or not _non_placeholder_text(assignment.get("approved_internal_channel"))
            or not _valid_evidence_links(assignment.get("approval_evidence_links"))
        ):
            return False
    incident = _mapping(document.get("incident_communication"))
    if (
        incident.get("status") != "configured"
        or not _non_placeholder_text(incident.get("primary_internal_channel"))
        or not _non_placeholder_text(incident.get("fallback_internal_channel"))
        or not _valid_evidence_links(incident.get("approval_evidence_links"))
    ):
        return False
    coverage = _mapping(document.get("support_coverage"))
    if (
        coverage.get("status") != "confirmed"
        or not _non_placeholder_text(coverage.get("support_hours"))
        or not _non_placeholder_text(coverage.get("after_hours_assumption"))
        or not _valid_iana_timezone(coverage.get("timezone"))
        or not _valid_evidence_links(coverage.get("approval_evidence_links"))
    ):
        return False
    escalation = _mapping(document.get("escalation_path"))
    raw_steps = escalation.get("steps")
    if not isinstance(raw_steps, list) or any(not isinstance(step, Mapping) for step in raw_steps):
        return False
    steps = [dict(step) for step in raw_steps]
    orders = [step.get("order") for step in steps]
    owner_refs = [step.get("owner_ref") for step in steps]
    return (
        escalation.get("status") == "configured"
        and _valid_evidence_links(escalation.get("approval_evidence_links"))
        and len(steps) >= 2
        and all(type(order) is int and order >= 1 for order in orders)
        and len(set(orders)) == len(orders)
        and all(isinstance(owner_ref, str) for owner_ref in owner_refs)
        and len(set(owner_refs)) == len(owner_refs)
        and all(
            step.get("owner_ref") in REQUIRED_OWNERS
            and _non_placeholder_text(step.get("channel_ref"))
            for step in steps
        )
    )


def _critical_limitations_accepted(document: dict[str, Any]) -> bool:
    if (
        document.get("record_kind") != "internal_pilot_known_limitations_acceptance"
        or document.get("record_status") != "accepted"
    ):
        return False
    raw_rows = document.get("limitations")
    if not isinstance(raw_rows, list) or any(not isinstance(row, Mapping) for row in raw_rows):
        return False
    rows = [dict(row) for row in raw_rows]
    row_ids = [row.get("id") for row in rows]
    if any(not _non_placeholder_text(row_id) for row_id in row_ids):
        return False
    ids = set(row_ids)
    if len(ids) != len(rows):
        return False
    if not REQUIRED_LIMITATIONS.issubset(ids):
        return False
    for row in rows:
        limitation_id = row.get("id")
        is_required = limitation_id in REQUIRED_LIMITATIONS
        if is_required and row.get("critical") is not True:
            return False
        status = row.get("acceptance_status")
        if not isinstance(status, str) or status not in {"accepted", "pending", "rejected"}:
            return False
        if row.get("critical") is False and not is_required:
            continue
        if row.get("critical") is not True:
            return False
        if (
            row.get("acceptance_status") != "accepted"
            or not _non_placeholder_text(row.get("owner_role"))
            or not _non_placeholder_text(row.get("accepted_by_role"))
            or not _valid_utc_timestamp(row.get("accepted_at_utc"))
            or not _valid_evidence_links(row.get("acceptance_evidence_links"))
            or not _non_placeholder_text(row.get("review_trigger"))
        ):
            return False
    return True


def _condition_is_bounded(condition: Mapping[str, Any]) -> bool:
    return all(
        (
            _non_placeholder_text(condition.get("description")),
            _non_placeholder_text(condition.get("owner_role")),
            _non_placeholder_text(condition.get("mitigation")),
            _non_placeholder_text(condition.get("review_trigger")),
            _non_placeholder_text(condition.get("pilot_scope_limit")),
            _valid_evidence_links(condition.get("evidence_links")),
        )
    )
