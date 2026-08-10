"""Ordered operational-escalation path validation."""

from __future__ import annotations

from typing import Any

from ..constants import REQUIRED_OWNERS
from ..document_shapes import _list_of_mappings, _mapping
from ..document_values import _non_placeholder_text
from ..evidence_values import _valid_evidence_links
from ..findings import _add
from ..schemas import Finding


def _validate_escalation_path(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
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
