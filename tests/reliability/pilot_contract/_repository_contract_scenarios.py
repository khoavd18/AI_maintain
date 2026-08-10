"""Characterize checked-in deployment-manifest repository bindings."""

# ruff: noqa: F401 - split suites import their explicit scenario dependencies

from __future__ import annotations

from copy import deepcopy

from inspect import signature

import json

from pathlib import Path

from typing import Any

import pytest

from src.release import APPLICATION_VERSION, CANONICAL_SCHEMA_REVISION

from src.reliability.pilot_contract import (
    validate_deployment_manifest,
    validate_pilot_contract,
)

from src.reliability.pilot_contract.cli import main as pilot_contract_main

from src.reliability.pilot_contract.manifest import (
    _validate_repository_contract as manifest_repository_contract_validator,
)

from src.reliability.pilot_contract.deployment_manifest.repository import (
    _validate_repository_contract,
)

from src.reliability.pilot_contract.schemas import Finding

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

COMPOSE_NAME = "docker-compose.contract.yml"

PYTHON_IMAGE = "python:3.11-slim"

NODE_IMAGE = "node:20-alpine"

POSTGRES_IMAGE = "postgres:16-alpine"

QDRANT_IMAGE = "qdrant/qdrant:v1.9.7"

FRONTEND_VERSION = "0.1.0"

NEXT_VERSION = "14.2.5"

_DEFAULT_PACKAGE = object()


def _valid_document() -> dict[str, Any]:
    return {
        "compose_file": COMPOSE_NAME,
        "required_environment_variables": [{"name": "DECLARED_ENV", "secret": False}],
        "release": {"alembic_revision": CANONICAL_SCHEMA_REVISION},
        "versions": {
            "application": APPLICATION_VERSION,
            "frontend": FRONTEND_VERSION,
            "nextjs": NEXT_VERSION,
        },
        "images": {
            "python_base": PYTHON_IMAGE,
            "node_base": NODE_IMAGE,
            "postgresql": POSTGRES_IMAGE,
            "qdrant": QDRANT_IMAGE,
        },
    }


def _write_repository(
    root: Path,
    *,
    compose_text: str | None = None,
    python_dockerfile: str | None = None,
    node_dockerfile: str | None = None,
    package: object = _DEFAULT_PACKAGE,
) -> dict[str, bytes]:
    frontend = root / "frontend"
    frontend.mkdir(parents=True)
    (root / COMPOSE_NAME).write_text(
        compose_text
        or (
            "services:\n"
            f"  postgres:\n    image: {POSTGRES_IMAGE}\n"
            f"  qdrant:\n    image: {QDRANT_IMAGE}\n"
            "  api:\n    environment:\n"
            "      DECLARED_ENV: ${DECLARED_ENV:?required}\n"
        ),
        encoding="utf-8",
    )
    (root / "Dockerfile").write_text(
        python_dockerfile or f"FROM {PYTHON_IMAGE}\n",
        encoding="utf-8",
    )
    (frontend / "Dockerfile").write_text(
        node_dockerfile or f"FROM {NODE_IMAGE}\n",
        encoding="utf-8",
    )
    package_value = (
        {"version": FRONTEND_VERSION, "dependencies": {"next": NEXT_VERSION}}
        if package is _DEFAULT_PACKAGE
        else package
    )
    (frontend / "package.json").write_text(
        json.dumps(package_value),
        encoding="utf-8",
    )
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def _findings(
    document: dict[str, Any],
    repository_root: Path,
) -> tuple[None, list[Finding]]:
    findings: list[Finding] = []
    result = _validate_repository_contract(document, repository_root, findings)
    return result, findings


def _finding(code: str, scope: str, message: str) -> Finding:
    return Finding(code=code, scope=scope, message=message)


def _repository_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
