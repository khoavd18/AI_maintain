"""Declared environment names and secret flags in the deployment manifest."""

from __future__ import annotations

from typing import Any

from ..constants import (
    REQUIRED_PILOT_ENVIRONMENT,
    SECRET_ENVIRONMENT_NAMES,
    _ENV_NAME_RE,
)
from ..document_shapes import _list_of_mappings
from ..findings import _add
from ..schemas import Finding


def _validate_environment_declarations(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
    raw = document.get("required_environment_variables")
    rows = _list_of_mappings(
        raw,
        findings=findings,
        scope="manifest.required_environment_variables",
    )
    if not isinstance(raw, list):
        _add(
            findings,
            "invalid_environment_contract",
            "manifest.required_environment_variables",
            "required_environment_variables phải là list chỉ chứa tên và secret flag.",
        )
    names: set[str] = set()
    for row in rows:
        name = row.get("name")
        if not isinstance(name, str) or not _ENV_NAME_RE.fullmatch(name):
            _add(
                findings,
                "invalid_environment_name",
                "manifest.required_environment_variables",
                "Environment variable phải có tên uppercase hợp lệ.",
            )
            continue
        if name in names:
            _add(
                findings,
                "duplicate_environment_name",
                f"manifest.required_environment_variables.{name}",
                "Environment variable bị khai báo trùng.",
            )
        names.add(name)
        if set(row) - {"name", "secret"}:
            _add(
                findings,
                "environment_value_in_manifest",
                f"manifest.required_environment_variables.{name}",
                "Manifest chỉ được ghi tên environment variable và secret flag.",
            )
        if type(row.get("secret")) is not bool:
            _add(
                findings,
                "environment_secret_flag_missing",
                f"manifest.required_environment_variables.{name}",
                "Mỗi environment variable phải có secret flag kiểu boolean.",
            )
    for name in sorted(REQUIRED_PILOT_ENVIRONMENT - names):
        _add(
            findings,
            "required_environment_name_missing",
            f"manifest.required_environment_variables.{name}",
            f"Thiếu tên environment variable bắt buộc: {name}.",
        )
    flags = {row.get("name"): row.get("secret") for row in rows if isinstance(row.get("name"), str)}
    for name in sorted(SECRET_ENVIRONMENT_NAMES):
        if flags.get(name) is not True:
            _add(
                findings,
                "secret_environment_not_marked",
                f"manifest.required_environment_variables.{name}",
                f"{name} phải được đánh dấu secret=true.",
            )
