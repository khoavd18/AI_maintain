"""Validate the closed deployment service catalog and version references."""

from __future__ import annotations

from typing import Any

from ..constants import REQUIRED_SERVICES
from ..document_shapes import _check_unique_names, _list_of_mappings
from ..findings import _add
from ..schemas import Finding


def _validate_services(
    document: dict[str, Any],
    versions: dict[str, Any],
    findings: list[Finding],
) -> set[str]:
    services = _list_of_mappings(
        document.get("services"),
        findings=findings,
        scope="manifest.services",
    )
    if not isinstance(document.get("services"), list):
        _add(findings, "invalid_services", "manifest.services", "services phải là list.")
    service_names = _check_unique_names(services, "name", "service", findings)
    missing_services = REQUIRED_SERVICES - service_names
    unsupported_services = service_names - REQUIRED_SERVICES
    for name in sorted(missing_services):
        _add(
            findings,
            "required_service_missing",
            f"manifest.services.{name}",
            f"Thiếu service bắt buộc: {name}.",
        )
    for name in sorted(unsupported_services):
        _add(
            findings,
            "unsupported_service",
            f"manifest.services.{name}",
            f"Service ngoài contract PM9: {name}.",
        )
    for service in services:
        name = service.get("name")
        if service.get("required") is not True:
            _add(
                findings,
                "service_not_required",
                f"manifest.services.{name}",
                "Mỗi service trong closed pilot topology phải được đánh dấu required=true.",
            )
        version_ref = service.get("version_ref")
        if version_ref not in versions:
            _add(
                findings,
                "service_version_reference_invalid",
                f"manifest.services.{name}",
                "Service phải tham chiếu component version đã khai báo.",
            )
    return service_names
