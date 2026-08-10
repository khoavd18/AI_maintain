"""Required operational-owner assignment validation."""

from __future__ import annotations

from typing import Any

from ..constants import REQUIRED_OWNERS
from ..document_shapes import _mapping
from ..document_values import _non_placeholder_text
from ..evidence_values import _valid_evidence_links
from ..findings import _add
from ..schemas import Finding


def _validate_owner_assignments(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
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
