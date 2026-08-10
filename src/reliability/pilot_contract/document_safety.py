"""Recursive secret, credential, contact, and local-path document safety."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .constants import _EMAIL_RE, _PHONE_RE, _SENSITIVE_VALUE_KEYS
from .findings import _add
from .path_contracts import _looks_like_local_absolute_path, _url_contains_credentials
from .schemas import Finding


def _validate_safe_document(
    document: dict[str, Any],
    scope: str,
    findings: list[Finding],
) -> None:
    def visit(value: Any, location: str, key: str | None = None) -> None:
        normalized_key = (key or "").casefold()
        if normalized_key in _SENSITIVE_VALUE_KEYS and value not in (None, False, True, ""):
            _add(
                findings,
                "secret_or_personal_value_committed",
                location,
                "Contract không được chứa secret, credential hoặc personal contact value.",
            )
            return
        if isinstance(value, Mapping):
            for child_key, child_value in value.items():
                visit(child_value, f"{location}.{child_key}", str(child_key))
        elif isinstance(value, list):
            for index, child_value in enumerate(value):
                visit(child_value, f"{location}[{index}]")
        elif isinstance(value, str):
            if _url_contains_credentials(value):
                _add(
                    findings,
                    "credential_url_committed",
                    location,
                    "Contract không được chứa URL có credential.",
                )
            if _looks_like_local_absolute_path(value) and normalized_key != "container_path":
                _add(
                    findings,
                    "absolute_local_path_committed",
                    location,
                    "Contract không được chứa absolute local path.",
                )
            if _EMAIL_RE.search(value) or _PHONE_RE.search(value):
                _add(
                    findings,
                    "personal_contact_committed",
                    location,
                    "Contract không được chứa email hoặc số điện thoại cá nhân.",
                )

    visit(document, scope)
