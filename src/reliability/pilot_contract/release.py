"""Release observations and release-record validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .constants import (
    REQUIRED_OWNERS,
    CRITICAL_GATES,
    ALLOWED_RISK_CATEGORIES,
    ALLOWED_RISK_SEVERITIES,
    ALLOWED_RISK_STATUSES,
    ServiceProbe,
    _COMMIT_RE,
)

from .schemas import Finding
from .support import (
    _critical_limitations_accepted,
    _valid_evidence_links,
    _valid_utc_timestamp,
    _git_identity_matches,
    _is_placeholder,
    _non_placeholder_text,
    _versioned,
    _mapping,
    _list_of_mappings,
    _require_keys,
    _check_unique_names,
    _add,
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


