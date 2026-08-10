"""Validate service port ownership, environment bindings, and collisions."""

from __future__ import annotations

from typing import Any

from ..constants import _ENV_NAME_RE
from ..document_shapes import _check_unique_names, _list_of_mappings
from ..findings import _add
from ..schemas import Finding


def _validate_ports(
    document: dict[str, Any],
    service_names: set[str],
    findings: list[Finding],
) -> None:
    ports = _list_of_mappings(
        document.get("ports"),
        findings=findings,
        scope="manifest.ports",
    )
    if not isinstance(document.get("ports"), list):
        _add(findings, "invalid_ports", "manifest.ports", "ports phải là list.")
    _check_unique_names(ports, "name", "port", findings)
    occupied: dict[tuple[str, int], str] = {}
    for port in ports:
        name = str(port.get("name", "unknown"))
        service = port.get("service")
        protocol = port.get("protocol")
        host_port = port.get("host_port")
        container_port = port.get("container_port")
        if service not in service_names:
            _add(
                findings,
                "port_service_unknown",
                f"manifest.ports.{name}",
                "Port tham chiếu service không tồn tại.",
            )
        if protocol not in {"tcp", "udp"}:
            _add(
                findings,
                "invalid_port_protocol",
                f"manifest.ports.{name}",
                "Port protocol phải là tcp hoặc udp.",
            )
        for field in ("bind_address_environment", "host_port_environment"):
            environment_name = port.get(field)
            if not isinstance(environment_name, str) or not _ENV_NAME_RE.fullmatch(
                environment_name
            ):
                _add(
                    findings,
                    "port_environment_missing",
                    f"manifest.ports.{name}.{field}",
                    "Mỗi host port phải tham chiếu biến môi trường bind và port.",
                )
        for field, value in (("host_port", host_port), ("container_port", container_port)):
            if type(value) is not int or not 1 <= value <= 65535:
                _add(
                    findings,
                    "invalid_port",
                    f"manifest.ports.{name}.{field}",
                    "Port phải là số nguyên trong khoảng 1..65535.",
                )
        if isinstance(host_port, int) and isinstance(protocol, str):
            key = (protocol, host_port)
            if key in occupied:
                _add(
                    findings,
                    "duplicate_port",
                    f"manifest.ports.{name}",
                    "Hai service không được dùng trùng host port và protocol.",
                )
            else:
                occupied[key] = name
