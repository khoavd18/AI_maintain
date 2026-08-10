"""Characterize injected pilot runtime-environment capabilities."""

# ruff: noqa: F401 - split suites import their explicit scenario dependencies

from __future__ import annotations

from copy import deepcopy

from inspect import signature

import json

from pathlib import Path

from typing import Any

import pytest

import src.reliability.pilot_contract.environment as environment_module

from src.reliability.pilot_contract.contract import (
    _validate_environment as contract_environment_validator,
)

from src.reliability.pilot_contract import validate_deployment_manifest

from src.reliability.pilot_contract.cli import main as pilot_contract_main

from src.reliability.pilot_contract.environment import _validate_environment

from src.reliability.pilot_contract.runtime_environment.identity import (
    _validate_identity_environment,
)

from src.reliability.pilot_contract.runtime_environment.network import (
    _validate_network_environment,
)

from src.reliability.pilot_contract.runtime_environment.settings import (
    _validate_runtime_environment_settings,
)

from src.reliability.pilot_contract.runtime_environment.security import (
    _validate_security_environment,
)

from src.reliability.pilot_contract.runtime_environment.storage import (
    _validate_storage_environment,
)

from src.reliability.pilot_contract.schemas import Finding

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

DEPLOYMENT_ROOT = REPOSITORY_ROOT / "deployment"


def _ready_manifest() -> dict[str, Any]:
    manifest = json.loads((DEPLOYMENT_ROOT / "pilot_manifest.json").read_text(encoding="utf-8"))
    manifest["release"]["tag_status"] = "verified"
    return manifest


