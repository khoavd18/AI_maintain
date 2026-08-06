"""Pilot decision calculation and release-record generation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .constants import (
    GO,
    CONDITIONAL_GO,
    NO_GO,
    EXTERNAL_PILOT_NO_GO,
    REQUIRED_OWNERS,
    CRITICAL_GATES,
    PROTECTED_RISK_CATEGORIES,
    ALLOWED_RISK_CATEGORIES,
    ALLOWED_RISK_SEVERITIES,
    ALLOWED_RISK_STATUSES,
    JsonMapping,
    JsonSource,
)

from .documents import load_json_document, manifest_sha256
from .redaction import redact_release_record
from .support import (
    _ownership_ready,
    _critical_limitations_accepted,
    _condition_is_bounded,
    _valid_evidence_links,
    _non_placeholder_text,
    _mapping,
    _list_of_mappings,
)


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


