"""Secret-free deployment and release-decision contract for the internal pilot.

The validator is deliberately infrastructure-neutral.  It validates the small JSON
contract in ``deployment/`` and accepts environment, release identity, migration
identity, and reachability observations as injected values.  Findings contain only
field or service names; supplied environment values are never returned.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Literal
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.release import APPLICATION_VERSION, CANONICAL_SCHEMA_REVISION


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


@dataclass(frozen=True, slots=True)
class Finding:
    """One deterministic, value-free contract finding."""

    code: str
    scope: str
    message: str
    severity: Severity = "blocker"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "scope": self.scope,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Reviewable result of one contract validation."""

    decision: str
    manifest_sha256: str
    findings: tuple[Finding, ...]

    @property
    def is_valid(self) -> bool:
        return not any(finding.severity == "blocker" for finding in self.findings)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "is_valid": self.is_valid,
            "manifest_sha256": self.manifest_sha256,
            "findings": [finding.as_dict() for finding in self.findings],
        }

    def __getitem__(self, key: str) -> Any:
        """Allow concise dictionary-style use in small operator scripts."""

        return self.as_dict()[key]


def load_json_document(source: JsonSource) -> dict[str, Any]:
    """Load a JSON object from a mapping or path."""

    if isinstance(source, Mapping):
        return json.loads(json.dumps(source))
    path = Path(source)
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return value


def manifest_sha256(manifest: JsonSource) -> str:
    """Return a stable SHA-256 over the semantic JSON manifest."""

    payload = load_json_document(manifest)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_deployment_manifest(
    manifest: JsonSource,
    *,
    environment: Mapping[str, str] | None = None,
    actual_commit: str | None = None,
    actual_tag: str | None = None,
    actual_tag_target_commit: str | None = None,
    actual_migration_revision: str | None = None,
    service_probe: ServiceProbe | None = None,
    repository_root: str | Path | None = None,
) -> ValidationReport:
    """Validate deployment structure and any supplied runtime observations."""

    document = load_json_document(manifest)
    findings: list[Finding] = []
    root = Path(repository_root or Path.cwd()).resolve()
    _validate_safe_document(document, "manifest", findings)
    _validate_manifest_structure(document, root, findings)
    if environment is not None:
        _validate_environment(document, environment, root, findings)
    _validate_release_observations(
        document,
        environment=environment,
        actual_commit=actual_commit,
        actual_tag=actual_tag,
        actual_tag_target_commit=actual_tag_target_commit,
        actual_migration_revision=actual_migration_revision,
        findings=findings,
    )
    if service_probe is not None:
        _validate_service_reachability(document, service_probe, findings)
    ordered = _ordered_findings(findings)
    decision = NO_GO if _has_blocker(ordered) else GO
    return ValidationReport(decision, manifest_sha256(document), ordered)


def validate_pilot_contract(
    manifest: JsonSource,
    ownership: JsonSource,
    limitations: JsonSource,
    release_record: JsonSource,
    *,
    environment: Mapping[str, str] | None = None,
    actual_commit: str | None = None,
    actual_tag: str | None = None,
    actual_tag_target_commit: str | None = None,
    actual_migration_revision: str | None = None,
    service_probe: ServiceProbe | None = None,
    repository_root: str | Path | None = None,
) -> ValidationReport:
    """Validate the complete PM9 contract and calculate the pilot decision."""

    manifest_document = load_json_document(manifest)
    ownership_document = load_json_document(ownership)
    limitation_document = load_json_document(limitations)
    release_document = load_json_document(release_record)
    root = Path(repository_root or Path.cwd()).resolve()
    findings: list[Finding] = []

    for scope, document in (
        ("manifest", manifest_document),
        ("ownership", ownership_document),
        ("limitations", limitation_document),
        ("release_record", release_document),
    ):
        _validate_safe_document(document, scope, findings)

    _validate_manifest_structure(manifest_document, root, findings)
    if environment is not None:
        _validate_environment(manifest_document, environment, root, findings)
    _validate_release_observations(
        manifest_document,
        environment=environment,
        actual_commit=actual_commit,
        actual_tag=actual_tag,
        actual_tag_target_commit=actual_tag_target_commit,
        actual_migration_revision=actual_migration_revision,
        findings=findings,
    )
    if service_probe is not None:
        _validate_service_reachability(manifest_document, service_probe, findings)
    _validate_ownership(ownership_document, findings)
    _validate_limitations(limitation_document, findings)
    digest = manifest_sha256(manifest_document)
    _validate_release_record(
        release_document,
        manifest_document,
        ownership_document,
        limitation_document,
        digest,
        actual_commit,
        findings,
    )
    if release_document.get("record_status") == "final":
        _validate_final_release_observation_presence(
            environment=environment,
            actual_tag=actual_tag,
            actual_tag_target_commit=actual_tag_target_commit,
            actual_migration_revision=actual_migration_revision,
            findings=findings,
        )

    semantic_decision = evaluate_pilot_decision(
        release_document,
        ownership_document,
        limitation_document,
    )
    preliminary = NO_GO if _has_blocker(findings) else semantic_decision
    external_pilot_blocked = _has_external_pilot_blocked_classification(release_document)
    expected_declared = (
        EXTERNAL_PILOT_NO_GO if preliminary == NO_GO and external_pilot_blocked else preliminary
    )
    declared = release_document.get("final_decision")
    if declared not in ALLOWED_DECISIONS:
        _add(
            findings,
            "invalid_final_decision",
            "release_record",
            "Quyết định phải dùng đúng một giá trị trong danh sách cho phép.",
        )
    elif declared != expected_declared:
        _add(
            findings,
            "declared_decision_mismatch",
            "release_record",
            "Quyết định đã ghi không khớp kết quả tất định của contract.",
        )

    ordered = _ordered_findings(findings)
    decision = (
        EXTERNAL_PILOT_NO_GO
        if _has_blocker(ordered) and external_pilot_blocked
        else NO_GO
        if _has_blocker(ordered)
        else semantic_decision
    )
    return ValidationReport(decision, digest, ordered)


def _has_external_pilot_blocked_classification(record: Mapping[str, Any]) -> bool:
    """Recognize the truthful PM9 design-ready/external-dependency decision model."""

    gates = _mapping(record.get("decision_gates"))
    engineering = _mapping(gates.get("engineering_readiness"))
    local = _mapping(gates.get("local_rehearsal"))
    real_company = _mapping(gates.get("real_company_pilot"))
    return (
        record.get("implementation_status") == "COMPLETE"
        and engineering.get("status") == "PASS"
        and local.get("status") in {"PASS", "PARTIAL", "FAIL"}
        and real_company.get("status") == "BLOCKED_EXTERNAL_DEPENDENCY"
        and real_company.get("display_status") == "BLOCKED \u2014 EXTERNAL DEPENDENCY"
        and record.get("overall_external_pilot_decision") == EXTERNAL_PILOT_NO_GO
        and record.get("final_decision") == EXTERNAL_PILOT_NO_GO
    )


def evaluate_pilot_decision(
    release_record: JsonSource,
    ownership: JsonSource,
    limitations: JsonSource,
) -> str:
    """Return GO, CONDITIONAL GO, or NO-GO from explicit recorded state."""

    release = load_json_document(release_record)
    ownership_document = load_json_document(ownership)
    limitation_document = load_json_document(limitations)

    if not _ownership_ready(ownership_document):
        return NO_GO
    if not _critical_limitations_accepted(limitation_document):
        return NO_GO
    assignments = _mapping(ownership_document.get("assignments"))
    assigned_roles = {
        _mapping(assignments.get(key)).get("assigned_role") for key in REQUIRED_OWNERS
    }

    gates = release.get("gates")
    if not isinstance(gates, list):
        return NO_GO
    gate_by_id: dict[str, Mapping[str, Any]] = {}
    for gate in gates:
        if not isinstance(gate, Mapping):
            return NO_GO
        gate_id = gate.get("id")
        if not isinstance(gate_id, str) or not gate_id or gate_id in gate_by_id:
            return NO_GO
        gate_by_id[gate_id] = gate
    for gate_id in CRITICAL_GATES:
        gate = gate_by_id.get(gate_id)
        if (
            not isinstance(gate, Mapping)
            or gate.get("critical") is not True
            or gate.get("status") != "passed"
            or not _valid_evidence_links(gate.get("evidence_links"))
        ):
            return NO_GO

    rollback = release.get("rollback")
    if not isinstance(rollback, Mapping) or rollback.get("ready") is not True:
        return NO_GO
    if rollback.get("rehearsal_status") != "passed":
        return NO_GO

    open_risks = release.get("open_risks", [])
    if not isinstance(open_risks, list):
        return NO_GO
    bounded_items: set[str] = set()
    risk_ids: set[str] = set()
    for risk in open_risks:
        if not isinstance(risk, Mapping):
            return NO_GO
        risk_id = risk.get("id")
        if not _non_placeholder_text(risk_id) or risk_id in risk_ids:
            return NO_GO
        risk_ids.add(risk_id)
        status = risk.get("status")
        severity = risk.get("severity")
        category = risk.get("category")
        if (
            not isinstance(status, str)
            or status not in ALLOWED_RISK_STATUSES
            or not isinstance(severity, str)
            or severity not in ALLOWED_RISK_SEVERITIES
            or not isinstance(category, str)
            or category not in ALLOWED_RISK_CATEGORIES
        ):
            return NO_GO
        if severity == "critical" or category in PROTECTED_RISK_CATEGORIES:
            return NO_GO
        bounded_items.add(risk_id)

    limitations_list = limitation_document.get("limitations", [])
    if not isinstance(limitations_list, list):
        return NO_GO
    for limitation in limitations_list:
        if not isinstance(limitation, Mapping):
            return NO_GO
        limitation_id = limitation.get("id")
        if not _non_placeholder_text(limitation_id) or limitation_id in risk_ids:
            return NO_GO
        if limitation.get("acceptance_status") != "accepted":
            if limitation.get("critical") is True:
                return NO_GO
            bounded_items.add(limitation_id)

    conditions = release.get("conditions", [])
    if not isinstance(conditions, list):
        return NO_GO
    condition_by_item: dict[str, Mapping[str, Any]] = {}
    for condition in conditions:
        if (
            not isinstance(condition, Mapping)
            or not _condition_is_bounded(condition)
            or condition.get("owner_role") not in assigned_roles
        ):
            return NO_GO
        item_id = condition.get("risk_or_limitation_id")
        if not _non_placeholder_text(item_id) or item_id in condition_by_item:
            return NO_GO
        condition_by_item[item_id] = condition
    if set(condition_by_item) != bounded_items:
        return NO_GO
    if bounded_items:
        return CONDITIONAL_GO
    return GO


