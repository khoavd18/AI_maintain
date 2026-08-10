"""Manifest structure and deployment-contract validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .deployment_manifest.artifacts import _validate_artifact_declarations
from .deployment_manifest.environment import _validate_environment_declarations
from .deployment_manifest.health import _validate_health_endpoints
from .deployment_manifest.jobs import _validate_job_catalog
from .deployment_manifest.repository import _validate_repository_contract
from .deployment_manifest.storage import _validate_storage
from .deployment_manifest.topology import _validate_service_topology
from .runtime import _validate_runtime_settings
from .schemas import Finding


def _validate_manifest_structure(
    document: dict[str, Any],
    repository_root: Path,
    findings: list[Finding],
) -> None:
    versions = _validate_artifact_declarations(document, findings)
    service_names = _validate_service_topology(document, versions, findings)
    _validate_storage(document, repository_root, findings)
    _validate_environment_declarations(document, findings)
    _validate_repository_contract(document, repository_root, findings)
    _validate_health_endpoints(document, service_names, findings)
    _validate_job_catalog(document, findings)
    _validate_runtime_settings(document, findings)
