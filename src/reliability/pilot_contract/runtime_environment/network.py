"""Validate injected pilot network and internal-service URLs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from ..document_shapes import _list_of_mappings
from ..findings import _add
from ..path_contracts import _safe_service_url
from ..schemas import Finding


def _validate_network_environment(
    manifest: dict[str, Any],
    environment: Mapping[str, str],
    findings: list[Finding],
) -> None:
    for name in ("CORS_ALLOWED_ORIGINS", "TRUSTED_HOSTS"):
        value = environment.get(name, "")
        if value and (
            "*" in {part.strip() for part in value.split(",")}
            or "localhost" in value.casefold()
            or "127.0.0.1" in value
            or "testserver" in value.casefold()
        ):
            _add(
                findings,
                "development_network_default",
                f"environment.{name}",
                f"{name} vẫn dùng wildcard hoặc development host.",
            )
    cors_origins = [
        item.strip()
        for item in environment.get("CORS_ALLOWED_ORIGINS", "").split(",")
        if item.strip()
    ]
    if any(
        not _safe_service_url(origin) or urlsplit(origin).scheme != "https"
        for origin in cors_origins
    ):
        _add(
            findings,
            "pilot_cors_origin_invalid",
            "environment.CORS_ALLOWED_ORIGINS",
            "Mỗi pilot CORS origin phải là HTTPS origin không chứa credential.",
        )
    for name in ("FRONTEND_BASE_URL", "NEXT_PUBLIC_API_BASE_URL", "QDRANT_URL"):
        value = environment.get(name, "")
        if value and not _safe_service_url(value):
            _add(
                findings,
                "service_url_invalid",
                f"environment.{name}",
                f"{name} phải là http(s) URL không chứa credential.",
            )
        elif value:
            parsed_service = urlsplit(value)
            hostname = parsed_service.hostname
            if name != "QDRANT_URL" and hostname in {"localhost", "127.0.0.1", "::1"}:
                _add(
                    findings,
                    "development_network_default",
                    f"environment.{name}",
                    f"{name} vẫn dùng development host.",
                )
            if name != "QDRANT_URL" and parsed_service.scheme != "https":
                _add(
                    findings,
                    "pilot_tls_origin_required",
                    f"environment.{name}",
                    f"{name} phải dùng HTTPS cho pilot.",
                )
    qdrant_service = next(
        (
            service
            for service in _list_of_mappings(manifest.get("services"))
            if service.get("name") == "qdrant"
        ),
        {},
    )
    if environment.get("QDRANT_URL") and environment.get("QDRANT_URL") != qdrant_service.get(
        "internal_url"
    ):
        _add(
            findings,
            "qdrant_internal_url_mismatch",
            "environment.QDRANT_URL",
            "QDRANT_URL phải dùng địa chỉ service nội bộ đã khai báo.",
        )
