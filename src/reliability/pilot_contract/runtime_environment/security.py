"""Validate injected pilot security and PostgreSQL environment values."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import unquote, urlsplit

from ..constants import SECRET_ENVIRONMENT_NAMES
from ..document_shapes import _list_of_mappings
from ..document_values import _is_placeholder
from ..findings import _add
from ..schemas import Finding
from .integers import _truthy


def _validate_security_environment(
    manifest: dict[str, Any],
    environment: Mapping[str, str],
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