def generate_release_record(
    manifest: JsonSource,
    ownership: JsonSource,
    limitations: JsonSource,
    *,
    gate_results: Mapping[str, JsonMapping] | None = None,
    evidence_links: Sequence[str] = (),
    open_risks: Sequence[JsonMapping] = (),
    conditions: Sequence[JsonMapping] = (),
    generated_at_utc: str | None = None,
    release_commit: str | None = None,
) -> dict[str, Any]:
    """Build a redacted, reviewable release record without persisting it."""

    manifest_document = load_json_document(manifest)
    ownership_document = load_json_document(ownership)
    limitation_document = load_json_document(limitations)
    release = _mapping(manifest_document.get("release"))
    versions = _mapping(manifest_document.get("versions"))
    jobs = _list_of_mappings(manifest_document.get("scheduled_jobs"))
    owner_assignments = _mapping(ownership_document.get("assignments"))
    limitation_rows = _list_of_mappings(limitation_document.get("limitations"))
    supplied_gates = gate_results or {}

    gates: list[dict[str, Any]] = []
    for gate_id in sorted(CRITICAL_GATES):
        supplied = _mapping(supplied_gates.get(gate_id))
        gates.append(
            {
                "id": gate_id,
                "critical": True,
                "status": supplied.get("status", "unverified"),
                "evidence_links": list(supplied.get("evidence_links", [])),
            }
        )

    rollback_manifest = _mapping(manifest_document.get("rollback"))
    record: dict[str, Any] = {
        "schema_version": "1.0",
        "record_kind": "internal_pilot_release_record",
        "record_status": "draft",
        "generated_at_utc": generated_at_utc,
        "release": {
            "release_name": release.get("release_id"),
            "git_commit": release_commit or "PENDING_EXACT_TAG_TARGET",
            "git_tag_recommendation": release.get("tag_recommendation"),
            "migration_revision": release.get("alembic_revision"),
            "deployment_manifest_sha256": manifest_sha256(manifest_document),
        },
        "application_versions": dict(versions),
        "database_version": versions.get("postgresql"),
        "enabled_jobs": sorted(
            row.get("job_type")
            for row in jobs
            if row.get("enabled") is True and isinstance(row.get("job_type"), str)
        ),
        "configured_alert_thresholds": dict(_mapping(manifest_document.get("operational_alerts"))),
        "backup_validation": {
            "status": "unverified",
            "validated_at_utc": None,
            "evidence_links": [],
        },
        "restore_validation": {
            "status": "unverified",
            "validated_at_utc": None,
            "evidence_links": [],
        },
        "load_and_soak_profiles": {
            "status": "unverified",
            "summaries": [],
            "evidence_links": [],
        },
        "attachment_restore": {
            "status": "unverified",
            "validated_at_utc": None,
            "evidence_links": [],
        },
        "secret_rotation": {
            "status": "unverified",
            "validated_at_utc": None,
            "evidence_links": [],
        },
        "open_risks": list(open_risks),
        "ownership_status": {
            key: _mapping(owner_assignments.get(key)).get("status", "unassigned")
            for key in REQUIRED_OWNERS
        },
        "incident_contact_status": _mapping(ownership_document.get("incident_communication")).get(
            "status", "unconfigured"
        ),
        "known_limitations_acceptance_status": (
            "accepted"
            if limitation_rows
            and all(row.get("acceptance_status") == "accepted" for row in limitation_rows)
            else "pending"
        ),
        "rollback": {
            "target_release_id": rollback_manifest.get("target_release_id"),
            "target_git_tag": rollback_manifest.get("target_git_tag"),
            "target_git_commit": rollback_manifest.get("target_git_commit"),
            "target_alembic_revision": rollback_manifest.get("target_alembic_revision"),
            "mode": rollback_manifest.get("mode"),
            "ready": rollback_manifest.get("rehearsal_status") == "passed",
            "rehearsal_status": rollback_manifest.get("rehearsal_status", "unverified"),
        },
        "gates": gates,
        "conditions": list(conditions),
        "final_decision": NO_GO,
        "evidence_links": list(evidence_links),
        "production_readiness_claim": False,
    }
    redacted = redact_release_record(record)
    redacted["final_decision"] = evaluate_pilot_decision(
        redacted, ownership_document, limitation_document
    )
    return redacted


def redact_release_record(value: Any) -> Any:
    """Recursively remove credential values, personal contacts, and local paths."""

    def visit(item: Any, key: str | None = None) -> Any:
        normalized_key = (key or "").casefold()
        if normalized_key in _SENSITIVE_VALUE_KEYS or normalized_key.endswith(
            ("_password", "_secret", "_token", "_credential")
        ):
            return "[REDACTED]"
        if isinstance(item, Mapping):
            return {
                str(child_key): visit(child, str(child_key)) for child_key, child in item.items()
            }
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, tuple):
            return [visit(child) for child in item]
        if isinstance(item, str):
            if _looks_like_local_absolute_path(item):
                return "[REDACTED_LOCAL_PATH]"
            if _url_contains_credentials(item):
                return "[REDACTED_CREDENTIAL_URL]"
            if _EMAIL_RE.search(item) or _PHONE_RE.search(item):
                return "[REDACTED_PERSONAL_CONTACT]"
        return item

    return visit(value)


def _validate_manifest_structure(
    document: dict[str, Any],
    repository_root: Path,
    findings: list[Finding],
) -> None:
    _require_keys(
        document,
        {
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
        },
        "manifest",
        findings,
    )
    if not _versioned(document):
        _add(
            findings,
            "invalid_schema_version",
            "manifest",
            "Deployment manifest phải có schema_version rõ ràng.",
        )
    if document.get("manifest_kind") != "ai_maintenance_copilot_internal_pilot":
        _add(
            findings,
            "invalid_manifest_kind",
            "manifest",
            "Deployment manifest không đúng loại internal pilot.",
        )
    if document.get("production_readiness_claim") is not False:
        _add(
            findings,
            "production_readiness_claim_forbidden",
            "manifest",
            "Contract internal pilot không được tuyên bố production readiness.",
        )

    release = _mapping(document.get("release"))
    _require_keys(
        release,
        {
            "release_id",
            "commit_resolution",
            "tag_recommendation",
            "tag_status",
            "alembic_revision",
        },
        "manifest.release",
        findings,
    )
    commit_resolution = release.get("commit_resolution")
    if commit_resolution != _EXACT_TAG_TARGET_COMMIT_RESOLUTION:
        code = "invalid_commit_resolution"
        _add(
            findings,
            code,
            "manifest.release.commit_resolution",
            "Release commit phải được resolve từ exact Git tag target.",
        )
    if release.get("tag_status") not in {"checkpointed", "verified"}:
        _add(
            findings,
            "release_tag_pending",
            "manifest.release",
            "Git tag recommendation chưa được xác nhận tại checkpoint.",
        )
    for key in ("release_id", "tag_recommendation", "alembic_revision"):
        if not _non_placeholder_text(release.get(key)):
            _add(
                findings,
                "missing_release_identity",
                f"manifest.release.{key}",
                "Release identity còn thiếu hoặc đang là placeholder.",
            )

    versions = _mapping(document.get("versions"))
    required_versions = {
        "application",
        "frontend",
        "python",
        "node",
        "postgresql",
        "qdrant",
    }
    _require_keys(versions, required_versions, "manifest.versions", findings)
    for name in required_versions:
        if not _non_placeholder_text(versions.get(name)):
            _add(
                findings,
                "missing_component_version",
                f"manifest.versions.{name}",
                "Mọi runtime bắt buộc phải có version không phải placeholder.",
            )

    images = _mapping(document.get("images"))
    required_images = {
        "application",
        "frontend",
        "python_base",
        "node_base",
        "postgresql",
        "qdrant",
    }
    _require_keys(images, required_images, "manifest.images", findings)
    for name in required_images:
        value = images.get(name)
        invalid_digest = (
            isinstance(value, str)
            and "@sha256:" in value
            and len(value.rsplit("@sha256:", 1)[1]) != 64
        )
        if not _non_placeholder_text(value) or str(value).endswith(":latest") or invalid_digest:
            _add(
                findings,
                "invalid_image_reference",
                f"manifest.images.{name}",
                "Image reference phải rõ ràng và không được dùng thẻ latest.",
            )

    services = _list_of_mappings(
        document.get("services"),
        findings=findings,
        scope="manifest.services",
    )
    if not isinstance(document.get("services"), list):
        _add(findings, "invalid_services", "manifest.services", "services phải là list.")
    service_names = _check_unique_names(services, "name", "service", findings)
    missing_services = REQUIRED_SERVICES - service_names
    unsupported_services = service_names - REQUIRED_SERVICES
    for name in sorted(missing_services):
        _add(
            findings,
            "required_service_missing",
            f"manifest.services.{name}",
            f"Thiếu service bắt buộc: {name}.",
        )
    for name in sorted(unsupported_services):
        _add(
            findings,
            "unsupported_service",
            f"manifest.services.{name}",
            f"Service ngoài contract PM9: {name}.",
        )
    for service in services:
        name = service.get("name")
        if service.get("required") is not True:
            _add(
                findings,
                "service_not_required",
                f"manifest.services.{name}",
                "Mỗi service trong closed pilot topology phải được đánh dấu required=true.",
            )
        version_ref = service.get("version_ref")
        if version_ref not in versions:
            _add(
                findings,
                "service_version_reference_invalid",
                f"manifest.services.{name}",
                "Service phải tham chiếu component version đã khai báo.",
            )

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

    volumes = _list_of_mappings(
        document.get("volumes"),
        findings=findings,
        scope="manifest.volumes",
    )
    if not isinstance(document.get("volumes"), list):
        _add(findings, "invalid_volumes", "manifest.volumes", "volumes phải là list.")
    _check_unique_names(volumes, "name", "volume", findings)
    purposes = {
        volume.get("purpose") for volume in volumes if isinstance(volume.get("purpose"), str)
    }
    for purpose in {
        "transactional_database",
        "rag_document_index",
        "local_attachment_bytes",
        "batch_analytics_contracts",
        "validated_backup_archives",
    } - purposes:
        _add(
            findings,
            "required_volume_missing",
            f"manifest.volumes.{purpose}",
            f"Thiếu persistent volume cho {purpose}.",
        )
    for volume in volumes:
        if volume.get("service") not in service_names:
            _add(
                findings,
                "volume_service_unknown",
                "manifest.volumes",
                "Volume tham chiếu service không tồn tại.",
            )
        kind = volume.get("kind")
        if kind not in {
            "compose_named_volume",
            "host_bind",
            "operator_managed_directory",
        }:
            _add(
                findings,
                "invalid_volume_kind",
                f"manifest.volumes.{volume.get('name')}",
                "Persistent storage phải khai báo loại volume được hỗ trợ.",
            )
        if kind in {"host_bind", "operator_managed_directory"}:
            storage_path_ref = volume.get("storage_path_ref")
            if storage_path_ref not in _mapping(_mapping(document.get("storage")).get("paths")):
                _add(
                    findings,
                    "volume_storage_path_unknown",
                    f"manifest.volumes.{volume.get('name')}",
                    "Host storage phải tham chiếu storage path đã khai báo.",
                )
        mounted_by = volume.get("mounted_by")
        if mounted_by is not None and (
            not isinstance(mounted_by, list)
            or not mounted_by
            or any(service not in service_names for service in mounted_by)
        ):
            _add(
                findings,
                "volume_mount_service_unknown",
                f"manifest.volumes.{volume.get('name')}",
                "mounted_by chỉ được tham chiếu service trong closed topology.",
            )
        if volume.get("persistent") is not True:
            _add(
                findings,
                "volume_not_persistent",
                "manifest.volumes",
                "Volume pilot phải được đánh dấu persistent=true.",
            )

    _validate_storage(document, repository_root, findings)
    _validate_environment_declarations(document, findings)
    _validate_repository_contract(document, repository_root, findings)
    _validate_health_endpoints(document, service_names, findings)
    _validate_job_catalog(document, findings)
    _validate_runtime_settings(document, findings)


