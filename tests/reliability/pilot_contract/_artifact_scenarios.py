"""Characterize deployment-manifest artifact declarations."""

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
    validate_deployment_manifest,
    validate_pilot_contract,
)

from src.reliability.pilot_contract.cli import main as pilot_contract_main

from src.reliability.pilot_contract.deployment_manifest.artifacts import (
    _validate_artifact_declarations,
)

from src.reliability.pilot_contract.manifest import (
    _validate_artifact_declarations as manifest_artifact_validator,
)

from src.reliability.pilot_contract.schemas import Finding

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_TOP_LEVEL = {
    "schema_version",
    "manifest_kind",
    "compose_file",
    "release",
    "versions",
    "images",
    "services",
    "ports",
    "volumes",
    "storage",
    "required_environment_variables",
    "health_endpoints",
    "scheduled_jobs",
    "worker",
    "retry_and_dead_letter",
    "operational_alerts",
    "database",
    "restore_prerequisites",
    "rollback",
    "production_readiness_claim",
}

REQUIRED_RELEASE = {
    "release_id",
    "commit_resolution",
    "tag_recommendation",
    "tag_status",
    "alembic_revision",
}

REQUIRED_VERSIONS = {
    "application",
    "frontend",
    "python",
    "node",
    "postgresql",
    "qdrant",
}

REQUIRED_IMAGES = {
    "application",
    "frontend",
    "python_base",
    "node_base",
    "postgresql",
    "qdrant",
}

ARTIFACT_CODES = {
    "required_key_missing",
    "invalid_schema_version",
    "invalid_manifest_kind",
    "production_readiness_claim_forbidden",
    "invalid_commit_resolution",
    "release_tag_pending",
    "missing_release_identity",
    "missing_component_version",
    "invalid_image_reference",
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


def _artifact_findings(document: dict[str, Any]) -> list[Finding]:
    return [finding for finding in _findings(document)[1] if finding.code in ARTIFACT_CODES]


def _finding(code: str, scope: str, message: str) -> Finding:
    return Finding(code=code, scope=scope, message=message)
