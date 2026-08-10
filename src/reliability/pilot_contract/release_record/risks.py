"""Validate the bounded open-risk register in a pilot release record."""

from __future__ import annotations

from typing import Any

from ..constants import ALLOWED_RISK_CATEGORIES, ALLOWED_RISK_SEVERITIES, ALLOWED_RISK_STATUSES
from ..document_shapes import _list_of_mappings
from ..document_values import _non_placeholder_text
from ..findings import _add
from ..schemas import Finding


def _validate_release_record_risks(
    record: dict[str, Any],
    findings: list[Finding],
) -> None:
    risks = _list_of_mappings(
        record.get("open_risks"),
        findings=findings,
        scope="release_record.open_risks",
    )
    risk_ids: set[str] = set()
    for risk in risks:
        risk_id = risk.get("id")
        if not _non_placeholder_text(risk_id):
            _add(
                findings,
                "risk_id_missing",
                "release_record.open_risks",
                "Mỗi risk phải có id không phải placeholder.",
            )
        elif risk_id in risk_ids:
            _add(
                findings,
                "duplicate_risk",
                f"release_record.open_risks.{risk_id}",
                "Risk không được khai báo trùng.",
            )
        else:
            risk_ids.add(risk_id)
        status = risk.get("status")
        if not isinstance(status, str) or status not in ALLOWED_RISK_STATUSES:
            _add(
                findings,
                "risk_status_invalid",
                f"release_record.open_risks.{risk_id}",
                "Danh sách open_risks chỉ chấp nhận status open.",
            )
        severity = risk.get("severity")
        if not isinstance(severity, str) or severity not in ALLOWED_RISK_SEVERITIES:
            _add(
                findings,
                "risk_severity_invalid",
                f"release_record.open_risks.{risk_id}",
                "Risk severity nằm ngoài allow-list.",
            )
        category = risk.get("category")
        if not isinstance(category, str) or category not in ALLOWED_RISK_CATEGORIES:
            _add(
                findings,
                "risk_category_invalid",
                f"release_record.open_risks.{risk_id}",
                "Risk category nằm ngoài allow-list.",
            )