def _validate_storage(
    document: dict[str, Any],
    repository_root: Path,
    findings: list[Finding],
) -> None:
    storage = _mapping(document.get("storage"))
    roots = _mapping(storage.get("allowed_roots"))
    paths = _mapping(storage.get("paths"))
    if not roots:
        _add(
            findings,
            "allowed_roots_missing",
            "manifest.storage",
            "Storage contract phải khai báo allowed_roots.",
        )
    resolved_roots: dict[str, Path] = {}
    for name, root_value in roots.items():
        root_contract = _mapping(root_value)
        environment_name = root_contract.get("environment_variable")
        if (
            not isinstance(environment_name, str)
            or not _ENV_NAME_RE.fullmatch(environment_name)
            or root_contract.get("scope") != "host"
            or root_contract.get("outside_repository") is not True
            or set(root_contract) != {"environment_variable", "scope", "outside_repository"}
        ):
            _add(
                findings,
                "invalid_allowed_root",
                f"manifest.storage.allowed_roots.{name}",
                "Allowed root phải tham chiếu biến môi trường host nằm ngoài repository.",
            )
            continue
        resolved_roots[str(name)] = repository_root

    for required_path in ("attachments", "analytics_source", "analytics_output", "backups"):
        row = _mapping(paths.get(required_path))
        if not row:
            _add(
                findings,
                "required_storage_path_missing",
                f"manifest.storage.paths.{required_path}",
                "Thiếu storage path bắt buộc.",
            )
            continue
        root_name = row.get("root")
        relative_path = row.get("relative_path")
        if root_name not in resolved_roots:
            _add(
                findings,
                "storage_root_unknown",
                f"manifest.storage.paths.{required_path}",
                "Storage path tham chiếu allowed root không tồn tại.",
            )
            continue
        if not _safe_relative_path(relative_path):
            _add(
                findings,
                "path_containment_violation",
                f"manifest.storage.paths.{required_path}",
                "Storage path phải là đường dẫn tương đối nằm trong allowed root.",
            )
            continue
        target = (resolved_roots[str(root_name)] / str(relative_path)).resolve()
        if not target.is_relative_to(resolved_roots[str(root_name)]):
            _add(
                findings,
                "path_containment_violation",
                f"manifest.storage.paths.{required_path}",
                "Storage path thoát khỏi allowed root.",
            )
        if required_path != "backups":
            container_path = row.get("container_path")
            configuration_environment = row.get("configuration_environment")
            if (
                not _safe_container_path(container_path)
                or not isinstance(configuration_environment, str)
                or not _ENV_NAME_RE.fullmatch(configuration_environment)
            ):
                _add(
                    findings,
                    "invalid_container_storage_path",
                    f"manifest.storage.paths.{required_path}",
                    "Application storage phải có container path tuyệt đối và biến cấu hình.",
                )
        else:
            retention = row.get("retention_keep_count")
            if type(retention) is not int or not 1 <= retention <= 365:
                _add(
                    findings,
                    "invalid_backup_retention",
                    "manifest.storage.paths.backups.retention_keep_count",
                    "Số bản backup giữ lại phải nằm trong khoảng 1..365.",
                )


def _validate_environment_declarations(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
    raw = document.get("required_environment_variables")
    rows = _list_of_mappings(
        raw,
        findings=findings,
        scope="manifest.required_environment_variables",
    )
    if not isinstance(raw, list):
        _add(
            findings,
            "invalid_environment_contract",
            "manifest.required_environment_variables",
            "required_environment_variables phải là list chỉ chứa tên và secret flag.",
        )
    names: set[str] = set()
    for row in rows:
        name = row.get("name")
        if not isinstance(name, str) or not _ENV_NAME_RE.fullmatch(name):
            _add(
                findings,
                "invalid_environment_name",
                "manifest.required_environment_variables",
                "Environment variable phải có tên uppercase hợp lệ.",
            )
            continue
        if name in names:
            _add(
                findings,
                "duplicate_environment_name",
                f"manifest.required_environment_variables.{name}",
                "Environment variable bị khai báo trùng.",
            )
        names.add(name)
        if set(row) - {"name", "secret"}:
            _add(
                findings,
                "environment_value_in_manifest",
                f"manifest.required_environment_variables.{name}",
                "Manifest chỉ được ghi tên environment variable và secret flag.",
            )
        if type(row.get("secret")) is not bool:
            _add(
                findings,
                "environment_secret_flag_missing",
                f"manifest.required_environment_variables.{name}",
                "Mỗi environment variable phải có secret flag kiểu boolean.",
            )
    for name in sorted(REQUIRED_PILOT_ENVIRONMENT - names):
        _add(
            findings,
            "required_environment_name_missing",
            f"manifest.required_environment_variables.{name}",
            f"Thiếu tên environment variable bắt buộc: {name}.",
        )
    flags = {row.get("name"): row.get("secret") for row in rows if isinstance(row.get("name"), str)}
    for name in sorted(SECRET_ENVIRONMENT_NAMES):
        if flags.get(name) is not True:
            _add(
                findings,
                "secret_environment_not_marked",
                f"manifest.required_environment_variables.{name}",
                f"{name} phải được đánh dấu secret=true.",
            )


def _validate_repository_contract(
    document: dict[str, Any],
    repository_root: Path,
    findings: list[Finding],
) -> None:
    """Bind the manifest to the checked-in Compose and runtime release sources."""

    compose_relative = document.get("compose_file")
    if not _safe_relative_path(compose_relative):
        _add(
            findings,
            "invalid_compose_file",
            "manifest.compose_file",
            "Compose file phải là đường dẫn tương đối nằm trong repository.",
        )
        return
    compose_path = (repository_root / str(compose_relative)).resolve()
    if not compose_path.is_relative_to(repository_root) or not compose_path.is_file():
        _add(
            findings,
            "compose_file_missing",
            "manifest.compose_file",
            "Không tìm thấy Compose file đã khai báo.",
        )
        return
    try:
        compose_text = compose_path.read_text(encoding="utf-8")
    except OSError:
        _add(
            findings,
            "compose_file_unreadable",
            "manifest.compose_file",
            "Không thể đọc Compose file đã khai báo.",
        )
        return

    declarations = _list_of_mappings(document.get("required_environment_variables"))
    declared_names = {row.get("name") for row in declarations if isinstance(row.get("name"), str)}
    compose_required = set(_COMPOSE_REQUIRED_ENV_RE.findall(compose_text))
    for name in sorted(compose_required - declared_names):
        _add(
            findings,
            "compose_environment_not_declared",
            f"manifest.required_environment_variables.{name}",
            f"Biến bắt buộc của Compose chưa có trong manifest: {name}.",
        )

    release = _mapping(document.get("release"))
    versions = _mapping(document.get("versions"))
    if versions.get("application") != APPLICATION_VERSION:
        _add(
            findings,
            "application_version_mismatch",
            "manifest.versions.application",
            "Application version trong manifest không khớp runtime.",
        )
    if release.get("alembic_revision") != CANONICAL_SCHEMA_REVISION:
        _add(
            findings,
            "canonical_migration_revision_mismatch",
            "manifest.release.alembic_revision",
            "Alembic revision trong manifest không khớp schema head của ứng dụng.",
        )

    images = _mapping(document.get("images"))
    source_expectations = (
        (
            repository_root / "Dockerfile",
            f"FROM {images.get('python_base', '')}",
            "manifest.images.python_base",
        ),
        (
            repository_root / "frontend" / "Dockerfile",
            f"FROM {images.get('node_base', '')}",
            "manifest.images.node_base",
        ),
        (
            compose_path,
            f"image: {images.get('postgresql', '')}",
            "manifest.images.postgresql",
        ),
        (
            compose_path,
            f"image: {images.get('qdrant', '')}",
            "manifest.images.qdrant",
        ),
    )
    for source_path, expected_text, scope in source_expectations:
        try:
            source_text = source_path.read_text(encoding="utf-8")
        except OSError:
            _add(
                findings,
                "runtime_source_unreadable",
                scope,
                "Không thể đọc runtime source để đối chiếu version.",
            )
            continue
        if not expected_text.strip() or expected_text not in source_text:
            _add(
                findings,
                "runtime_image_mismatch",
                scope,
                "Image trong manifest không khớp deployment source.",
            )

    package_path = repository_root / "frontend" / "package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _add(
            findings,
            "frontend_package_unreadable",
            "manifest.versions.frontend",
            "Không thể đọc frontend package metadata để đối chiếu version.",
        )
        return
    dependencies = _mapping(package.get("dependencies"))
    if package.get("version") != versions.get("frontend"):
        _add(
            findings,
            "frontend_version_mismatch",
            "manifest.versions.frontend",
            "Frontend version trong manifest không khớp package metadata.",
        )
    if dependencies.get("next") != versions.get("nextjs"):
        _add(
            findings,
            "nextjs_version_mismatch",
            "manifest.versions.nextjs",
            "Next.js version trong manifest không khớp package metadata.",
        )


def _validate_health_endpoints(
    document: dict[str, Any],
    service_names: set[str],
    findings: list[Finding],
) -> None:
    endpoints = _list_of_mappings(
        document.get("health_endpoints"),
        findings=findings,
        scope="manifest.health_endpoints",
    )
    kinds = {endpoint.get("kind") for endpoint in endpoints}
    for kind in {"liveness", "readiness", "worker_readiness"} - kinds:
        _add(
            findings,
            "health_endpoint_missing",
            f"manifest.health_endpoints.{kind}",
            f"Thiếu endpoint {kind}.",
        )
    seen: set[tuple[Any, Any]] = set()
    for endpoint in endpoints:
        key = (endpoint.get("service"), endpoint.get("path"))
        if key in seen:
            _add(
                findings,
                "duplicate_health_endpoint",
                "manifest.health_endpoints",
                "Health endpoint bị khai báo trùng.",
            )
        seen.add(key)
        if endpoint.get("service") not in service_names:
            _add(
                findings,
                "health_service_unknown",
                "manifest.health_endpoints",
                "Health endpoint tham chiếu service không tồn tại.",
            )
        path = endpoint.get("path")
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or "://" in path
            or ".." in PurePosixPath(path).parts
        ):
            _add(
                findings,
                "invalid_health_path",
                "manifest.health_endpoints",
                "Health endpoint phải là URL path tương đối theo host.",
            )
        statuses = endpoint.get("expected_status")
        if (
            not isinstance(statuses, list)
            or not statuses
            or any(type(status) is not int or not 100 <= status <= 599 for status in statuses)
        ):
            _add(
                findings,
                "invalid_health_status",
                "manifest.health_endpoints",
                "Health endpoint phải khai báo expected HTTP status.",
            )


def _validate_job_catalog(document: dict[str, Any], findings: list[Finding]) -> None:
    raw = document.get("scheduled_jobs")
    jobs = _list_of_mappings(
        raw,
        findings=findings,
        scope="manifest.scheduled_jobs",
    )
    if not isinstance(raw, list):
        _add(
            findings,
            "invalid_job_catalog",
            "manifest.scheduled_jobs",
            "scheduled_jobs phải là list.",
        )
    names: set[str] = set()
    for job in jobs:
        name = job.get("job_type")
        if not isinstance(name, str):
            _add(
                findings,
                "invalid_job_type",
                "manifest.scheduled_jobs",
                "Mỗi job phải có job_type.",
            )
            continue
        if name in names:
            _add(
                findings,
                "duplicate_job",
                f"manifest.scheduled_jobs.{name}",
                "Job bị khai báo trùng.",
            )
        names.add(name)
        if type(job.get("enabled")) is not bool:
            _add(
                findings,
                "job_enabled_not_explicit",
                f"manifest.scheduled_jobs.{name}",
                "Mỗi job phải có enabled kiểu boolean.",
            )
        if set(job) != {"job_type", "enabled"}:
            _add(
                findings,
                "job_configuration_not_closed",
                f"manifest.scheduled_jobs.{name}",
                "Deployment manifest không được nhận cấu hình executable tùy ý.",
            )
    for name in sorted(names - SUPPORTED_JOBS):
        _add(
            findings,
            "unsupported_job",
            f"manifest.scheduled_jobs.{name}",
            f"Job ngoài closed catalog: {name}.",
        )
    for name in sorted(SUPPORTED_JOBS - names):
        _add(
            findings,
            "supported_job_missing",
            f"manifest.scheduled_jobs.{name}",
            f"Closed catalog phải khai báo job {name} với enabled rõ ràng.",
        )


