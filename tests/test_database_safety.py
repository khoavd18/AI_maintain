"""Unit coverage for fail-closed PostgreSQL integration-test targeting."""

from __future__ import annotations

import pytest

from src.database.test_database import (
    validate_test_database_environment,
    validate_test_database_url,
)

_URL = (
    "postgresql+psycopg://maintenance_test:maintenance_test_password"
    "@localhost:15433/maintenance_copilot_test"
)


def test_test_database_url_accepts_the_dedicated_local_database() -> None:
    parsed = validate_test_database_url(_URL)

    assert parsed.database == "maintenance_copilot_test"
    assert parsed.host == "localhost"


@pytest.mark.parametrize(
    "url, message",
    [
        ("", "required"),
        ("postgresql://test:secret@localhost:15433/maintenance_copilot_test", "psycopg"),
        (
            "postgresql+psycopg://test:secret@localhost:15433/maintenance_copilot",
            "_test",
        ),
        (
            "postgresql+psycopg://test:secret@db.example.com:5432/maintenance_copilot_test",
            "loopback",
        ),
        (
            "postgresql+psycopg://maintenance:maintenance@localhost:15433/maintenance_copilot_test",
            "development",
        ),
        (
            "postgresql+psycopg://replace_with_database_user:secret@localhost:15433/maintenance_copilot_test",
            "placeholders",
        ),
        (
            "postgresql+psycopg://test:@localhost:15433/maintenance_copilot_test",
            "credentials",
        ),
    ],
)
def test_test_database_url_rejects_unsafe_targets(url: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_test_database_url(url)


def test_test_database_environment_rejects_runtime_url_mismatch() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        validate_test_database_environment(
            {
                "TEST_DATABASE_URL": _URL,
                "DATABASE_URL": (
                    "postgresql+psycopg://maintenance:maintenance"
                    "@localhost:5432/maintenance_copilot"
                ),
            }
        )


def test_test_database_environment_requires_explicit_test_url() -> None:
    with pytest.raises(ValueError, match="required"):
        validate_test_database_environment({})


def test_test_database_environment_accepts_matching_urls() -> None:
    parsed = validate_test_database_environment(
        {"TEST_DATABASE_URL": _URL, "DATABASE_URL": _URL}
    )

    assert parsed.database == "maintenance_copilot_test"
