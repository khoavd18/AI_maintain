"""Secret-safe release-record redaction."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any
from urllib.parse import urlsplit

_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+\d[\d .()-]{7,}\d)")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_SENSITIVE_VALUE_KEYS = frozenset(
    {
        "password",
        "password_value",
        "secret",
        "secret_value",
        "token",
        "token_value",
        "credential",
        "credentials",
        "database_url",
        "authorization",
        "authorization_header",
        "cookie",
        "phone",
        "phone_number",
        "email",
        "personal_contact",
    }
)


def redact_release_record(value: Any) -> Any:
    """Recursively remove credential values, personal contacts, and local paths."""

    def visit(item: Any, key: str | None = None) -> Any:
        normalized_key = (key or "").casefold()
        if normalized_key in _SENSITIVE_VALUE_KEYS or normalized_key.endswith(
            ("_password", "_secret", "_token", "_credential")
        ):
            return "[REDACTED]"
        if isinstance(item, Mapping):
            return {
                str(child_key): visit(child, str(child_key))
                for child_key, child in item.items()
            }
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, tuple):
            return [visit(child) for child in item]
        if isinstance(item, str):
            if _looks_like_local_absolute_path(item):
                return "[REDACTED_LOCAL_PATH]"
            if _url_contains_credentials(item):
                return "[REDACTED_CREDENTIAL_URL]"
            if _EMAIL_RE.search(item) or _PHONE_RE.search(item):
                return "[REDACTED_PERSONAL_CONTACT]"
        return item

    return visit(value)


def _url_contains_credentials(value: str) -> bool:
    if "://" not in value:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return True
    return parsed.username is not None or parsed.password is not None


def _looks_like_local_absolute_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return bool(
        _WINDOWS_ABSOLUTE_RE.match(value)
        or value.startswith("\\\\")
        or normalized.startswith(
            (
                "/Users/",
                "/home/",
                "/tmp/",
                "/var/",
                "/etc/",
                "/opt/",
                "/srv/",
                "/mnt/",
                "/app/",
                "/root/",
            )
        )
    )