def _validate_runtime_settings(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
    sections = {
        "worker": {
            "instance_count",
            "poll_interval_seconds",
            "heartbeat_interval_seconds",
            "heartbeat_stale_seconds",
            "outbox_lease_seconds",
            "batch_size",
        },
        "operational_alerts": {
            "outbox_oldest_age_seconds",
            "repeated_job_failure_count",
            "analytics_stale_seconds",
            "backup_overdue_seconds",
            "worker_heartbeat_stale_seconds",
            "disk_warning_free_percent",
            "disk_critical_free_percent",
            "delivery",
        },
        "database": {
            "pool_size",
            "max_overflow",
            "connect_timeout_seconds",
            "pool_timeout_seconds",
            "statement_timeout_seconds",
            "lock_timeout_seconds",
            "idle_transaction_timeout_seconds",
        },
    }
    for section_name, keys in sections.items():
        section = _mapping(document.get(section_name))
        _require_keys(section, keys, f"manifest.{section_name}", findings)
    worker = _mapping(document.get("worker"))
    if worker.get("instance_count") != 1:
        _add(
            findings,
            "unsupported_worker_topology",
            "manifest.worker.instance_count",
            "Internal pilot contract chỉ hỗ trợ một worker instance.",
        )
    heartbeat = worker.get("heartbeat_interval_seconds")
    stale = worker.get("heartbeat_stale_seconds")
    if type(heartbeat) is not int or type(stale) is not int or heartbeat <= 0 or stale <= heartbeat:
        _add(
            findings,
            "invalid_worker_heartbeat_window",
            "manifest.worker",
            "Heartbeat stale window phải lớn hơn heartbeat interval.",
        )
    for section_name in ("worker", "database"):
        section = _mapping(document.get(section_name))
        for key, value in section.items():
            if key == "max_overflow":
                valid = type(value) is int and value >= 0
            else:
                valid = type(value) is int and value > 0
            if not valid:
                _add(
                    findings,
                    "invalid_runtime_setting",
                    f"manifest.{section_name}.{key}",
                    "Runtime numeric setting phải có giá trị nguyên dương có giới hạn.",
                )
    alerts = _mapping(document.get("operational_alerts"))
    if alerts.get("delivery") != "in_app_only":
        _add(
            findings,
            "unsupported_alert_delivery",
            "manifest.operational_alerts.delivery",
            "Pilot chỉ cho phép cảnh báo in-app.",
        )
    for key, value in alerts.items():
        if key != "delivery" and (type(value) is not int or value <= 0):
            _add(
                findings,
                "invalid_alert_threshold",
                f"manifest.operational_alerts.{key}",
                "Alert threshold phải là số nguyên dương.",
            )
    warning_percent = alerts.get("disk_warning_free_percent")
    critical_percent = alerts.get("disk_critical_free_percent")
    if (
        type(warning_percent) is not int
        or type(critical_percent) is not int
        or critical_percent >= warning_percent
    ):
        _add(
            findings,
            "invalid_disk_threshold_order",
            "manifest.operational_alerts",
            "Ngưỡng disk critical phải thấp hơn ngưỡng warning.",
        )

    retry = _mapping(document.get("retry_and_dead_letter"))
    jobs = _mapping(retry.get("jobs"))
    if set(jobs) != SUPPORTED_JOBS:
        _add(
            findings,
            "retry_job_catalog_mismatch",
            "manifest.retry_and_dead_letter.jobs",
            "Retry settings phải khớp đúng closed four-job catalog.",
        )
    for name, row_value in jobs.items():
        row = _mapping(row_value)
        for key in ("max_attempts", "lease_seconds", "retry_backoff_seconds"):
            if type(row.get(key)) is not int or row.get(key) <= 0:
                _add(
                    findings,
                    "invalid_retry_setting",
                    f"manifest.retry_and_dead_letter.jobs.{name}.{key}",
                    "Retry setting phải là số nguyên dương.",
                )
    outbox = _mapping(retry.get("outbox"))
    for key in ("max_attempts", "retry_backoff_seconds"):
        if type(outbox.get(key)) is not int or outbox.get(key) <= 0:
            _add(
                findings,
                "invalid_outbox_retry_setting",
                f"manifest.retry_and_dead_letter.outbox.{key}",
                "Outbox retry setting phải là số nguyên dương.",
            )
    if (
        retry.get("dead_letter_operator_visible") is not True
        or retry.get("manual_redrive_only") is not True
    ):
        _add(
            findings,
            "dead_letter_contract_weakened",
            "manifest.retry_and_dead_letter",
            "Dead letter phải operator-visible và chỉ redrive bằng action rõ ràng.",
        )

    restore = _mapping(document.get("restore_prerequisites"))
    for key in (
        "separate_restore_database_required",
        "validated_checksum_required",
        "backup_metadata_required",
        "compatible_postgresql_tools_required",
        "attachment_snapshot_required_when_metadata_is_nonempty",
        "owner_approval_required",
    ):
        if restore.get(key) is not True:
            _add(
                findings,
                "restore_prerequisite_missing",
                f"manifest.restore_prerequisites.{key}",
                "Restore prerequisite bắt buộc phải được khai báo true.",
            )
    if restore.get("restore_database_name_suffix") != "_restore":
        _add(
            findings,
            "unsafe_restore_database_suffix",
            "manifest.restore_prerequisites.restore_database_name_suffix",
            "Database restore rehearsal phải có tên kết thúc bằng _restore.",
        )
    if restore.get("postgresql_integration_test_database_name_suffix") != "_test":
        _add(
            findings,
            "unsafe_postgresql_test_database_suffix",
            "manifest.restore_prerequisites.postgresql_integration_test_database_name_suffix",
            "PostgreSQL integration test database phải có tên kết thúc bằng _test.",
        )

    rollback = _mapping(document.get("rollback"))
    _require_keys(
        rollback,
        {
            "target_release_id",
            "target_git_tag",
            "target_git_commit",
            "target_alembic_revision",
            "mode",
            "database_downgrade_allowed",
            "validated_backup_required",
            "rehearsal_status",
        },
        "manifest.rollback",
        findings,
    )
    if not _COMMIT_RE.fullmatch(str(rollback.get("target_git_commit", ""))):
        _add(
            findings,
            "rollback_commit_invalid",
            "manifest.rollback.target_git_commit",
            "Rollback target phải dùng full Git SHA.",
        )
    if rollback.get("database_downgrade_allowed") is not False:
        _add(
            findings,
            "unsafe_database_downgrade",
            "manifest.rollback.database_downgrade_allowed",
            "PM9 không xác nhận migration downgrade an toàn; phải dùng validated restore.",
        )
    if rollback.get("validated_backup_required") is not True:
        _add(
            findings,
            "rollback_backup_not_required",
            "manifest.rollback.validated_backup_required",
            "Rollback restore phải yêu cầu validated backup.",
        )
    if rollback.get("rehearsal_status") != "passed":
        _add(
            findings,
            "rollback_rehearsal_unverified",
            "manifest.rollback.rehearsal_status",
            "Rollback rehearsal chưa có bằng chứng passed.",
        )


def _validate_environment(
    manifest: dict[str, Any],
    environment: Mapping[str, str],
    repository_root: Path,
    findings: list[Finding],
) -> None:
    declarations = _list_of_mappings(manifest.get("required_environment_variables"))
    required_names = {row.get("name") for row in declarations if isinstance(row.get("name"), str)}
    for name in sorted(required_names):
        if not environment.get(name):
            _add(
                findings,
                "environment_variable_missing",
                f"environment.{name}",
                f"Thiếu environment variable bắt buộc: {name}.",
            )
        elif _is_placeholder(environment[name]):
            _add(
                findings,
                "environment_placeholder",
                f"environment.{name}",
                f"Environment variable {name} vẫn chứa placeholder.",
            )
    for name in SECRET_ENVIRONMENT_NAMES:
        if not environment.get(name):
            _add(
                findings,
                "pilot_secret_missing",
                f"environment.{name}",
                f"Pilot secret {name} chưa được inject.",
            )

    if environment.get("APP_ENVIRONMENT") != "pilot":
        _add(
            findings,
            "pilot_environment_required",
            "environment.APP_ENVIRONMENT",
            "APP_ENVIRONMENT phải là pilot.",
        )
    if environment.get("STORAGE_BACKEND") != "postgresql":
        _add(
            findings,
            "postgresql_storage_required",
            "environment.STORAGE_BACKEND",
            "Pilot phải dùng PostgreSQL primary storage.",
        )
    if not _truthy(environment.get("AUTH_COOKIE_SECURE")):
        _add(
            findings,
            "secure_cookie_required",
            "environment.AUTH_COOKIE_SECURE",
            "Pilot phải bật secure refresh cookie.",
        )

    signing_secret = environment.get("TOKEN_SIGNING_SECRET", "")
    if signing_secret and (len(signing_secret) < 32 or _is_placeholder(signing_secret)):
        _add(
            findings,
            "pilot_signing_secret_invalid",
            "environment.TOKEN_SIGNING_SECRET",
            "Pilot signing secret thiếu độ dài hoặc vẫn là placeholder.",
        )
    previous_secret = environment.get("TOKEN_SIGNING_PREVIOUS_SECRET", "")
    if previous_secret and (len(previous_secret) < 32 or previous_secret == signing_secret):
        _add(
            findings,
            "previous_signing_secret_invalid",
            "environment.TOKEN_SIGNING_PREVIOUS_SECRET",
            "Previous signing secret không hợp lệ cho rotation overlap.",
        )

    for name in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        value = environment.get(name, "")
        if value and (_is_placeholder(value) or value.casefold() == "maintenance"):
            _add(
                findings,
                "development_database_default",
                f"environment.{name}",
                f"{name} vẫn dùng development default hoặc placeholder.",
            )
    password = environment.get("POSTGRES_PASSWORD", "")
    if password and len(password) < 16:
        _add(
            findings,
            "database_password_too_short",
            "environment.POSTGRES_PASSWORD",
            "Pilot database password chưa đạt độ dài tối thiểu của contract.",
        )

    database_url = environment.get("DATABASE_URL", "")
    if database_url:
        try:
            parsed = urlsplit(database_url)
        except ValueError:
            parsed = None
        if parsed is not None:
            try:
                parsed.port
            except ValueError:
                parsed = None
        if (
            parsed is None
            or parsed.scheme != "postgresql+psycopg"
            or not parsed.hostname
            or not parsed.username
            or not parsed.password
            or not parsed.path.strip("/")
        ):
            _add(
                findings,
                "database_url_invalid",
                "environment.DATABASE_URL",
                "DATABASE_URL pilot không đủ PostgreSQL connection components.",
            )
        elif (
            _is_placeholder(parsed.username)
            or _is_placeholder(parsed.password)
            or _is_placeholder(parsed.path.strip("/"))
            or (
                parsed.username.casefold() == "maintenance"
                and parsed.password.casefold() == "maintenance"
            )
        ):
            _add(
                findings,
                "development_database_url",
                "environment.DATABASE_URL",
                "DATABASE_URL vẫn dùng development default hoặc placeholder.",
            )
        elif (
            parsed.hostname != "postgres"
            or (parsed.port or 5432) != 5432
            or unquote(parsed.username or "") != environment.get("POSTGRES_USER")
            or unquote(parsed.path.strip("/")) != environment.get("POSTGRES_DB")
            or unquote(parsed.password or "") != environment.get("POSTGRES_PASSWORD")
        ):
            _add(
                findings,
                "database_environment_mismatch",
                "environment.DATABASE_URL",
                "DATABASE_URL phải khớp PostgreSQL service, user, password và database đã khai báo.",
            )

    for name in ("CORS_ALLOWED_ORIGINS", "TRUSTED_HOSTS"):
        value = environment.get(name, "")
        if value and (
            "*" in {part.strip() for part in value.split(",")}
            or "localhost" in value.casefold()
            or "127.0.0.1" in value
            or "testserver" in value.casefold()
        ):
            _add(
                findings,
                "development_network_default",
                f"environment.{name}",
                f"{name} vẫn dùng wildcard hoặc development host.",
            )
    cors_origins = [
        item.strip()
        for item in environment.get("CORS_ALLOWED_ORIGINS", "").split(",")
        if item.strip()
    ]
    if any(
        not _safe_service_url(origin) or urlsplit(origin).scheme != "https"
        for origin in cors_origins
    ):
        _add(
            findings,
            "pilot_cors_origin_invalid",
            "environment.CORS_ALLOWED_ORIGINS",
            "Mỗi pilot CORS origin phải là HTTPS origin không chứa credential.",
        )
    for name in ("FRONTEND_BASE_URL", "NEXT_PUBLIC_API_BASE_URL", "QDRANT_URL"):
        value = environment.get(name, "")
        if value and not _safe_service_url(value):
            _add(
                findings,
                "service_url_invalid",
                f"environment.{name}",
                f"{name} phải là http(s) URL không chứa credential.",
            )
        elif value:
            parsed_service = urlsplit(value)
            hostname = parsed_service.hostname
            if name != "QDRANT_URL" and hostname in {"localhost", "127.0.0.1", "::1"}:
                _add(
                    findings,
                    "development_network_default",
                    f"environment.{name}",
                    f"{name} vẫn dùng development host.",
                )
            if name != "QDRANT_URL" and parsed_service.scheme != "https":
                _add(
                    findings,
                    "pilot_tls_origin_required",
                    f"environment.{name}",
                    f"{name} phải dùng HTTPS cho pilot.",
                )
    qdrant_service = next(
        (
            service
            for service in _list_of_mappings(manifest.get("services"))
            if service.get("name") == "qdrant"
        ),
        {},
    )
    if environment.get("QDRANT_URL") and environment.get("QDRANT_URL") != qdrant_service.get(
        "internal_url"
    ):
        _add(
            findings,
            "qdrant_internal_url_mismatch",
            "environment.QDRANT_URL",
            "QDRANT_URL phải dùng địa chỉ service nội bộ đã khai báo.",
        )

    release = _mapping(manifest.get("release"))
    release_environment = {
        "RELEASE_IDENTIFIER": release.get("release_id"),
        "RELEASE_GIT_TAG": release.get("tag_recommendation"),
        "RELEASE_ALEMBIC_REVISION": release.get("alembic_revision"),
    }
    for name, expected in release_environment.items():
        if environment.get(name) and environment.get(name) != expected:
            _add(
                findings,
                "release_environment_mismatch",
                f"environment.{name}",
                f"{name} không khớp release manifest.",
            )
    release_commit = environment.get("RELEASE_GIT_COMMIT")
    if release_commit and not _COMMIT_RE.fullmatch(release_commit):
        _add(
            findings,
            "release_environment_commit_invalid",
            "environment.RELEASE_GIT_COMMIT",
            "RELEASE_GIT_COMMIT phải là full 40-character Git SHA.",
        )

    images = _mapping(manifest.get("images"))
    for name, expected in {
        "PILOT_APP_IMAGE": images.get("application"),
        "PILOT_FRONTEND_IMAGE": images.get("frontend"),
    }.items():
        if environment.get(name) and environment.get(name) != expected:
            _add(
                findings,
                "image_environment_mismatch",
                f"environment.{name}",
                f"{name} không khớp image reference trong manifest.",
            )

    runtime_sections = {
        "worker": {
            "WORKER_POLL_INTERVAL_SECONDS": "poll_interval_seconds",
            "WORKER_HEARTBEAT_INTERVAL_SECONDS": "heartbeat_interval_seconds",
            "WORKER_HEARTBEAT_STALE_SECONDS": "heartbeat_stale_seconds",
            "WORKER_OUTBOX_LEASE_SECONDS": "outbox_lease_seconds",
            "WORKER_BATCH_SIZE": "batch_size",
        },
        "database": {
            "DATABASE_CONNECT_TIMEOUT_SECONDS": "connect_timeout_seconds",
            "DATABASE_POOL_SIZE": "pool_size",
            "DATABASE_MAX_OVERFLOW": "max_overflow",
            "DATABASE_POOL_TIMEOUT_SECONDS": "pool_timeout_seconds",
            "DATABASE_STATEMENT_TIMEOUT_SECONDS": "statement_timeout_seconds",
            "DATABASE_LOCK_TIMEOUT_SECONDS": "lock_timeout_seconds",
            "DATABASE_IDLE_TRANSACTION_TIMEOUT_SECONDS": ("idle_transaction_timeout_seconds"),
        },
        "operational_alerts": {
            "OPERATIONAL_OUTBOX_AGE_ALERT_SECONDS": "outbox_oldest_age_seconds",
            "OPERATIONAL_REPEATED_JOB_FAILURE_THRESHOLD": ("repeated_job_failure_count"),
            "OPERATIONAL_ANALYTICS_STALE_SECONDS": "analytics_stale_seconds",
            "OPERATIONAL_BACKUP_OVERDUE_SECONDS": "backup_overdue_seconds",
            "OPERATIONAL_DISK_WARNING_FREE_PERCENT": "disk_warning_free_percent",
            "OPERATIONAL_DISK_CRITICAL_FREE_PERCENT": "disk_critical_free_percent",
        },
    }
    for section_name, value_map in runtime_sections.items():
        section = _mapping(manifest.get(section_name))
        for environment_name, setting_name in value_map.items():
            _validate_integer_environment_match(
                environment,
                environment_name,
                section.get(setting_name),
                findings,
            )

    bounded_integers = {
        "ACCESS_TOKEN_LIFETIME_MINUTES": (1, 60),
        "REFRESH_SESSION_LIFETIME_DAYS": (1, 30),
        "LOGIN_RATE_LIMIT_ATTEMPTS": (1, 100),
        "LOGIN_RATE_LIMIT_WINDOW_SECONDS": (10, 3600),
        "ATTACHMENT_MAX_SIZE_BYTES": (1024, 50 * 1024 * 1024),
    }
    for name, (minimum, maximum) in bounded_integers.items():
        _validate_integer_environment_range(
            environment,
            name,
            minimum,
            maximum,
            findings,
        )

    for name, allowed in {
        "ATTACHMENT_STORAGE_BACKEND": {"local"},
        "AUTH_COOKIE_SAMESITE": {"lax", "strict", "none"},
        "LOG_LEVEL": {"DEBUG", "INFO", "WARNING", "ERROR"},
    }.items():
        if environment.get(name) and environment[name] not in allowed:
            _add(
                findings,
                "environment_value_unsupported",
                f"environment.{name}",
                f"{name} có giá trị ngoài allow-list.",
            )
    for name in ("REFRESH_COOKIE_NAME", "CSRF_COOKIE_NAME"):
        value = environment.get(name, "")
        if value and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
            _add(
                findings,
                "cookie_name_invalid",
                f"environment.{name}",
                f"{name} không phải tên cookie an toàn.",
            )

    ports = _list_of_mappings(manifest.get("ports"))
    for port in ports:
        environment_name = port.get("host_port_environment")
        if isinstance(environment_name, str):
            _validate_integer_environment_match(
                environment,
                environment_name,
                port.get("host_port"),
                findings,
            )
        bind_name = port.get("bind_address_environment")
        bind_value = environment.get(str(bind_name), "")
        if bind_value and (
            any(character.isspace() for character in bind_value)
            or "/" in bind_value
            or "\\" in bind_value
            or "://" in bind_value
        ):
            _add(
                findings,
                "bind_address_invalid",
                f"environment.{bind_name}",
                f"{bind_name} không phải bind address hợp lệ.",
            )

    host_identifier = environment.get("PILOT_HOST_IDENTIFIER", "")
    if host_identifier and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}", host_identifier):
        _add(
            findings,
            "pilot_host_identifier_invalid",
            "environment.PILOT_HOST_IDENTIFIER",
            "PILOT_HOST_IDENTIFIER phải là opaque identifier, không phải đường dẫn.",
        )

    storage = _mapping(manifest.get("storage"))
    roots = _mapping(storage.get("allowed_roots"))
    paths = _mapping(storage.get("paths"))
    resolved_roots: dict[str, Path] = {}
    for root_name, root_value in roots.items():
        root_contract = _mapping(root_value)
        environment_name = root_contract.get("environment_variable")
        value = environment.get(str(environment_name), "")
        if not value:
            continue
        candidate = Path(value)
        try:
            resolved = candidate.resolve()
            valid = candidate.is_absolute() and not (
                resolved == repository_root or resolved.is_relative_to(repository_root)
            )
        except (OSError, RuntimeError):
            valid = False
            resolved = candidate
        if not valid:
            _add(
                findings,
                "environment_root_containment_violation",
                f"environment.{environment_name}",
                f"{environment_name} phải là absolute root nằm ngoài repository.",
            )
            continue
        resolved_roots[str(root_name)] = resolved

    data_root = resolved_roots.get("data")
    backup_root = resolved_roots.get("backup")
    if (
        data_root is not None
        and backup_root is not None
        and (
            data_root == backup_root
            or data_root.is_relative_to(backup_root)
            or backup_root.is_relative_to(data_root)
        )
    ):
        _add(
            findings,
            "storage_roots_overlap",
            "environment.PILOT_BACKUP_ROOT",
            "Pilot data root và backup root phải tách biệt, không lồng nhau.",
        )

    for path_name, path_value in paths.items():
        row = _mapping(path_value)
        root = resolved_roots.get(str(row.get("root")))
        relative_path = row.get("relative_path")
        if root is not None and _safe_relative_path(relative_path):
            target = (root / str(relative_path)).resolve()
            if not target.is_relative_to(root):
                _add(
                    findings,
                    "environment_path_containment_violation",
                    f"manifest.storage.paths.{path_name}",
                    "Configured host path thoát khỏi allowed root.",
                )
        configuration_name = row.get("configuration_environment")
        if isinstance(configuration_name, str):
            configured_path = environment.get(configuration_name)
            if configured_path and configured_path != row.get("container_path"):
                _add(
                    findings,
                    "container_path_environment_mismatch",
                    f"environment.{configuration_name}",
                    f"{configuration_name} không khớp container storage path.",
                )
    backup_row = _mapping(paths.get("backups"))
    _validate_integer_environment_match(
        environment,
        "PILOT_BACKUP_RETENTION_COUNT",
        backup_row.get("retention_keep_count"),
        findings,
    )


