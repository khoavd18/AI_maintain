"""Validate injected runtime settings against bounded manifest configuration."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from ..document_shapes import _list_of_mappings, _mapping
from ..findings import _add
from ..schemas import Finding
from .integers import (
    _validate_integer_environment_match,
    _validate_integer_environment_range,
)


def _validate_runtime_environment_settings(
    manifest: dict[str, Any],
    environment: Mapping[str, str],
    findings: list[Finding],
) -> None:
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
