"""Health endpoint declarations for the deployment manifest contract."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from ..document_shapes import _list_of_mappings
from ..findings import _add
from ..schemas import Finding


def _validate_health_endpoints(
    document: dict[str, Any],
    service_names: set[str],
    findings: list[Finding],
) -> None:
    endpoints = _list_of_mappings(
        document.get("health_endpoints"),
        findings=findings,
        scope="manifest.health_endpoints",
    )
    kinds = {endpoint.get("kind") for endpoint in endpoints}
    for kind in {"liveness", "readiness", "worker_readiness"} - kinds:
        _add(
            findings,
            "health_endpoint_missing",
            f"manifest.health_endpoints.{kind}",
            f"Thiếu endpoint {kind}.",
        )
    seen: set[tuple[Any, Any]] = set()
    for endpoint in endpoints:
        key = (endpoint.get("service"), endpoint.get("path"))
        if key in seen:
            _add(
                findings,
                "duplicate_health_endpoint",
                "manifest.health_endpoints",
                "Health endpoint bị khai báo trùng.",
            )
        seen.add(key)
        if endpoint.get("service") not in service_names:
            _add(
                findings,
                "health_service_unknown",
                "manifest.health_endpoints",
                "Health endpoint tham chiếu service không tồn tại.",
            )
        path = endpoint.get("path")
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or "://" in path
            or ".." in PurePosixPath(path).parts
        ):
            _add(
                findings,
                "invalid_health_path",
                "manifest.health_endpoints",
                "Health endpoint phải là URL path tương đối theo host.",
            )
        statuses = endpoint.get("expected_status")
        if (
            not isinstance(statuses, list)
            or not statuses
            or any(type(status) is not int or not 100 <= status <= 599 for status in statuses)
        ):
            _add(
                findings,
                "invalid_health_status",
                "manifest.health_endpoints",
                "Health endpoint phải khai báo expected HTTP status.",
            )
