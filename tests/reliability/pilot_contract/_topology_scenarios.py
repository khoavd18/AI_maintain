"""Characterize the closed deployment service, port, and volume topology."""

# ruff: noqa: F401 - split suites import their explicit scenario dependencies

from __future__ import annotations

from copy import deepcopy

from inspect import signature

import json

from pathlib import Path

from typing import Any

import pytest

import src.reliability.pilot_contract.manifest as manifest_module

from src.reliability.pilot_contract import (
    REQUIRED_SERVICES,
    validate_deployment_manifest,
    validate_pilot_contract,
)

from src.reliability.pilot_contract.schemas import Finding

from src.reliability.pilot_contract.manifest import (
    _validate_service_topology as manifest_topology_validator,
)

from src.reliability.pilot_contract.deployment_manifest.topology import (
    _validate_service_topology,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_VOLUME_PURPOSES = {
    "transactional_database",
    "rag_document_index",
    "local_attachment_bytes",
    "batch_analytics_contracts",
    "validated_backup_archives",
}

TOPOLOGY_CODES = {
    "list_entry_not_object",
    "invalid_services",
    "service_name_missing",
    "duplicate_service",
    "required_service_missing",
    "unsupported_service",
    "service_not_required",
    "service_version_reference_invalid",
    "invalid_ports",
    "port_name_missing",
    "duplicate_port",
    "port_service_unknown",
    "invalid_port_protocol",
    "port_environment_missing",
    "invalid_port",
    "invalid_volumes",
    "volume_name_missing",
    "duplicate_volume",
    "required_volume_missing",
    "volume_service_unknown",
    "invalid_volume_kind",
    "volume_storage_path_unknown",
    "volume_mount_service_unknown",
    "volume_not_persistent",
}


def _ready_manifest() -> dict[str, Any]:
    document = json.loads(
        (REPOSITORY_ROOT / "deployment" / "pilot_manifest.json").read_text(encoding="utf-8")
    )
    document["release"]["tag_status"] = "checkpointed"
    return document


@pytest.fixture
def isolate_downstream(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "_validate_storage",
        "_validate_environment_declarations",
        "_validate_repository_contract",
        "_validate_health_endpoints",
        "_validate_job_catalog",
        "_validate_runtime_settings",
    ):
        monkeypatch.setattr(manifest_module, name, lambda *args, **kwargs: None)


def _findings(document: dict[str, Any]) -> tuple[None, list[Finding]]:
    findings: list[Finding] = []
    result = manifest_module._validate_manifest_structure(document, REPOSITORY_ROOT, findings)
    return result, findings


def _topology_findings(document: dict[str, Any]) -> list[Finding]:
    return [finding for finding in _findings(document)[1] if finding.code in TOPOLOGY_CODES]


def _finding(code: str, scope: str, message: str) -> Finding:
    return Finding(code=code, scope=scope, message=message)


def _valid_port(
    name: str, *, host_port: object = 65000, protocol: object = "tcp"
) -> dict[str, Any]:
    return {
        "name": name,
        "service": "api",
        "protocol": protocol,
        "bind_address_environment": "PILOT_API_BIND_ADDRESS",
        "host_port_environment": "PILOT_API_PORT",
        "host_port": host_port,
        "container_port": 8000,
    }
