"""Pilot environment validation."""

from __future__ import annotations

from collections.abc import Mapping
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .constants import (
    SECRET_ENVIRONMENT_NAMES,
    _COMMIT_RE,
)

from .schemas import Finding
from .support import (
    _safe_relative_path,
    _safe_service_url,
    _validate_integer_environment_match,
    _validate_integer_environment_range,
    _truthy,
    _is_placeholder,
    _mapping,
    _list_of_mappings,
    _add,
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