def _validate_release_observations(
    manifest: dict[str, Any],
    *,
    environment: Mapping[str, str] | None,
    actual_commit: str | None,
    actual_tag: str | None,
    actual_tag_target_commit: str | None,
    actual_migration_revision: str | None,
    findings: list[Finding],
) -> None:
    release = _mapping(manifest.get("release"))
    if actual_commit is not None and not _COMMIT_RE.fullmatch(actual_commit):
        _add(
            findings,
            "release_commit_observation_invalid",
            "release_observation.commit",
            "Observed Git commit phải là full 40-character SHA.",
        )
    environment_commit = environment.get("RELEASE_GIT_COMMIT") if environment is not None else None
    if (
        actual_commit is not None
        and environment_commit is not None
        and not _git_identity_matches(environment_commit, actual_commit)
    ):
        _add(
            findings,
            "release_environment_commit_mismatch",
            "release_observation.commit",
            "Runtime release commit không khớp exact tagged checkout.",
        )
    if actual_tag is not None and actual_tag != release.get("tag_recommendation"):
        _add(
            findings,
            "release_tag_mismatch",
            "release_observation.tag",
            "Deployed Git tag không khớp tag recommendation.",
        )
    if actual_tag_target_commit is not None and not _COMMIT_RE.fullmatch(actual_tag_target_commit):
        _add(
            findings,
            "release_tag_target_observation_invalid",
            "release_observation.tag_target_commit",
            "Observed Git tag target phải là full 40-character SHA.",
        )
    if (
        actual_commit is not None
        and actual_tag_target_commit is not None
        and not _git_identity_matches(actual_tag_target_commit, actual_commit)
    ):
        _add(
            findings,
            "release_tag_target_commit_mismatch",
            "release_observation.tag_target_commit",
            "Observed exact tag target không khớp checkout commit.",
        )
    if actual_migration_revision is not None and actual_migration_revision != release.get(
        "alembic_revision"
    ):
        _add(
            findings,
            "migration_revision_mismatch",
            "release_observation.migration",
            "Alembic revision đang chạy không khớp release contract.",
        )


