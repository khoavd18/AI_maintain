"""Validate operational evidence attached to an internal-pilot release record."""

from __future__ import annotations

from typing import Any

from ..document_shapes import _mapping
from ..evidence_values import _valid_evidence_links, _valid_utc_timestamp
from ..findings import _add
from ..schemas import Finding


def _validate_release_record_evidence(
    record: dict[str, Any],
    findings: list[Finding],
) -> None:
    for section_name in (
        "backup_validation",
        "restore_validation",
        "attachment_restore",
        "secret_rotation",
    ):
        section = _mapping(record.get(section_name))
        if section.get("status") == "passed":
            if not _valid_utc_timestamp(
                section.get("validated_at_utc")
            ) or not _valid_evidence_links(section.get("evidence_links")):
                _add(
                    findings,
                    "validation_evidence_missing",
                    f"release_record.{section_name}",
                    f"{section_name} passed nhưng thiếu timestamp hoặc evidence.",
                )
        elif section.get("status") != "passed":
            _add(
                findings,
                "release_validation_open",
                f"release_record.{section_name}",
                f"{section_name} chưa có kết quả passed cho pilot.",
            )

    load_profiles = _mapping(record.get("load_and_soak_profiles"))
    if (
        load_profiles.get("status") != "passed"
        or not isinstance(load_profiles.get("summaries"), list)
        or not load_profiles.get("summaries")
        or not _valid_evidence_links(load_profiles.get("evidence_links"))
    ):
        _add(
            findings,
            "load_and_soak_evidence_open",
            "release_record.load_and_soak_profiles",
            "Load và soak profiles chưa có summary cùng evidence passed.",
        )
