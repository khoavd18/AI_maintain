"""Ordered characterization for runtime and governance validator facades."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from src.reliability.pilot_contract.ownership import _validate_limitations, _validate_ownership
from src.reliability.pilot_contract.runtime import _validate_runtime_settings


DEPLOYMENT_ROOT = Path(__file__).resolve().parents[3] / "deployment"


def _load(name: str) -> dict[str, Any]:
    return json.loads((DEPLOYMENT_ROOT / name).read_text(encoding="utf-8"))


def _finding_identity(findings: list[Any]) -> list[tuple[str, str]]:
    return [(finding.code, finding.scope) for finding in findings]


def test_runtime_validator_preserves_capability_and_finding_order() -> None:
    manifest = _load("pilot_manifest.json")
    manifest["worker"]["instance_count"] = 2
    manifest["worker"]["heartbeat_stale_seconds"] = manifest["worker"]["heartbeat_interval_seconds"]
    manifest["database"]["pool_size"] = 0
    manifest["operational_alerts"]["delivery"] = "email"
    manifest["operational_alerts"]["disk_critical_free_percent"] = manifest["operational_alerts"][
        "disk_warning_free_percent"
    ]
    first_job = next(iter(manifest["retry_and_dead_letter"]["jobs"]))
    del manifest["retry_and_dead_letter"]["jobs"][first_job]
    next_job = next(iter(manifest["retry_and_dead_letter"]["jobs"]))
    manifest["retry_and_dead_letter"]["jobs"][next_job]["max_attempts"] = 0
    manifest["retry_and_dead_letter"]["outbox"]["max_attempts"] = 0
    manifest["retry_and_dead_letter"]["dead_letter_operator_visible"] = False
    manifest["restore_prerequisites"]["validated_checksum_required"] = False
    manifest["restore_prerequisites"]["restore_database_name_suffix"] = "restore"
    manifest["restore_prerequisites"]["postgresql_integration_test_database_name_suffix"] = "test"
    manifest["rollback"]["target_git_commit"] = "short"
    manifest["rollback"]["database_downgrade_allowed"] = True
    manifest["rollback"]["validated_backup_required"] = False
    manifest["rollback"]["rehearsal_status"] = "pending"

    findings: list[Any] = []
    _validate_runtime_settings(manifest, findings)

    assert _finding_identity(findings) == [
        ("unsupported_worker_topology", "manifest.worker.instance_count"),
        ("invalid_worker_heartbeat_window", "manifest.worker"),
        ("invalid_runtime_setting", "manifest.database.pool_size"),
        ("unsupported_alert_delivery", "manifest.operational_alerts.delivery"),
        ("invalid_disk_threshold_order", "manifest.operational_alerts"),
        ("retry_job_catalog_mismatch", "manifest.retry_and_dead_letter.jobs"),
        (
            "invalid_retry_setting",
            "manifest.retry_and_dead_letter.jobs.sla_escalation.max_attempts",
        ),
        ("invalid_outbox_retry_setting", "manifest.retry_and_dead_letter.outbox.max_attempts"),
        ("dead_letter_contract_weakened", "manifest.retry_and_dead_letter"),
        (
            "restore_prerequisite_missing",
            "manifest.restore_prerequisites.validated_checksum_required",
        ),
        (
            "unsafe_restore_database_suffix",
            "manifest.restore_prerequisites.restore_database_name_suffix",
        ),
        (
            "unsafe_postgresql_test_database_suffix",
            "manifest.restore_prerequisites.postgresql_integration_test_database_name_suffix",
        ),
        ("rollback_commit_invalid", "manifest.rollback.target_git_commit"),
        ("unsafe_database_downgrade", "manifest.rollback.database_downgrade_allowed"),
        ("rollback_backup_not_required", "manifest.rollback.validated_backup_required"),
        ("rollback_rehearsal_unverified", "manifest.rollback.rehearsal_status"),
    ]


def test_ownership_validator_preserves_section_order() -> None:
    ownership = _load("operational_ownership.json")
    ownership["record_status"] = "approved"
    for key, assignment in ownership["assignments"].items():
        assignment.update(
            status="assigned",
            assigned_role=f"role-{key}",
            approved_internal_channel="channel",
            approval_evidence_links=[f"evidence/{key}.json"],
        )
    ownership["incident_communication"].update(
        status="configured",
        primary_internal_channel="primary",
        fallback_internal_channel="fallback",
        approval_evidence_links=["evidence/incident.json"],
    )
    ownership["support_coverage"].update(
        status="confirmed",
        support_hours="hours",
        after_hours_assumption="paused",
        timezone="Asia/Ho_Chi_Minh",
        approval_evidence_links=["evidence/coverage.json"],
    )
    ownership["escalation_path"].update(
        status="configured",
        approval_evidence_links=["evidence/escalation.json"],
    )
    ownership["assignments"]["operational_owner"]["status"] = "pending"
    ownership["incident_communication"]["primary_internal_channel"] = ""
    ownership["support_coverage"]["timezone"] = "Mars/Olympus"
    ownership["escalation_path"]["steps"].append(deepcopy(ownership["escalation_path"]["steps"][0]))

    findings: list[Any] = []
    _validate_ownership(ownership, findings)

    assert _finding_identity(findings) == [
        ("ownership_placeholder", "ownership.assignments.operational_owner"),
        ("incident_path_missing", "ownership.incident_communication"),
        ("support_timezone_invalid", "ownership.support_coverage.timezone"),
        ("duplicate_escalation_step", "ownership.escalation_path"),
    ]


def test_limitations_validator_preserves_row_and_duplicate_order() -> None:
    limitations = _load("known_limitations.json")
    limitations["record_status"] = "accepted"
    for row in limitations["limitations"]:
        row.update(
            owner_role="owner",
            acceptance_status="accepted",
            accepted_by_role="acceptor",
            accepted_at_utc="2026-07-26T12:00:00Z",
            acceptance_evidence_links=[f"evidence/{row['id']}.json"],
        )
    first = limitations["limitations"][0]
    first.update(critical=False, description="", owner_role="", accepted_at_utc="invalid")
    limitations["limitations"].append(deepcopy(first))

    findings: list[Any] = []
    _validate_limitations(limitations, findings)

    assert [code for code, _scope in _finding_identity(findings)] == [
        "required_limitation_weakened",
        "limitation_field_missing",
        "limitation_owner_placeholder",
        "limitation_acceptance_evidence_missing",
        "duplicate_limitation",
        "required_limitation_weakened",
        "limitation_field_missing",
        "limitation_owner_placeholder",
        "limitation_acceptance_evidence_missing",
    ]