def _validate_service_reachability(
    manifest: dict[str, Any],
    probe: ServiceProbe,
    findings: list[Finding],
) -> None:
    for service in _list_of_mappings(manifest.get("services")):
        if service.get("required") is not True:
            continue
        name = str(service.get("name", "unknown"))
        try:
            reachable = probe(service) is True
        except Exception:  # The report must not echo probe exception or connection data.
            reachable = False
        if not reachable:
            _add(
                findings,
                "required_service_unreachable",
                f"service_probe.{name}",
                f"Service bắt buộc chưa reachable: {name}.",
            )


def _validate_ownership(document: dict[str, Any], findings: list[Finding]) -> None:
    _require_keys(
        document,
        {
            "schema_version",
            "record_kind",
            "record_status",
            "assignments",
            "incident_communication",
            "support_coverage",
            "escalation_path",
        },
        "ownership",
        findings,
    )
    if not _versioned(document):
        _add(
            findings,
            "invalid_schema_version",
            "ownership",
            "Ownership record phải có schema_version.",
        )
    if document.get("record_kind") != "internal_pilot_operational_ownership":
        _add(
            findings,
            "invalid_ownership_record_kind",
            "ownership.record_kind",
            "Ownership record kind không khớp internal-pilot contract.",
        )
    if document.get("record_status") != "approved":
        _add(
            findings,
            "ownership_record_not_approved",
            "ownership.record_status",
            "Ownership record chưa được approved.",
        )
    assignments = _mapping(document.get("assignments"))
    for key in REQUIRED_OWNERS:
        assignment = _mapping(assignments.get(key))
        if not assignment:
            _add(
                findings,
                "ownership_assignment_missing",
                f"ownership.assignments.{key}",
                f"Thiếu ownership assignment: {key}.",
            )
            continue
        if (
            assignment.get("status") != "assigned"
            or not _non_placeholder_text(assignment.get("assigned_role"))
            or not _non_placeholder_text(assignment.get("approved_internal_channel"))
        ):
            _add(
                findings,
                "ownership_placeholder",
                f"ownership.assignments.{key}",
                f"Ownership {key} chưa được gán rõ ràng.",
            )
        if assignment.get("status") == "assigned" and not _valid_evidence_links(
            assignment.get("approval_evidence_links")
        ):
            _add(
                findings,
                "ownership_evidence_missing",
                f"ownership.assignments.{key}",
                f"Ownership {key} thiếu approval evidence link.",
            )

    incident = _mapping(document.get("incident_communication"))
    if (
        incident.get("status") != "configured"
        or not _non_placeholder_text(incident.get("primary_internal_channel"))
        or not _non_placeholder_text(incident.get("fallback_internal_channel"))
    ):
        _add(
            findings,
            "incident_path_missing",
            "ownership.incident_communication",
            "Incident communication path chưa được cấu hình.",
        )
    elif not _valid_evidence_links(incident.get("approval_evidence_links")):
        _add(
            findings,
            "incident_path_evidence_missing",
            "ownership.incident_communication",
            "Incident communication path thiếu approval evidence link.",
        )

    coverage = _mapping(document.get("support_coverage"))
    if (
        coverage.get("status") != "confirmed"
        or not _non_placeholder_text(coverage.get("support_hours"))
        or not _non_placeholder_text(coverage.get("after_hours_assumption"))
        or not _non_placeholder_text(coverage.get("timezone"))
    ):
        _add(
            findings,
            "support_coverage_unconfirmed",
            "ownership.support_coverage",
            "Support hours hoặc coverage assumptions chưa được xác nhận.",
        )
    elif not _valid_iana_timezone(coverage.get("timezone")):
        _add(
            findings,
            "support_timezone_invalid",
            "ownership.support_coverage.timezone",
            "Support coverage phải dùng timezone IANA hợp lệ.",
        )
    elif not _valid_evidence_links(coverage.get("approval_evidence_links")):
        _add(
            findings,
            "support_coverage_evidence_missing",
            "ownership.support_coverage",
            "Support coverage thiếu approval evidence link.",
        )

    escalation = _mapping(document.get("escalation_path"))
    steps = _list_of_mappings(
        escalation.get("steps"),
        findings=findings,
        scope="ownership.escalation_path.steps",
    )
    if escalation.get("status") != "configured" or len(steps) < 2:
        _add(
            findings,
            "escalation_path_missing",
            "ownership.escalation_path",
            "Escalation path chưa được cấu hình đầy đủ.",
        )
    elif not _valid_evidence_links(escalation.get("approval_evidence_links")):
        _add(
            findings,
            "escalation_path_evidence_missing",
            "ownership.escalation_path",
            "Escalation path thiếu approval evidence link.",
        )
    seen_orders: set[int] = set()
    seen_owner_refs: set[str] = set()
    for step in steps:
        order = step.get("order")
        owner_ref = step.get("owner_ref")
        if (
            type(order) is not int
            or order < 1
            or owner_ref not in REQUIRED_OWNERS
            or not _non_placeholder_text(step.get("channel_ref"))
        ):
            _add(
                findings,
                "escalation_step_invalid",
                "ownership.escalation_path",
                "Escalation step phải tham chiếu owner và channel hợp lệ.",
            )
        if (
            isinstance(order, int)
            and not isinstance(order, bool)
            and isinstance(owner_ref, str)
            and (order in seen_orders or owner_ref in seen_owner_refs)
        ):
            _add(
                findings,
                "duplicate_escalation_step",
                "ownership.escalation_path",
                "Escalation path không được lặp order hoặc owner.",
            )
        if isinstance(order, int) and not isinstance(order, bool):
            seen_orders.add(order)
        if isinstance(owner_ref, str):
            seen_owner_refs.add(owner_ref)


def _validate_limitations(document: dict[str, Any], findings: list[Finding]) -> None:
    _require_keys(
        document,
        {"schema_version", "record_kind", "record_status", "limitations"},
        "limitations",
        findings,
    )
    if not _versioned(document):
        _add(
            findings,
            "invalid_schema_version",
            "limitations",
            "Known-limitations record phải có schema_version.",
        )
    if document.get("record_kind") != "internal_pilot_known_limitations_acceptance":
        _add(
            findings,
            "invalid_limitations_record_kind",
            "limitations.record_kind",
            "Known-limitations record kind không khớp internal-pilot contract.",
        )
    if document.get("record_status") != "accepted":
        _add(
            findings,
            "limitations_record_not_accepted",
            "limitations.record_status",
            "Known-limitations record chưa được accepted.",
        )
    rows = _list_of_mappings(
        document.get("limitations"),
        findings=findings,
        scope="limitations.limitations",
    )
    ids: set[str] = set()
    for row in rows:
        limitation_id = row.get("id")
        if not _non_placeholder_text(limitation_id):
            _add(
                findings,
                "limitation_id_missing",
                "limitations.limitations",
                "Mỗi limitation phải có id.",
            )
            continue
        if limitation_id in ids:
            _add(
                findings,
                "duplicate_limitation",
                f"limitations.{limitation_id}",
                "Known limitation bị khai báo trùng.",
            )
        ids.add(limitation_id)
        _require_keys(
            row,
            {
                "critical",
                "description",
                "operational_consequence",
                "mitigation",
                "owner_role",
                "acceptance_status",
                "review_trigger",
            },
            f"limitations.{limitation_id}",
            findings,
        )
        if type(row.get("critical")) is not bool:
            _add(
                findings,
                "limitation_criticality_invalid",
                f"limitations.{limitation_id}.critical",
                "Criticality của limitation phải là boolean.",
            )
        elif limitation_id in REQUIRED_LIMITATIONS and row.get("critical") is not True:
            _add(
                findings,
                "required_limitation_weakened",
                f"limitations.{limitation_id}.critical",
                "Known limitation bắt buộc không được hạ cấp khỏi critical.",
            )
        for key in (
            "description",
            "operational_consequence",
            "mitigation",
            "review_trigger",
        ):
            if not _non_placeholder_text(row.get(key)):
                _add(
                    findings,
                    "limitation_field_missing",
                    f"limitations.{limitation_id}.{key}",
                    "Limitation thiếu mô tả, hậu quả, mitigation hoặc review trigger.",
                )
        if not _non_placeholder_text(row.get("owner_role")):
            _add(
                findings,
                "limitation_owner_placeholder",
                f"limitations.{limitation_id}.owner_role",
                f"Limitation {limitation_id} chưa có owner role.",
            )
        status = row.get("acceptance_status")
        if not isinstance(status, str) or status not in {
            "accepted",
            "pending",
            "rejected",
        }:
            _add(
                findings,
                "limitation_acceptance_invalid",
                f"limitations.{limitation_id}.acceptance_status",
                "Acceptance status phải là accepted, pending hoặc rejected.",
            )
        if row.get("critical") is True and status != "accepted":
            _add(
                findings,
                "critical_limitation_unaccepted",
                f"limitations.{limitation_id}",
                f"Critical limitation chưa được chấp nhận: {limitation_id}.",
            )
        if status == "accepted":
            if (
                not _non_placeholder_text(row.get("accepted_by_role"))
                or not _valid_utc_timestamp(row.get("accepted_at_utc"))
                or not _valid_evidence_links(row.get("acceptance_evidence_links"))
            ):
                _add(
                    findings,
                    "limitation_acceptance_evidence_missing",
                    f"limitations.{limitation_id}",
                    "Acceptance phải có role, UTC timestamp và evidence link.",
                )
    for limitation_id in sorted(REQUIRED_LIMITATIONS - ids):
        _add(
            findings,
            "required_limitation_missing",
            f"limitations.{limitation_id}",
            f"Thiếu known limitation bắt buộc: {limitation_id}.",
        )


