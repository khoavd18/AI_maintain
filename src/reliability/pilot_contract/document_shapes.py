"""Strict JSON-object, list, key, identity, and version shape contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .findings import _add
from .schemas import Finding


def _versioned(document: Mapping[str, Any]) -> bool:
    value = document.get("schema_version")
    return (
        isinstance(value, (str, int)) and not isinstance(value, bool) and bool(str(value).strip())
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_of_mappings(
    value: Any,
    *,
    findings: list[Finding] | None = None,
    scope: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            rows.append(dict(item))
        elif findings is not None and scope is not None:
            _add(
                findings,
                "list_entry_not_object",
                f"{scope}.{index}",
                "Mỗi phần tử trong danh sách contract phải là JSON object.",
            )
    return rows


def _require_keys(
    value: Mapping[str, Any],
    required: set[str],
    scope: str,
    findings: list[Finding],
) -> None:
    for key in sorted(required - set(value)):
        _add(
            findings,
            "required_key_missing",
            f"{scope}.{key}",
            f"Thiếu required key: {key}.",
        )


def _check_unique_names(
    rows: list[dict[str, Any]],
    key: str,
    entity: str,
    findings: list[Finding],
) -> set[str]:
    names: set[str] = set()
    for row in rows:
        name = row.get(key)
        if not isinstance(name, str) or not name:
            _add(
                findings,
                f"{entity}_name_missing",
                f"manifest.{entity}s",
                f"Mỗi {entity} phải có {key}.",
            )
            continue
        if name in names:
            _add(
                findings,
                f"duplicate_{entity}",
                f"manifest.{entity}s.{name}",
                f"{entity} bị khai báo trùng.",
            )
        names.add(name)
    return names
