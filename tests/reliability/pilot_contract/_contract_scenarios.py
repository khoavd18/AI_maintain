"""Cross-capability tests for the PM9 deployment, ownership, and release contract."""

# ruff: noqa: F401 - split suites import their explicit scenario dependencies

from __future__ import annotations

import json

from pathlib import Path

from typing import Any

from src.reliability.pilot_contract import (
    CONDITIONAL_GO,
    CRITICAL_GATES,
    EXTERNAL_PILOT_NO_GO,
    GO,
    NO_GO,
    evaluate_pilot_decision,
    generate_release_record,
    manifest_sha256,
    redact_release_record,
    validate_deployment_manifest,
    validate_pilot_contract,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

DEPLOYMENT_ROOT = REPOSITORY_ROOT / "deployment"

DESIGN_READINESS_TAG = "product-milestone-9-pilot-ready-by-design"


def _load(name: str) -> dict[str, Any]:
    return json.loads((DEPLOYMENT_ROOT / name).read_text(encoding="utf-8"))


def _ready_manifest() -> dict[str, Any]:
    manifest = _load("pilot_manifest.json")
    manifest["release"]["tag_status"] = "verified"
    manifest["rollback"]["rehearsal_status"] = "passed"
    return manifest


def _ready_ownership() -> dict[str, Any]:
    ownership = _load("operational_ownership.json")
    ownership["record_status"] = "approved"
    for key, assignment in ownership["assignments"].items():
        assignment.update(
            {
                "assigned_role": f"internal_pilot_{key}_role",
                "approved_internal_channel": "approved-internal-operations-channel",
                "status": "assigned",
                "approval_evidence_links": [f"evidence/ownership/{key}.json"],
            }
        )
    ownership["incident_communication"].update(
        {
            "status": "configured",
            "primary_internal_channel": "approved-internal-incident-channel",
            "fallback_internal_channel": "approved-internal-escalation-channel",
            "approval_evidence_links": ["evidence/ownership/incident-path.json"],
        }
    )
    ownership["support_coverage"].update(
        {
            "status": "confirmed",
            "support_hours": "business-hours-in-declared-timezone",
            "after_hours_assumption": "pilot-paused-until-support-window",
            "approval_evidence_links": ["evidence/ownership/coverage.json"],
        }
    )
    ownership["escalation_path"].update(
        {
            "status": "configured",
            "approval_evidence_links": ["evidence/ownership/escalation.json"],
        }
    )
    return ownership


def _ready_limitations() -> dict[str, Any]:
    limitations = _load("known_limitations.json")
    limitations["record_status"] = "accepted"
    for limitation in limitations["limitations"]:
        limitation.update(
            {
                "owner_role": "internal_pilot_governance_role",
                "acceptance_status": "accepted",
                "accepted_by_role": "internal_pilot_business_owner_role",
                "accepted_at_utc": "2026-07-26T12:00:00Z",
                "acceptance_evidence_links": [f"evidence/limitations/{limitation['id']}.json"],
            }
        )
    return limitations


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


def _ready_documents() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    manifest = _ready_manifest()
    ownership = _ready_ownership()
    limitations = _ready_limitations()
    gates = {
        gate_id: {
            "status": "passed",
            "evidence_links": [f"evidence/gates/{gate_id}.json"],
        }
        for gate_id in CRITICAL_GATES
    }
    record = generate_release_record(
        manifest,
        ownership,
        limitations,
        gate_results=gates,
        evidence_links=["evidence/releases/pm9.json"],
        generated_at_utc="2026-07-26T12:00:00Z",
        release_commit="a" * 40,
    )
    record["record_status"] = "final"
    for section_name in (
        "backup_validation",
        "restore_validation",
        "attachment_restore",
        "secret_rotation",
    ):
        record[section_name] = {
            "status": "passed",
            "validated_at_utc": "2026-07-26T12:00:00Z",
            "evidence_links": [f"evidence/gates/{section_name}.json"],
        }
    record["load_and_soak_profiles"] = {
        "status": "passed",
        "summaries": [{"scope": "approved-pilot-equivalent-host"}],
        "evidence_links": ["evidence/gates/load-and-soak.json"],
    }
    return manifest, ownership, limitations, record
