"""Focused tests for the PM9 deployment, ownership, and release contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.reliability.pilot_contract import (
    CONDITIONAL_GO,
    CRITICAL_GATES,
    GO,
    NO_GO,
    evaluate_pilot_decision,
    generate_release_record,
    manifest_sha256,
    redact_release_record,
    validate_deployment_manifest,
    validate_pilot_contract,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_ROOT = REPOSITORY_ROOT / "deployment"


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


def test_checked_in_placeholders_keep_release_no_go_and_hash_is_bound() -> None:
    manifest = _load("pilot_manifest.json")
    release = _load("pilot_release_record.json")

    report = validate_pilot_contract(
        manifest,
        _load("operational_ownership.json"),
        _load("known_limitations.json"),
        release,
        repository_root=REPOSITORY_ROOT,
    )

    assert report.decision == NO_GO
    assert "ownership_placeholder" in report.codes
    assert "critical_limitation_unaccepted" in report.codes
    assert "critical_gate_open" in report.codes
    assert release["release"]["deployment_manifest_sha256"] == manifest_sha256(manifest)


def test_manifest_detects_missing_service_duplicate_port_job_and_path_escape() -> None:
    manifest = _ready_manifest()
    manifest["services"] = [
        service for service in manifest["services"] if service["name"] != "qdrant"
    ]
    manifest["ports"][1]["host_port"] = manifest["ports"][0]["host_port"]
    manifest["scheduled_jobs"].append({"job_type": "arbitrary_shell", "enabled": True})
    manifest["storage"]["paths"]["attachments"]["relative_path"] = "../../outside"

    report = validate_deployment_manifest(manifest, repository_root=REPOSITORY_ROOT)

    assert {
        "required_service_missing",
        "duplicate_port",
        "unsupported_job",
        "path_containment_violation",
    }.issubset(report.codes)


def test_manifest_rejects_scalar_rows_in_closed_contract_lists() -> None:
    manifest = _ready_manifest()
    for key in (
        "services",
        "ports",
        "volumes",
        "required_environment_variables",
        "health_endpoints",
        "scheduled_jobs",
    ):
        manifest[key].append(42)

    report = validate_deployment_manifest(manifest, repository_root=REPOSITORY_ROOT)
    malformed_scopes = {
        finding.scope for finding in report.findings if finding.code == "list_entry_not_object"
    }

    assert malformed_scopes == {
        f"manifest.{key}.{len(manifest[key]) - 1}"
        for key in (
            "services",
            "ports",
            "volumes",
            "required_environment_variables",
            "health_endpoints",
            "scheduled_jobs",
        )
    }
    assert report.decision == NO_GO


def test_runtime_observations_detect_identity_and_reachability_mismatches() -> None:
    manifest = _ready_manifest()
    probed: list[str] = []

    def probe(service: dict[str, Any]) -> bool:
        probed.append(service["name"])
        return service["name"] != "worker"

    report = validate_deployment_manifest(
        manifest,
        environment=_ready_environment(),
        actual_commit="b" * 40,
        actual_tag="wrong-tag",
        actual_tag_target_commit="c" * 40,
        actual_migration_revision="wrong-revision",
        service_probe=probe,
        repository_root=REPOSITORY_ROOT,
    )

    assert set(probed) == {"postgres", "qdrant", "api", "worker", "frontend"}
    assert {
        "release_environment_commit_mismatch",
        "release_tag_mismatch",
        "release_tag_target_commit_mismatch",
        "migration_revision_mismatch",
        "required_service_unreachable",
    }.issubset(report.codes)


def test_release_commit_is_resolved_from_exact_tag_target_without_self_reference() -> None:
    manifest = _ready_manifest()
    environment = _ready_environment()

    assert "expected_commit" not in manifest["release"]
    assert manifest["release"]["commit_resolution"] == "exact_tag_target"

    report = validate_deployment_manifest(
        manifest,
        environment=environment,
        actual_commit=environment["RELEASE_GIT_COMMIT"],
        actual_tag=environment["RELEASE_GIT_TAG"],
        actual_tag_target_commit=environment["RELEASE_GIT_COMMIT"],
        actual_migration_revision=environment["RELEASE_ALEMBIC_REVISION"],
        service_probe=lambda _service: True,
        repository_root=REPOSITORY_ROOT,
    )

    assert report.is_valid
    assert report.decision == GO


def test_final_release_record_requires_observed_tag_target_commit() -> None:
    manifest, ownership, limitations, record = _ready_documents()

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        repository_root=REPOSITORY_ROOT,
    )

    assert report.decision == NO_GO
    assert "release_commit_observation_missing" in report.codes
    assert "release_tag_target_observation_missing" in report.codes


def test_final_release_record_requires_complete_runtime_observations() -> None:
    manifest, ownership, limitations, record = _ready_documents()

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        actual_commit="a" * 40,
        repository_root=REPOSITORY_ROOT,
    )

    assert {
        "release_environment_observation_missing",
        "release_tag_observation_missing",
        "release_tag_target_observation_missing",
        "migration_observation_missing",
    }.issubset(report.codes)
    assert report.decision == NO_GO


def test_missing_pilot_secret_is_reported_without_returning_values() -> None:
    environment = _ready_environment()
    environment.pop("TOKEN_SIGNING_SECRET")
    sentinel = environment["POSTGRES_PASSWORD"]

    report = validate_deployment_manifest(
        _ready_manifest(),
        environment=environment,
        repository_root=REPOSITORY_ROOT,
    )
    serialized = json.dumps(report.as_dict())

    assert "pilot_secret_missing" in report.codes
    assert sentinel not in serialized
    assert "DATABASE_URL" not in serialized or environment["DATABASE_URL"] not in serialized


def test_compose_input_and_runtime_drift_are_blocking() -> None:
    manifest = _ready_manifest()
    manifest["required_environment_variables"] = [
        row
        for row in manifest["required_environment_variables"]
        if row["name"] != "PILOT_APP_IMAGE"
    ]
    environment = _ready_environment()
    environment["WORKER_BATCH_SIZE"] = "999"

    report = validate_deployment_manifest(
        manifest,
        environment=environment,
        repository_root=REPOSITORY_ROOT,
    )

    assert "compose_environment_not_declared" in report.codes
    assert "runtime_environment_mismatch" in report.codes


def test_restore_and_postgresql_test_suffixes_are_explicitly_separate() -> None:
    prerequisites = _load("pilot_manifest.json")["restore_prerequisites"]

    assert prerequisites["restore_database_name_suffix"] == "_restore"
    assert prerequisites["postgresql_integration_test_database_name_suffix"] == "_test"


def test_complete_evidence_is_go_and_result_is_deterministic() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    kwargs = {
        "environment": _ready_environment(),
        "actual_commit": "a" * 40,
        "actual_tag": "product-milestone-9",
        "actual_tag_target_commit": "a" * 40,
        "actual_migration_revision": "20260726_0008",
        "service_probe": lambda _service: True,
        "repository_root": REPOSITORY_ROOT,
    }

    first = validate_pilot_contract(manifest, ownership, limitations, record, **kwargs)
    second = validate_pilot_contract(manifest, ownership, limitations, record, **kwargs)

    assert first.decision == GO
    assert first.is_valid
    assert first.as_dict() == second.as_dict()


def test_missing_incident_path_and_unaccepted_critical_limitation_block_go() -> None:
    _manifest, ownership, limitations, record = _ready_documents()
    ownership["incident_communication"]["status"] = "unconfigured"
    limitations["limitations"][0]["acceptance_status"] = "pending"

    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO


def test_required_limitation_cannot_be_downgraded_from_critical() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    limitations["limitations"][0]["critical"] = False
    record["known_limitations_acceptance_status"] = "pending"
    record["final_decision"] = NO_GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        actual_commit="a" * 40,
        repository_root=REPOSITORY_ROOT,
    )

    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO
    assert "required_limitation_weakened" in report.codes
    assert report.decision == NO_GO


def test_invalid_timezone_and_duplicate_escalation_steps_block_readiness() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    ownership["support_coverage"]["timezone"] = "Mars/Olympus_Mons"
    ownership["escalation_path"]["steps"].append(dict(ownership["escalation_path"]["steps"][0]))
    record["final_decision"] = NO_GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        actual_commit="a" * 40,
        repository_root=REPOSITORY_ROOT,
    )

    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO
    assert {
        "support_timezone_invalid",
        "duplicate_escalation_step",
    }.issubset(report.codes)
    assert report.decision == NO_GO


def test_pending_governance_records_and_missing_approval_evidence_block_go() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    ownership["record_status"] = "pending_owner_input"
    limitations["record_status"] = "pending_business_acceptance"
    record["final_decision"] = NO_GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        repository_root=REPOSITORY_ROOT,
    )

    assert report.decision == NO_GO
    assert "ownership_record_not_approved" in report.codes
    assert "limitations_record_not_accepted" in report.codes

    ownership = _ready_ownership()
    limitations = _ready_limitations()
    ownership["support_coverage"]["approval_evidence_links"] = []
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO


def test_decision_fails_closed_for_malformed_or_duplicate_rows() -> None:
    _manifest, ownership, limitations, record = _ready_documents()
    record["gates"].append(42)
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

    _manifest, ownership, limitations, record = _ready_documents()
    record["gates"].append(dict(record["gates"][0]))
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

    _manifest, ownership, limitations, record = _ready_documents()
    record["gates"][0]["critical"] = False
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

    _manifest, ownership, limitations, record = _ready_documents()
    record["open_risks"] = [42]
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO


def test_bounded_noncritical_risk_is_conditional_go() -> None:
    _manifest, ownership, limitations, record = _ready_documents()
    assigned_owner_role = ownership["assignments"]["application_support_contact"]["assigned_role"]
    record["open_risks"] = [
        {
            "id": "bounded_display_risk",
            "severity": "low",
            "category": "usability",
            "status": "open",
        }
    ]
    record["conditions"] = [
        {
            "risk_or_limitation_id": "bounded_display_risk",
            "description": "Một nhãn pilot cần được làm rõ.",
            "owner_role": assigned_owner_role,
            "mitigation": "Hướng dẫn operator đã được ghi trong pilot runbook.",
            "review_trigger": "Trước khi mở rộng nhóm pilot.",
            "pilot_scope_limit": "Chỉ nhóm internal pilot đã phê duyệt.",
            "evidence_links": ["evidence/conditions/bounded-display-risk.json"],
        }
    ]

    assert evaluate_pilot_decision(record, ownership, limitations) == CONDITIONAL_GO

    record["conditions"][0]["owner_role"] = "PENDING_ASSIGNMENT"
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO


def test_condition_owner_must_match_an_assigned_operational_role() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    record["open_risks"] = [
        {
            "id": "bounded_display_risk",
            "severity": "low",
            "category": "usability",
            "status": "open",
        }
    ]
    record["conditions"] = [
        {
            "risk_or_limitation_id": "bounded_display_risk",
            "description": "Một nhãn pilot cần được làm rõ.",
            "owner_role": "shadow_support_role",
            "mitigation": "Hướng dẫn operator đã được ghi trong pilot runbook.",
            "review_trigger": "Trước khi mở rộng nhóm pilot.",
            "pilot_scope_limit": "Chỉ nhóm internal pilot đã phê duyệt.",
            "evidence_links": ["evidence/conditions/bounded-display-risk.json"],
        }
    ]

    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

    ownership["assignments"]["shadow_contact"] = {
        "assigned_role": "shadow_support_role",
        "status": "assigned",
    }
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO
    record["final_decision"] = NO_GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        environment=_ready_environment(),
        actual_commit="a" * 40,
        actual_tag="product-milestone-9",
        actual_tag_target_commit="a" * 40,
        actual_migration_revision="20260726_0008",
        service_probe=lambda _service: True,
        repository_root=REPOSITORY_ROOT,
    )

    assert report.decision == NO_GO


def test_optional_limitation_with_invalid_status_fails_closed() -> None:
    _manifest, ownership, limitations, record = _ready_documents()
    limitations["limitations"].append(
        {
            "id": "optional_cosmetic_limitation",
            "critical": False,
            "description": "Giới hạn hiển thị không ảnh hưởng tính toàn vẹn.",
            "operational_consequence": "Operator có thể cần đọc hướng dẫn bổ sung.",
            "mitigation": "Giữ hướng dẫn trong runbook pilot.",
            "owner_role": ownership["assignments"]["application_support_contact"]["assigned_role"],
            "acceptance_status": "unknown",
            "review_trigger": "Trước khi mở rộng nhóm pilot.",
        }
    )
    record["conditions"] = [
        {
            "risk_or_limitation_id": "optional_cosmetic_limitation",
            "description": "Điều kiện pilot có giới hạn.",
            "owner_role": ownership["assignments"]["application_support_contact"]["assigned_role"],
            "mitigation": "Giữ phạm vi pilot có giới hạn.",
            "review_trigger": "Trước khi mở rộng pilot.",
            "pilot_scope_limit": "Chỉ nhóm internal pilot đã phê duyệt.",
            "evidence_links": ["evidence/conditions/optional-limitation.json"],
        }
    ]

    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO


def test_non_string_limitation_statuses_fail_closed_without_type_error() -> None:
    for invalid_status in (None, [], {}):
        manifest, ownership, limitations, record = _ready_documents()
        limitations["limitations"].append(
            {
                "id": "optional_cosmetic_limitation",
                "critical": False,
                "description": "Giới hạn hiển thị không ảnh hưởng tính toàn vẹn.",
                "operational_consequence": "Operator có thể cần đọc hướng dẫn bổ sung.",
                "mitigation": "Giữ hướng dẫn trong runbook pilot.",
                "owner_role": ownership["assignments"]["application_support_contact"][
                    "assigned_role"
                ],
                "acceptance_status": invalid_status,
                "review_trigger": "Trước khi mở rộng nhóm pilot.",
            }
        )
        record["final_decision"] = NO_GO

        assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

        report = validate_pilot_contract(
            manifest,
            ownership,
            limitations,
            record,
            environment=_ready_environment(),
            actual_commit="a" * 40,
            actual_tag="product-milestone-9",
            actual_tag_target_commit="a" * 40,
            actual_migration_revision="20260726_0008",
            service_probe=lambda _service: True,
            repository_root=REPOSITORY_ROOT,
        )

        assert "limitation_acceptance_invalid" in report.codes
        assert report.decision == NO_GO


def test_incomplete_or_unknown_risk_fields_cannot_yield_conditional_go() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    assigned_owner_role = ownership["assignments"]["application_support_contact"]["assigned_role"]
    bounded_condition = {
        "risk_or_limitation_id": "bounded_display_risk",
        "description": "Một nhãn pilot cần được làm rõ.",
        "owner_role": assigned_owner_role,
        "mitigation": "Hướng dẫn operator đã được ghi trong pilot runbook.",
        "review_trigger": "Trước khi mở rộng nhóm pilot.",
        "pilot_scope_limit": "Chỉ nhóm internal pilot đã phê duyệt.",
        "evidence_links": ["evidence/conditions/bounded-display-risk.json"],
    }
    baseline = {
        "id": "bounded_display_risk",
        "severity": "low",
        "category": "usability",
        "status": "open",
    }
    record["conditions"] = [bounded_condition]

    for field, invalid_value in (
        ("status", "unknown"),
        ("severity", "unknown"),
        ("category", "unknown"),
    ):
        risk = dict(baseline)
        risk[field] = invalid_value
        record["open_risks"] = [risk]
        assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

    record["open_risks"] = [{"id": "bounded_display_risk"}]
    record["final_decision"] = NO_GO
    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        actual_commit="a" * 40,
        repository_root=REPOSITORY_ROOT,
    )

    assert {
        "risk_status_invalid",
        "risk_severity_invalid",
        "risk_category_invalid",
    }.issubset(report.codes)
    assert report.decision == NO_GO


def test_closed_protected_risk_cannot_be_skipped_in_open_risk_register() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    record["open_risks"] = [
        {
            "id": "critical_auth_risk",
            "severity": "critical",
            "category": "authorization",
            "status": "closed",
        }
    ]
    record["final_decision"] = GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        environment=_ready_environment(),
        actual_commit="a" * 40,
        actual_tag="product-milestone-9",
        actual_tag_target_commit="a" * 40,
        actual_migration_revision="20260726_0008",
        service_probe=lambda _service: True,
        repository_root=REPOSITORY_ROOT,
    )

    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO
    assert "risk_status_invalid" in report.codes
    assert report.decision == NO_GO


def test_orphan_condition_and_cross_register_id_collision_fail_closed() -> None:
    _manifest, ownership, limitations, record = _ready_documents()
    record["conditions"] = [
        {
            "risk_or_limitation_id": "nonexistent_item",
            "description": "Điều kiện không có risk hoặc limitation nguồn.",
            "owner_role": ownership["assignments"]["application_support_contact"]["assigned_role"],
            "mitigation": "Giữ phạm vi pilot có giới hạn.",
            "review_trigger": "Trước khi mở rộng pilot.",
            "pilot_scope_limit": "Chỉ nhóm internal pilot đã phê duyệt.",
            "evidence_links": ["evidence/conditions/orphan.json"],
        }
    ]
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

    record["open_risks"] = [
        {
            "id": limitations["limitations"][0]["id"],
            "severity": "low",
            "category": "usability",
            "status": "open",
        }
    ]
    record["conditions"][0]["risk_or_limitation_id"] = record["open_risks"][0]["id"]
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO


def test_placeholder_risk_limitation_and_condition_ids_fail_closed() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    assigned_owner_role = ownership["assignments"]["application_support_contact"]["assigned_role"]
    limitations["limitations"].append(
        {
            "id": "PENDING_LIMITATION",
            "critical": False,
            "description": "Giới hạn phụ trong phạm vi pilot.",
            "operational_consequence": "Operator cần theo dõi thủ công.",
            "mitigation": "Giữ phạm vi pilot có giới hạn.",
            "owner_role": assigned_owner_role,
            "acceptance_status": "pending",
            "review_trigger": "Trước khi mở rộng pilot.",
        }
    )
    record["conditions"] = [
        {
            "risk_or_limitation_id": "PENDING_LIMITATION",
            "description": "Điều kiện pilot có giới hạn.",
            "owner_role": assigned_owner_role,
            "mitigation": "Giữ phạm vi pilot có giới hạn.",
            "review_trigger": "Trước khi mở rộng pilot.",
            "pilot_scope_limit": "Chỉ nhóm internal pilot đã phê duyệt.",
            "evidence_links": ["evidence/conditions/limitation.json"],
        }
    ]
    record["final_decision"] = CONDITIONAL_GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        environment=_ready_environment(),
        actual_commit="a" * 40,
        actual_tag="product-milestone-9",
        actual_tag_target_commit="a" * 40,
        actual_migration_revision="20260726_0008",
        service_probe=lambda _service: True,
        repository_root=REPOSITORY_ROOT,
    )

    assert "limitation_id_missing" in report.codes
    assert report.decision == NO_GO

    record["open_risks"] = [
        {
            "id": "PENDING_RISK",
            "severity": "low",
            "category": "usability",
            "status": "open",
        }
    ]
    record["conditions"][0]["risk_or_limitation_id"] = "PENDING_RISK"
    assert evaluate_pilot_decision(record, ownership, _ready_limitations()) == NO_GO


def test_release_record_requires_evidence_and_matching_rollback_metadata() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    record["gates"][0]["evidence_links"] = []
    record["rollback"]["target_git_tag"] = "wrong-tag"
    record["final_decision"] = NO_GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        environment=_ready_environment(),
        actual_commit="a" * 40,
        actual_tag="product-milestone-9",
        actual_tag_target_commit="a" * 40,
        actual_migration_revision="20260726_0008",
        service_probe=lambda _service: True,
        repository_root=REPOSITORY_ROOT,
    )

    assert "gate_evidence_missing" in report.codes
    assert "rollback_metadata_mismatch" in report.codes
    assert report.decision == NO_GO


def test_release_redactor_removes_credentials_contacts_and_local_paths() -> None:
    redacted = redact_release_record(
        {
            "password": "secret-value",
            "artifact_path": "C:\\Users\\Example\\private.json",
            "connection": "postgresql://pilot:secret@database/pilot",
            "email": "person@example.com",
            "safe_link": "evidence/releases/pm9.json",
        }
    )

    serialized = json.dumps(redacted)
    assert "secret-value" not in serialized
    assert "Example" not in serialized
    assert "person@example.com" not in serialized
    assert redacted["safe_link"] == "evidence/releases/pm9.json"
