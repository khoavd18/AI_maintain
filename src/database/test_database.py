"""Fail-closed validation for the dedicated PostgreSQL integration database."""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import unquote

from sqlalchemy.engine import URL
from sqlalchemy.engine.url import make_url

_LOCAL_TEST_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_PLACEHOLDER_PARTS = frozenset(
    {
        "replace_with_database_user",
        "replace_with_random_database_password",
        "replace_with_database_name",
    }
)
_DEVELOPMENT_DATABASE_NAMES = frozenset({"maintenance", "maintenance_copilot"})


def validate_test_database_url(
    database_url: str | URL | None,
    *,
    allowed_hosts: frozenset[str] = _LOCAL_TEST_HOSTS,
) -> URL:
    """Validate a PostgreSQL URL before any migration or destructive test setup.

    The integration suite is intentionally limited to local loopback hosts. A
    database suffix alone is insufficient protection because a production
    server can contain a database with a misleading name.
    """

    if database_url is None or not str(database_url).strip():
        raise ValueError("TEST_DATABASE_URL is required for PostgreSQL integration work.")
    parsed = make_url(database_url)
    database_name = unquote(parsed.database or "").strip()
    username = unquote(parsed.username or "").strip()
    password = unquote(parsed.password or "").strip()
    hostname = (parsed.host or "").strip().lower()

    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("TEST_DATABASE_URL must use postgresql+psycopg://")
    if not database_name.endswith("_test"):
        raise ValueError("Test database name must end with _test")
    if not hostname or hostname not in allowed_hosts:
        raise ValueError("TEST_DATABASE_URL host must be a local loopback host")
    if not username or not password:
        raise ValueError("TEST_DATABASE_URL must include dedicated test credentials")
    if any(
        part.lower().startswith("replace_with_") or part in _PLACEHOLDER_PARTS
        for part in (username, password, database_name)
    ):
        raise ValueError("TEST_DATABASE_URL must not contain example placeholders")
    if (
        username.lower() == "maintenance"
        and password.lower() == "maintenance"
    ):
        raise ValueError("TEST_DATABASE_URL must not use development database credentials")
    if database_name.lower() in _DEVELOPMENT_DATABASE_NAMES:
        raise ValueError("TEST_DATABASE_URL must not target the development database")
    return parsed


def validate_test_database_environment(
    environ: Mapping[str, str] | None = None,
) -> URL:
    """Validate the explicit test URL and reject an accidental URL mismatch."""

    values = os.environ if environ is None else environ
    test_url = values.get("TEST_DATABASE_URL")
    parsed = validate_test_database_url(test_url)
    runtime_url = values.get("DATABASE_URL")
    if runtime_url and make_url(runtime_url) != parsed:
        raise ValueError(
            "DATABASE_URL must equal TEST_DATABASE_URL during PostgreSQL integration work"
        )
    return parsed