def _ready_environment() -> dict[str, str]:
    manifest = _ready_manifest()
    worker = manifest["worker"]
    database = manifest["database"]
    alerts = manifest["operational_alerts"]
    release = manifest["release"]
    return {
        "ACCESS_TOKEN_LIFETIME_MINUTES": "15",
        "ANALYTICS_PROCESSED_DIR": "/app/data/processed",
        "ANALYTICS_SOURCE_DIR": "/app/data/raw",
        "APP_ENVIRONMENT": "pilot",
        "ATTACHMENT_MAX_SIZE_BYTES": "10485760",
        "ATTACHMENT_STORAGE_BACKEND": "local",
        "ATTACHMENT_STORAGE_ROOT": "/app/data/attachments",
        "AUTH_COOKIE_SAMESITE": "lax",
        "STORAGE_BACKEND": "postgresql",
        "DATABASE_URL": (
            "postgresql+psycopg://pilot_user:"
            "not-a-real-value-for-contract-tests@postgres:5432/pilot_copilot"
        ),
        "POSTGRES_USER": "pilot_user",
        "POSTGRES_PASSWORD": "not-a-real-value-for-contract-tests",
        "POSTGRES_DB": "pilot_copilot",
        "TOKEN_SIGNING_SECRET": "synthetic-contract-test-signing-key-000000000000",
        "AUTH_COOKIE_SECURE": "true",
        "CORS_ALLOWED_ORIGINS": "https://pilot.internal.example",
        "TRUSTED_HOSTS": "pilot.internal.example",
        "FRONTEND_BASE_URL": "https://pilot.internal.example",
        "NEXT_PUBLIC_API_BASE_URL": "https://pilot-api.internal.example",
        "QDRANT_URL": "http://qdrant:6333",
        "QDRANT_COLLECTION": "maintenance_knowledge",
        "EMBEDDING_MODEL_NAME": "intfloat/multilingual-e5-small",
        "REFRESH_SESSION_LIFETIME_DAYS": "7",
        "REFRESH_COOKIE_NAME": "maintenance_refresh",
        "CSRF_COOKIE_NAME": "maintenance_csrf",
        "LOGIN_RATE_LIMIT_ATTEMPTS": "5",
        "LOGIN_RATE_LIMIT_WINDOW_SECONDS": "60",
        "COPILOT_RATE_LIMIT_REQUESTS": "20",
        "COPILOT_RATE_LIMIT_WINDOW_SECONDS": "60",
        "LLM_ENABLED": "false",
        "LLM_PROVIDER": "ollama",
        "LLM_MODEL": "synthetic-contract-model",
        "LLM_BASE_URL": "http://llm.internal:11434",
        "LLM_TIMEOUT_SECONDS": "30",
        "LLM_TEMPERATURE": "0.0",
        "LLM_MAX_TOKENS": "1200",
        "LLM_MAX_RETRIES": "1",
        "LLM_MAX_CONTEXT_CHARS": "12000",
        "LLM_MIN_RELEVANT_DOCUMENTS": "1",
        "LOG_LEVEL": "INFO",
        "PILOT_ALLOWED_DATA_ROOT": str((REPOSITORY_ROOT.parent / "pm9-contract-data").resolve()),
        "PILOT_BACKUP_ROOT": str((REPOSITORY_ROOT.parent / "pm9-contract-backups").resolve()),
        "PILOT_BACKUP_RETENTION_COUNT": "7",
        "PILOT_HOST_IDENTIFIER": "synthetic-pilot-host",
        "PILOT_API_BIND_ADDRESS": "127.0.0.1",
        "PILOT_API_PORT": "8000",
        "PILOT_FRONTEND_BIND_ADDRESS": "127.0.0.1",
        "PILOT_FRONTEND_PORT": "3000",
        "PILOT_POSTGRES_BIND_ADDRESS": "127.0.0.1",
        "PILOT_POSTGRES_PORT": "5432",
        "PILOT_QDRANT_BIND_ADDRESS": "127.0.0.1",
        "PILOT_QDRANT_PORT": "6333",
        "PILOT_APP_IMAGE": manifest["images"]["application"],
        "PILOT_FRONTEND_IMAGE": manifest["images"]["frontend"],
        "RELEASE_IDENTIFIER": release["release_id"],
        "RELEASE_GIT_COMMIT": "a" * 40,
        "RELEASE_GIT_TAG": release["tag_recommendation"],
        "RELEASE_ALEMBIC_REVISION": release["alembic_revision"],
        "DATABASE_CONNECT_TIMEOUT_SECONDS": str(database["connect_timeout_seconds"]),
        "DATABASE_POOL_SIZE": str(database["pool_size"]),
        "DATABASE_MAX_OVERFLOW": str(database["max_overflow"]),
        "DATABASE_POOL_TIMEOUT_SECONDS": str(database["pool_timeout_seconds"]),
        "DATABASE_STATEMENT_TIMEOUT_SECONDS": str(database["statement_timeout_seconds"]),
        "DATABASE_LOCK_TIMEOUT_SECONDS": str(database["lock_timeout_seconds"]),
        "DATABASE_IDLE_TRANSACTION_TIMEOUT_SECONDS": str(
            database["idle_transaction_timeout_seconds"]
        ),
        "WORKER_POLL_INTERVAL_SECONDS": str(worker["poll_interval_seconds"]),
        "WORKER_HEARTBEAT_INTERVAL_SECONDS": str(worker["heartbeat_interval_seconds"]),
        "WORKER_HEARTBEAT_STALE_SECONDS": str(worker["heartbeat_stale_seconds"]),
        "WORKER_OUTBOX_LEASE_SECONDS": str(worker["outbox_lease_seconds"]),
        "WORKER_BATCH_SIZE": str(worker["batch_size"]),
        "OPERATIONAL_OUTBOX_AGE_ALERT_SECONDS": str(alerts["outbox_oldest_age_seconds"]),
        "OPERATIONAL_REPEATED_JOB_FAILURE_THRESHOLD": str(alerts["repeated_job_failure_count"]),
        "OPERATIONAL_ANALYTICS_STALE_SECONDS": str(alerts["analytics_stale_seconds"]),
        "OPERATIONAL_BACKUP_OVERDUE_SECONDS": str(alerts["backup_overdue_seconds"]),
        "OPERATIONAL_DISK_WARNING_FREE_PERCENT": str(alerts["disk_warning_free_percent"]),
        "OPERATIONAL_DISK_CRITICAL_FREE_PERCENT": str(alerts["disk_critical_free_percent"]),
    }


def _findings(
    manifest: dict[str, Any] | None = None,
    environment: dict[str, str] | None = None,
    repository_root: Path = REPOSITORY_ROOT,
) -> tuple[None, list[Finding]]:
    findings: list[Finding] = []
    result = _validate_environment(
        manifest or _ready_manifest(),
        environment or _ready_environment(),
        repository_root,
        findings,
    )
    return result, findings


def _finding(code: str, scope: str, message: str) -> Finding:
    return Finding(code=code, scope=scope, message=message)


def _only(findings: list[Finding], codes: set[str]) -> list[Finding]:
    return [finding for finding in findings if finding.code in codes]