def _validate_release_record(
    record: dict[str, Any],
    manifest: dict[str, Any],
    ownership: dict[str, Any],
    limitations: dict[str, Any],
    digest: str,
    actual_commit: str | None,
    findings: list[Finding],
) -> None:
    _require_keys(
        record,
        {
            "schema_version",
            "record_kind",
            "record_status",
            "release",
            "application_versions",
            "database_version",
            "enabled_jobs",
            "configured_alert_thresholds",
            "backup_validation",
            "restore_validation",
            "load_and_soak_profiles",
            "attachment_restore",
            "secret_rotation",
            "open_risks",
            "ownership_status",
            "incident_contact_status",
            "known_limitations_acceptance_status",
            "rollback",
            "gates",
            "conditions",
            "final_decision",
            "evidence_links",
            "production_readiness_claim",
        },
        "release_record",
        findings,
    )
    if not _versioned(record):
        _add(
            findings,
            "invalid_schema_version",
            "release_record",
            "Release record phải có schema_version.",
        )
    if record.get("record_kind") != "internal_pilot_release_record":
        _add(
            findings,
            "invalid_release_record_kind",
            "release_record.record_kind",
            "Release record kind không khớp internal-pilot contract.",
        )
    if record.get("record_status") != "final":
        _add(
            findings,
            "release_record_not_final",
            "release_record.record_status",
            "Pilot release record vẫn là draft.",
        )
    elif not _valid_utc_timestamp(record.get("generated_at_utc")):
        _add(
            findings,
            "release_timestamp_missing",
            "release_record.generated_at_utc",
            "Final release record phải có UTC generation timestamp.",
        )
    if record.get("production_readiness_claim") is not False:
        _add(
            findings,
            "production_readiness_claim_forbidden",
            "release_record",
            "Release record internal pilot không được tuyên bố production readiness.",
        )

    manifest_release = _mapping(manifest.get("release"))
    recorded_release = _mapping(record.get("release"))
    expected_release_values = {
        "release_name": manifest_release.get("release_id"),
        "git_tag_recommendation": manifest_release.get("tag_recommendation"),
        "migration_revision": manifest_release.get("alembic_revision"),
        "deployment_manifest_sha256": digest,
    }
    for key, expected in expected_release_values.items():
        if recorded_release.get(key) != expected:
            _add(
                findings,
                "release_record_identity_mismatch",
                f"release_record.release.{key}",
                f"Release record field {key} không khớp deployment manifest.",
            )
    recorded_commit = recorded_release.get("git_commit")
    if _is_placeholder(recorded_commit):
        _add(
            findings,
            "release_record_commit_pending",
            "release_record.release.git_commit",
            "Release record chưa được checkpoint bằng full Git SHA.",
        )
    elif not isinstance(recorded_commit, str) or not _COMMIT_RE.fullmatch(recorded_commit):
        _add(
            findings,
            "release_record_commit_invalid",
            "release_record.release.git_commit",
            "Release record commit phải là full 40-character Git SHA.",
        )
    elif actual_commit is not None and not _git_identity_matches(recorded_commit, actual_commit):
        _add(
            findings,
            "release_record_commit_mismatch",
            "release_record.release.git_commit",
            "Release record commit không khớp observed exact tag target.",
        )
    elif record.get("record_status") == "final" and actual_commit is None:
        _add(
            findings,
            "release_commit_observation_missing",
            "release_observation.commit",
            "Final release validation cần observed exact tag-target commit.",
        )

    if record.get("application_versions") != manifest.get("versions"):
        _add(
            findings,
            "release_version_mismatch",
            "release_record.application_versions",
            "Application versions không khớp deployment manifest.",
        )
    if record.get("database_version") != _mapping(manifest.get("versions")).get("postgresql"):
        _add(
            findings,
            "database_version_mismatch",
            "release_record.database_version",
            "Database version không khớp deployment manifest.",
        )
    expected_jobs = sorted(
        str(job.get("job_type"))
        for job in _list_of_mappings(manifest.get("scheduled_jobs"))
        if job.get("enabled") is True
    )
    if record.get("enabled_jobs") != expected_jobs:
        _add(
            findings,
            "enabled_jobs_mismatch",
            "release_record.enabled_jobs",
            "Enabled jobs không khớp deployment manifest.",
        )
    if record.get("configured_alert_thresholds") != manifest.get("operational_alerts"):
        _add(
            findings,
            "alert_threshold_mismatch",
            "release_record.configured_alert_thresholds",
            "Alert thresholds không khớp deployment manifest.",
        )

    for section_name in (
        "backup_validation",
        "restore_validation",
        "attachment_restore",
        "secret_rotation",
    ):
        section = _mapping(record.get(section_name))
        if section.get("status") == "passed":
            if not _valid_utc_timestamp(
                section.get("validated_at_utc")
            ) or not _valid_evidence_links(section.get("evidence_links")):
                _add(
                    findings,
                    "validation_evidence_missing",
                    f"release_record.{section_name}",
                    f"{section_name} passed nhưng thiếu timestamp hoặc evidence.",
                )
        elif section.get("status") != "passed":
            _add(
                findings,
                "release_validation_open",
                f"release_record.{section_name}",
                f"{section_name} chưa có kết quả passed cho pilot.",
            )

    load_profiles = _mapping(record.get("load_and_soak_profiles"))
    if (
        load_profiles.get("status") != "passed"
        or not isinstance(load_profiles.get("summaries"), list)
        or not load_profiles.get("summaries")
        or not _valid_evidence_links(load_profiles.get("evidence_links"))
    ):
        _add(
            findings,
            "load_and_soak_evidence_open",
            "release_record.load_and_soak_profiles",
            "Load và soak profiles chưa có summary cùng evidence passed.",
        )

    gates = _list_of_mappings(
        record.get("gates"),
        findings=findings,
        scope="release_record.gates",
    )
    gate_ids = _check_unique_names(gates, "id", "gate", findings)
    for gate_id in sorted(CRITICAL_GATES - gate_ids):
        _add(
            findings,
            "critical_gate_missing",
            f"release_record.gates.{gate_id}",
            f"Thiếu critical gate: {gate_id}.",
        )
    for gate in gates:
        gate_id = str(gate.get("id", "unknown"))
        if gate_id in CRITICAL_GATES and gate.get("critical") is not True:
            _add(
                findings,
                "critical_gate_weakened",
                f"release_record.gates.{gate_id}",
                "Critical gate không được hạ cấp.",
            )
        if gate.get("status") not in {"passed", "failed", "unverified"}:
            _add(
                findings,
                "gate_status_invalid",
                f"release_record.gates.{gate_id}",
                "Gate status phải là passed, failed hoặc unverified.",
            )
        if gate.get("status") == "passed" and not _valid_evidence_links(gate.get("evidence_links")):
            _add(
                findings,
                "gate_evidence_missing",
                f"release_record.gates.{gate_id}",
                "Gate passed phải có evidence link.",
            )
        if gate_id in CRITICAL_GATES and gate.get("status") != "passed":
            _add(
                findings,
                "critical_gate_open",
                f"release_record.gates.{gate_id}",
                f"Critical gate chưa passed: {gate_id}.",
            )

    risks = _list_of_mappings(
        record.get("open_risks"),
        findings=findings,
        scope="release_record.open_risks",
    )
    risk_ids: set[str] = set()
    for risk in risks:
        risk_id = risk.get("id")
        if not _non_placeholder_text(risk_id):
            _add(
                findings,
                "risk_id_missing",
                "release_record.open_risks",
                "Mỗi risk phải có id không phải placeholder.",
            )
        elif risk_id in risk_ids:
            _add(
                findings,
                "duplicate_risk",
                f"release_record.open_risks.{risk_id}",
                "Risk không được khai báo trùng.",
            )
        else:
            risk_ids.add(risk_id)
        status = risk.get("status")
        if not isinstance(status, str) or status not in ALLOWED_RISK_STATUSES:
            _add(
                findings,
                "risk_status_invalid",
                f"release_record.open_risks.{risk_id}",
                "Danh sách open_risks chỉ chấp nhận status open.",
            )
        severity = risk.get("severity")
        if not isinstance(severity, str) or severity not in ALLOWED_RISK_SEVERITIES:
            _add(
                findings,
                "risk_severity_invalid",
                f"release_record.open_risks.{risk_id}",
                "Risk severity nằm ngoài allow-list.",
            )
        category = risk.get("category")
        if not isinstance(category, str) or category not in ALLOWED_RISK_CATEGORIES:
            _add(
                findings,
                "risk_category_invalid",
                f"release_record.open_risks.{risk_id}",
                "Risk category nằm ngoài allow-list.",
            )

    if not _valid_evidence_links(record.get("evidence_links")):
        _add(
            findings,
            "release_evidence_links_missing",
            "release_record.evidence_links",
            "Release record phải có ít nhất một evidence-document link.",
        )
    if record.get("known_limitations_acceptance_status") != (
        "accepted" if _critical_limitations_accepted(limitations) else "pending"
    ):
        _add(
            findings,
            "limitation_summary_mismatch",
            "release_record.known_limitations_acceptance_status",
            "Known-limitations summary không khớp acceptance record.",
        )
    expected_incident = _mapping(ownership.get("incident_communication")).get("status")
    if record.get("incident_contact_status") != expected_incident:
        _add(
            findings,
            "incident_summary_mismatch",
            "release_record.incident_contact_status",
            "Incident-contact summary không khớp ownership record.",
        )
    assignments = _mapping(ownership.get("assignments"))
    expected_owner_status = {
        key: _mapping(assignments.get(key)).get("status", "unassigned") for key in REQUIRED_OWNERS
    }
    if record.get("ownership_status") != expected_owner_status:
        _add(
            findings,
            "ownership_summary_mismatch",
            "release_record.ownership_status",
            "Ownership summary không khớp operational ownership record.",
        )
    rollback_manifest = _mapping(manifest.get("rollback"))
    rollback_record = _mapping(record.get("rollback"))
    for key in (
        "target_release_id",
        "target_git_tag",
        "target_git_commit",
        "target_alembic_revision",
        "mode",
    ):
        if rollback_record.get(key) != rollback_manifest.get(key):
            _add(
                findings,
                "rollback_metadata_mismatch",
                f"release_record.rollback.{key}",
                "Rollback metadata không khớp deployment manifest.",
            )


def _validate_final_release_observation_presence(
    *,
    environment: Mapping[str, str] | None,
    actual_tag: str | None,
    actual_tag_target_commit: str | None,
    actual_migration_revision: str | None,
    findings: list[Finding],
) -> None:
    if environment is None:
        _add(
            findings,
            "release_environment_observation_missing",
            "release_observation.environment",
            "Final release validation cần protected environment observation.",
        )
    if actual_tag is None:
        _add(
            findings,
            "release_tag_observation_missing",
            "release_observation.tag",
            "Final release validation cần observed exact Git tag.",
        )
    if actual_tag_target_commit is None:
        _add(
            findings,
            "release_tag_target_observation_missing",
            "release_observation.tag_target_commit",
            "Final release validation cần observed exact Git tag-target commit.",
        )
    if actual_migration_revision is None:
        _add(
            findings,
            "migration_observation_missing",
            "release_observation.migration",
            "Final release validation cần observed Alembic revision.",
        )


def _validate_safe_document(
    document: dict[str, Any],
    scope: str,
    findings: list[Finding],
) -> None:
    def visit(value: Any, location: str, key: str | None = None) -> None:
        normalized_key = (key or "").casefold()
        if normalized_key in _SENSITIVE_VALUE_KEYS and value not in (None, False, True, ""):
            _add(
                findings,
                "secret_or_personal_value_committed",
                location,
                "Contract không được chứa secret, credential hoặc personal contact value.",
            )
            return
        if isinstance(value, Mapping):
            for child_key, child_value in value.items():
                visit(child_value, f"{location}.{child_key}", str(child_key))
        elif isinstance(value, list):
            for index, child_value in enumerate(value):
                visit(child_value, f"{location}[{index}]")
        elif isinstance(value, str):
            if _url_contains_credentials(value):
                _add(
                    findings,
                    "credential_url_committed",
                    location,
                    "Contract không được chứa URL có credential.",
                )
            if _looks_like_local_absolute_path(value) and normalized_key != "container_path":
                _add(
                    findings,
                    "absolute_local_path_committed",
                    location,
                    "Contract không được chứa absolute local path.",
                )
            if _EMAIL_RE.search(value) or _PHONE_RE.search(value):
                _add(
                    findings,
                    "personal_contact_committed",
                    location,
                    "Contract không được chứa email hoặc số điện thoại cá nhân.",
                )

    visit(document, scope)


