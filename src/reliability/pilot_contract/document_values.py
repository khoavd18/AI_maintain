"""Placeholder, text, Git identity, and timezone value contracts."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .constants import _COMMIT_RE, _PLACEHOLDER_MARKERS


def _is_placeholder(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return True
    normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
    return any(marker in normalized for marker in _PLACEHOLDER_MARKERS)


def _non_placeholder_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _is_placeholder(value)


def _git_identity_matches(expected: str, actual: str) -> bool:
    expected_normalized = expected.strip().casefold()
    actual_normalized = actual.strip().casefold()
    return bool(
        _COMMIT_RE.fullmatch(expected_normalized)
        and _COMMIT_RE.fullmatch(actual_normalized)
        and expected_normalized == actual_normalized
    )


def _valid_iana_timezone(value: Any) -> bool:
    if not _non_placeholder_text(value):
        return False
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True
