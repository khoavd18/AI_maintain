"""Ordered facade for closed service, port, and persistent-volume topology."""

from __future__ import annotations

from typing import Any

from ..schemas import Finding
from .ports import _validate_ports
from .services import _validate_services
from .volumes import _validate_volumes


def _validate_service_topology(
    document: dict[str, Any],
    versions: dict[str, Any],
    findings: list[Finding],
) -> set[str]:
    service_names = _validate_services(document, versions, findings)
    _validate_ports(document, service_names, findings)
    _validate_volumes(document, service_names, findings)
    return service_names
