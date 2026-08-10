"""Integer and truthy runtime-environment value contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..findings import _add
from ..schemas import Finding


def _validate_integer_environment_match(
    environment: Mapping[str, str],
    name: str,
    expected: Any,
    findings: list[Finding],
) -> None:
    value = environment.get(name)
    if not value:
        return
    try:
        actual = int(value)
    except ValueError:
        actual = None
    if actual != expected:
        _add(
            findings,
            "runtime_environment_mismatch",
            f"environment.{name}",
            f"{name} phải là số nguyên khớp deployment manifest.",
        )


def _validate_integer_environment_range(
    environment: Mapping[str, str],
    name: str,
    minimum: int,
    maximum: int,
    findings: list[Finding],
) -> None:
    value = environment.get(name)
    if not value:
        return
    try:
        actual = int(value)
    except ValueError:
        actual = None
    if actual is None or not minimum <= actual <= maximum:
        _add(
            findings,
            "runtime_environment_out_of_range",
            f"environment.{name}",
            f"{name} phải là số nguyên nằm trong giới hạn pilot.",
        )


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().casefold() in {"1", "true", "yes", "on"})
