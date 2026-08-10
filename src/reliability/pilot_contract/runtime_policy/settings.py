"""Worker, database, and operational-alert runtime policy validation."""

from __future__ import annotations

from typing import Any

from ..document_shapes import _mapping, _require_keys
from ..findings import _add
from ..schemas import Finding


def _validate_operating_settings(
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
