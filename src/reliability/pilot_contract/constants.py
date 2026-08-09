"""Constants and type aliases for the internal-pilot contract."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import re
from pathlib import Path
from typing import Any, Literal

GO = "GO"
CONDITIONAL_GO = "CONDITIONAL GO"
NO_GO = "NO-GO / NOT YET VERIFIED"
EXTERNAL_PILOT_NO_GO = "NO-GO / WAITING FOR PILOT SPONSOR"
ALLOWED_DECISIONS = frozenset({GO, CONDITIONAL_GO, NO_GO, EXTERNAL_PILOT_NO_GO})

SUPPORTED_JOBS = frozenset(
    {
        "preventive_generation",
        "sla_escalation",
        "analytics_refresh",
        "inventory_reorder_detection",
    }
)
REQUIRED_SERVICES = frozenset({"postgres", "qdrant", "api", "worker", "frontend"})
REQUIRED_OWNERS = (
    "operational_owner",
    "backup_owner",
    "release_owner",
    "rollback_owner",
    "incident_coordinator",
    "security_contact",
    "database_recovery_contact",
    "application_support_contact",
    "pilot_business_owner",
)
REQUIRED_LIMITATIONS = frozenset(
    {
        "single_api_instance",
        "single_worker_instance",
        "single_postgresql_instance",
        "no_automatic_failover",
        "no_automated_pitr",
        "local_attachment_storage",
        "no_malware_scanning",
        "in_app_alerts_only",
        "no_centralized_observability_on_call",
        "no_managed_secrets",
        "single_host_capacity_evidence",
        "no_multi_tenancy",
        "no_sso_mfa",
        "no_customer_facing_sla",
    }
)
CRITICAL_GATES = frozenset(
    {
        "intended_host_deployment_rehearsal",
        "sustained_soak",
        "mutation_workload",
        "capacity_degradation_boundary",
        "worker_termination_recovery",
        "backup_restore",
        "backup_failure_detection",
        "disk_warning_recovery",
        "pilot_secret_rotation",
        "representative_attachment_restore",
        "operational_ownership",
        "incident_response_path",
        "release_rollback_rehearsal",
        "authentication_rbac",
    }
)
REQUIRED_PILOT_ENVIRONMENT = frozenset(
    {
        "APP_ENVIRONMENT",
        "STORAGE_BACKEND",
        "DATABASE_URL",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "TOKEN_SIGNING_SECRET",
        "AUTH_COOKIE_SECURE",
        "CORS_ALLOWED_ORIGINS",
        "TRUSTED_HOSTS",
        "FRONTEND_BASE_URL",
        "NEXT_PUBLIC_API_BASE_URL",
        "QDRANT_URL",
        "ATTACHMENT_STORAGE_ROOT",
        "ANALYTICS_SOURCE_DIR",
        "ANALYTICS_PROCESSED_DIR",
        "PILOT_ALLOWED_DATA_ROOT",
        "PILOT_BACKUP_ROOT",
        "PILOT_BACKUP_RETENTION_COUNT",
        "PILOT_HOST_IDENTIFIER",
        "RELEASE_IDENTIFIER",
        "RELEASE_GIT_COMMIT",
        "RELEASE_GIT_TAG",
        "RELEASE_ALEMBIC_REVISION",
    }
)
SECRET_ENVIRONMENT_NAMES = frozenset({"DATABASE_URL", "POSTGRES_PASSWORD", "TOKEN_SIGNING_SECRET"})
PROTECTED_RISK_CATEGORIES = frozenset(
    {"data_integrity", "authorization", "recovery", "safety", "data_loss"}
)
ALLOWED_RISK_CATEGORIES = PROTECTED_RISK_CATEGORIES | frozenset(
    {"availability", "capacity", "operability", "performance", "usability"}
)
ALLOWED_RISK_SEVERITIES = frozenset({"low", "medium", "high", "critical"})
ALLOWED_RISK_STATUSES = frozenset({"open"})

JsonMapping = Mapping[str, Any]
JsonSource = JsonMapping | str | Path
ServiceProbe = Callable[[JsonMapping], bool]
Severity = Literal["blocker", "warning"]

_PLACEHOLDER_MARKERS = (
    "PENDING",
    "PLACEHOLDER",
    "REPLACE_WITH",
    "TBD",
    "TODO",
    "UNASSIGNED",
    "NOT_PROVIDED",
)
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_EXACT_TAG_TARGET_COMMIT_RESOLUTION = "exact_tag_target"
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+\d[\d .()-]{7,}\d)")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_COMPOSE_REQUIRED_ENV_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]*):\?[^}\r\n]+\}")
_SENSITIVE_VALUE_KEYS = frozenset(
    {
        "password",
        "password_value",
        "secret",
        "secret_value",
        "token",
        "token_value",
        "credential",
        "credentials",
        "database_url",
        "authorization",
        "authorization_header",
        "cookie",
        "phone",
        "phone_number",
        "email",
        "personal_contact",
    }
)
