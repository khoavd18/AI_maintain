"""Runtime, retry, restore, and rollback validation."""

from __future__ import annotations

from typing import Any

from .constants import (
    SUPPORTED_JOBS,
    _COMMIT_RE,
)

from .schemas import Finding
from .support import (
    _mapping,
    _require_keys,
    _add,
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


