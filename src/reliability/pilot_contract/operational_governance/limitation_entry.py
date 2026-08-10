"""One known-limitation row's semantic and evidence validation."""

from __future__ import annotations

from typing import Any

from ..constants import REQUIRED_LIMITATIONS
from ..document_shapes import _require_keys
from ..document_values import _non_placeholder_text
from ..evidence_values import _valid_evidence_links, _valid_utc_timestamp
from ..findings import _add
from ..schemas import Finding


def _validate_limitation_entry(
    row: dict[str, Any],
    limitation_id: str,
    findings: list[Finding],
) -> None:
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
