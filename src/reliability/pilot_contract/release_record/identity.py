"""Validate release-record identity and manifest summary bindings."""

from __future__ import annotations

from typing import Any

from ..constants import _COMMIT_RE
from ..document_shapes import _list_of_mappings, _mapping, _require_keys, _versioned
from ..document_values import _git_identity_matches, _is_placeholder
from ..evidence_values import _valid_utc_timestamp
from ..findings import _add
from ..schemas import Finding


def _validate_release_record_identity(
    record: dict[str, Any],
    manifest: dict[str, Any],
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
