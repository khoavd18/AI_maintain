"""Characterize deployment-manifest storage roots, paths, and retention."""

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

from src.reliability.pilot_contract.manifest import (
    _validate_storage as manifest_storage_validator,
)

from src.reliability.pilot_contract.schemas import Finding

from src.reliability.pilot_contract.deployment_manifest.storage import _validate_storage

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_STORAGE_PATHS = (
    "attachments",
    "analytics_source",
    "analytics_output",
    "backups",
)


def _valid_document() -> dict[str, Any]:
    return {
        "storage": {
            "allowed_roots": {
                "data": {
                    "environment_variable": "PILOT_ALLOWED_DATA_ROOT",
                    "scope": "host",
                    "outside_repository": True,
                },
                "backup": {
                    "environment_variable": "PILOT_BACKUP_ROOT",
                    "scope": "host",
                    "outside_repository": True,
                },
            },
            "paths": {
                "attachments": {
                    "root": "data",
                    "relative_path": "attachments",
                    "container_path": "/app/data/attachments",
                    "configuration_environment": "ATTACHMENT_STORAGE_ROOT",
                },
                "analytics_source": {
                    "root": "data",
                    "relative_path": "analytics-input",
                    "container_path": "/app/data/raw",
                    "configuration_environment": "ANALYTICS_SOURCE_DIR",
                },
                "analytics_output": {
                    "root": "data",
                    "relative_path": "analytics-output",
                    "container_path": "/app/data/processed",
                    "configuration_environment": "ANALYTICS_PROCESSED_DIR",
                },
                "backups": {
                    "root": "backup",
                    "relative_path": "postgresql",
                    "retention_keep_count": 7,
                },
            },
        }
    }


def _findings(
    document: dict[str, Any],
    repository_root: Any = REPOSITORY_ROOT,
) -> tuple[None, list[Finding]]:
    findings: list[Finding] = []
    result = _validate_storage(document, repository_root, findings)
    return result, findings


def _finding(code: str, scope: str, message: str) -> Finding:
    return Finding(code=code, scope=scope, message=message)


def _missing_path_finding(name: str) -> Finding:
    return _finding(
        "required_storage_path_missing",
        f"manifest.storage.paths.{name}",
        "Thiếu storage path bắt buộc.",
    )


def _unknown_root_finding(name: str) -> Finding:
    return _finding(
        "storage_root_unknown",
        f"manifest.storage.paths.{name}",
        "Storage path tham chiếu allowed root không tồn tại.",
    )


def _containment_finding(name: str, message: str) -> Finding:
    return _finding(
        "path_containment_violation",
        f"manifest.storage.paths.{name}",
        message,
    )
