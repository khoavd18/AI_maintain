"""Ordered known-limitations acceptance-record validation."""

from __future__ import annotations

from typing import Any

from ..constants import REQUIRED_LIMITATIONS
from ..document_shapes import _list_of_mappings, _require_keys, _versioned
from ..document_values import _non_placeholder_text
from ..findings import _add
from ..schemas import Finding
from .limitation_entry import _validate_limitation_entry


def _validate_limitations(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
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
        _validate_limitation_entry(row, limitation_id, findings)
    for limitation_id in sorted(REQUIRED_LIMITATIONS - ids):
        _add(
            findings,
            "required_limitation_missing",
            f"limitations.{limitation_id}",
            f"Thiếu known limitation bắt buộc: {limitation_id}.",
        )