def _ownership_ready(document: dict[str, Any]) -> bool:
    if (
        document.get("record_kind") != "internal_pilot_operational_ownership"
        or document.get("record_status") != "approved"
    ):
        return False
    assignments = _mapping(document.get("assignments"))
    for key in REQUIRED_OWNERS:
        assignment = _mapping(assignments.get(key))
        if (
            assignment.get("status") != "assigned"
            or not _non_placeholder_text(assignment.get("assigned_role"))
            or not _non_placeholder_text(assignment.get("approved_internal_channel"))
            or not _valid_evidence_links(assignment.get("approval_evidence_links"))
        ):
            return False
    incident = _mapping(document.get("incident_communication"))
    if (
        incident.get("status") != "configured"
        or not _non_placeholder_text(incident.get("primary_internal_channel"))
        or not _non_placeholder_text(incident.get("fallback_internal_channel"))
        or not _valid_evidence_links(incident.get("approval_evidence_links"))
    ):
        return False
    coverage = _mapping(document.get("support_coverage"))
    if (
        coverage.get("status") != "confirmed"
        or not _non_placeholder_text(coverage.get("support_hours"))
        or not _non_placeholder_text(coverage.get("after_hours_assumption"))
        or not _valid_iana_timezone(coverage.get("timezone"))
        or not _valid_evidence_links(coverage.get("approval_evidence_links"))
    ):
        return False
    escalation = _mapping(document.get("escalation_path"))
    raw_steps = escalation.get("steps")
    if not isinstance(raw_steps, list) or any(not isinstance(step, Mapping) for step in raw_steps):
        return False
    steps = [dict(step) for step in raw_steps]
    orders = [step.get("order") for step in steps]
    owner_refs = [step.get("owner_ref") for step in steps]
    return (
        escalation.get("status") == "configured"
        and _valid_evidence_links(escalation.get("approval_evidence_links"))
        and len(steps) >= 2
        and all(type(order) is int and order >= 1 for order in orders)
        and len(set(orders)) == len(orders)
        and all(isinstance(owner_ref, str) for owner_ref in owner_refs)
        and len(set(owner_refs)) == len(owner_refs)
        and all(
            step.get("owner_ref") in REQUIRED_OWNERS
            and _non_placeholder_text(step.get("channel_ref"))
            for step in steps
        )
    )


def _critical_limitations_accepted(document: dict[str, Any]) -> bool:
    if (
        document.get("record_kind") != "internal_pilot_known_limitations_acceptance"
        or document.get("record_status") != "accepted"
    ):
        return False
    raw_rows = document.get("limitations")
    if not isinstance(raw_rows, list) or any(not isinstance(row, Mapping) for row in raw_rows):
        return False
    rows = [dict(row) for row in raw_rows]
    row_ids = [row.get("id") for row in rows]
    if any(not _non_placeholder_text(row_id) for row_id in row_ids):
        return False
    ids = set(row_ids)
    if len(ids) != len(rows):
        return False
    if not REQUIRED_LIMITATIONS.issubset(ids):
        return False
    for row in rows:
        limitation_id = row.get("id")
        is_required = limitation_id in REQUIRED_LIMITATIONS
        if is_required and row.get("critical") is not True:
            return False
        status = row.get("acceptance_status")
        if not isinstance(status, str) or status not in {
            "accepted",
            "pending",
            "rejected",
        }:
            return False
        if row.get("critical") is False and not is_required:
            continue
        if row.get("critical") is not True:
            return False
        if (
            row.get("acceptance_status") != "accepted"
            or not _non_placeholder_text(row.get("owner_role"))
            or not _non_placeholder_text(row.get("accepted_by_role"))
            or not _valid_utc_timestamp(row.get("accepted_at_utc"))
            or not _valid_evidence_links(row.get("acceptance_evidence_links"))
            or not _non_placeholder_text(row.get("review_trigger"))
        ):
            return False
    return True


def _condition_is_bounded(condition: Mapping[str, Any]) -> bool:
    return all(
        (
            _non_placeholder_text(condition.get("description")),
            _non_placeholder_text(condition.get("owner_role")),
            _non_placeholder_text(condition.get("mitigation")),
            _non_placeholder_text(condition.get("review_trigger")),
            _non_placeholder_text(condition.get("pilot_scope_limit")),
            _valid_evidence_links(condition.get("evidence_links")),
        )
    )


def _valid_evidence_links(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for link in value:
        if not isinstance(link, str) or not link.strip() or _is_placeholder(link):
            return False
        if _looks_like_local_absolute_path(link) or _url_contains_credentials(link):
            return False
    return True


def _valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def _safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return False
    normalized = value.replace("\\", "/")
    if (
        normalized.startswith("/")
        or normalized.startswith("//")
        or _WINDOWS_ABSOLUTE_RE.match(value)
        or "://" in normalized
    ):
        return False
    parts = PurePosixPath(normalized).parts
    return ".." not in parts and all(part not in {"", "."} for part in parts)


def _safe_container_path(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or "\x00" in value
    ):
        return False
    parts = PurePosixPath(value).parts
    return ".." not in parts and all(part != "." for part in parts)


def _safe_service_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


def _url_contains_credentials(value: str) -> bool:
    if "://" not in value:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return True
    return parsed.username is not None or parsed.password is not None


def _looks_like_local_absolute_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return bool(
        _WINDOWS_ABSOLUTE_RE.match(value)
        or value.startswith("\\\\")
        or normalized.startswith(
            (
                "/Users/",
                "/home/",
                "/tmp/",
                "/var/",
                "/etc/",
                "/opt/",
                "/srv/",
                "/mnt/",
                "/app/",
                "/root/",
            )
        )
    )


def _git_identity_matches(expected: str, actual: str) -> bool:
    expected_normalized = expected.strip().casefold()
    actual_normalized = actual.strip().casefold()
    return bool(
        _COMMIT_RE.fullmatch(expected_normalized)
        and _COMMIT_RE.fullmatch(actual_normalized)
        and expected_normalized == actual_normalized
    )


def _validate_integer_environment_match(
    environment: Mapping[str, str],
    name: str,
    expected: Any,
    findings: list[Finding],
) -> None:
    value = environment.get(name)
    if not value:
        return
    try:
        actual = int(value)
    except ValueError:
        actual = None
    if actual != expected:
        _add(
            findings,
            "runtime_environment_mismatch",
            f"environment.{name}",
            f"{name} phải là số nguyên khớp deployment manifest.",
        )


def _validate_integer_environment_range(
    environment: Mapping[str, str],
    name: str,
    minimum: int,
    maximum: int,
    findings: list[Finding],
) -> None:
    value = environment.get(name)
    if not value:
        return
    try:
        actual = int(value)
    except ValueError:
        actual = None
    if actual is None or not minimum <= actual <= maximum:
        _add(
            findings,
            "runtime_environment_out_of_range",
            f"environment.{name}",
            f"{name} phải là số nguyên nằm trong giới hạn pilot.",
        )


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().casefold() in {"1", "true", "yes", "on"})


def _is_placeholder(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return True
    normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
    return any(marker in normalized for marker in _PLACEHOLDER_MARKERS)


def _non_placeholder_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _is_placeholder(value)


def _valid_iana_timezone(value: Any) -> bool:
    if not _non_placeholder_text(value):
        return False
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def _versioned(document: Mapping[str, Any]) -> bool:
    value = document.get("schema_version")
    return (
        isinstance(value, (str, int)) and not isinstance(value, bool) and bool(str(value).strip())
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_of_mappings(
    value: Any,
    *,
    findings: list[Finding] | None = None,
    scope: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            rows.append(dict(item))
        elif findings is not None and scope is not None:
            _add(
                findings,
                "list_entry_not_object",
                f"{scope}.{index}",
                "Mỗi phần tử trong danh sách contract phải là JSON object.",
            )
    return rows


def _require_keys(
    value: Mapping[str, Any],
    required: set[str],
    scope: str,
    findings: list[Finding],
) -> None:
    for key in sorted(required - set(value)):
        _add(
            findings,
            "required_key_missing",
            f"{scope}.{key}",
            f"Thiếu required key: {key}.",
        )


def _check_unique_names(
    rows: list[dict[str, Any]],
    key: str,
    entity: str,
    findings: list[Finding],
) -> set[str]:
    names: set[str] = set()
    for row in rows:
        name = row.get(key)
        if not isinstance(name, str) or not name:
            _add(
                findings,
                f"{entity}_name_missing",
                f"manifest.{entity}s",
                f"Mỗi {entity} phải có {key}.",
            )
            continue
        if name in names:
            _add(
                findings,
                f"duplicate_{entity}",
                f"manifest.{entity}s.{name}",
                f"{entity} bị khai báo trùng.",
            )
        names.add(name)
    return names


def _add(
    findings: list[Finding],
    code: str,
    scope: str,
    message: str,
    severity: Severity = "blocker",
) -> None:
    findings.append(Finding(code=code, scope=scope, message=message, severity=severity))


def _has_blocker(findings: Sequence[Finding]) -> bool:
    return any(finding.severity == "blocker" for finding in findings)


def _ordered_findings(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    unique = {
        (finding.code, finding.scope, finding.message, finding.severity): finding
        for finding in findings
    }
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (item.severity, item.code, item.scope, item.message),
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the checked-in contract without printing environment values."""

    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=repository_root / "deployment" / "pilot_manifest.json",
        type=Path,
    )
    parser.add_argument(
        "--ownership",
        default=repository_root / "deployment" / "operational_ownership.json",
        type=Path,
    )
    parser.add_argument(
        "--limitations",
        default=repository_root / "deployment" / "known_limitations.json",
        type=Path,
    )
    parser.add_argument(
        "--release-record",
        default=repository_root / "deployment" / "pilot_release_record.json",
        type=Path,
    )
    parser.add_argument("--actual-commit")
    parser.add_argument("--actual-tag")
    parser.add_argument("--actual-tag-target-commit")
    parser.add_argument("--actual-migration-revision")
    parser.add_argument(
        "--skip-environment",
        action="store_true",
        help="Skip runtime environment presence checks for static contract review.",
    )
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Validate only the deployment manifest and its repository bindings.",
    )
    args = parser.parse_args(argv)
    common = {
        "environment": None if args.skip_environment else os.environ,
        "actual_commit": args.actual_commit,
        "actual_tag": args.actual_tag,
        "actual_tag_target_commit": args.actual_tag_target_commit,
        "actual_migration_revision": args.actual_migration_revision,
        "repository_root": repository_root,
    }
    if args.manifest_only:
        report = validate_deployment_manifest(args.manifest, **common)
    else:
        report = validate_pilot_contract(
            args.manifest,
            args.ownership,
            args.limitations,
            args.release_record,
            **common,
        )
    # ASCII escapes keep this safe on Windows operator consoles with legacy encodings.
    print(json.dumps(report.as_dict(), ensure_ascii=True, indent=2))
    return 0 if report.decision in {GO, CONDITIONAL_GO} else 2


if __name__ == "__main__":
    raise SystemExit(main())
