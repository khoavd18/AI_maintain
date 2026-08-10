"""Credential-free URL and contained host/container path contracts."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from .constants import _WINDOWS_ABSOLUTE_RE


def _safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return False
    normalized = value.replace("\\", "/")
    if (
        normalized.startswith("/")
        or normalized.startswith("//")
        or _WINDOWS_ABSOLUTE_RE.match(value)
        or "://" in normalized
    ):
        return False
    parts = PurePosixPath(normalized).parts
    return ".." not in parts and all(part not in {"", "."} for part in parts)


def _safe_container_path(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or "\x00" in value
    ):
        return False
    parts = PurePosixPath(value).parts
    return ".." not in parts and all(part != "." for part in parts)


def _safe_service_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


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
