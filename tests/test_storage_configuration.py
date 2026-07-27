"""Tests for explicit PostgreSQL-primary runtime configuration."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.main import create_app
from src.api.services import get_processed_data_service
from src.config.settings import Settings, get_settings
from src.database.session import clear_database_caches
from src.repositories.contracts import StorageUnavailableError


def test_postgresql_mode_requires_explicit_psycopg_url() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+psycopg"):
        Settings(storage_backend="postgresql", database_url="sqlite:///local.db")


def test_explicit_csv_mode_does_not_require_postgresql_url() -> None:
    settings = Settings(storage_backend="csv", database_url="sqlite:///unused.db")
    assert settings.storage_backend == "csv"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"token_signing_secret": "", "auth_cookie_secure": True},
            "at least 32 characters",
        ),
        (
            {"token_signing_secret": "s" * 48, "auth_cookie_secure": False},
            "AUTH_COOKIE_SECURE",
        ),
    ],
)
def test_pilot_mode_rejects_unsafe_auth_configuration(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(app_environment="pilot", **overrides)


def test_browser_security_configuration_rejects_wildcards_and_unsafe_samesite() -> None:
    with pytest.raises(ValueError, match="explicit origins"):
        Settings(cors_allowed_origins="*").get_cors_allowed_origins()
    with pytest.raises(ValidationError, match="SameSite=None"):
        Settings(auth_cookie_samesite="none", auth_cookie_secure=False)


def test_api_documentation_is_local_only() -> None:
    development = Settings(app_environment="development")
    pilot = Settings(
        app_environment="pilot",
        release_identifier="product-milestone-9-test",
        release_git_commit="a" * 40,
        release_git_tag="product-milestone-9-test",
        token_signing_secret="s" * 48,
        auth_cookie_secure=True,
        database_url=(
            "postgresql+psycopg://pilot_user:pilot-password@db:5432/pilot_db"
        ),
    )

    assert development.docs_enabled is True
    assert pilot.docs_enabled is False


def test_pilot_mode_requires_postgresql_and_verified_release_identity() -> None:
    safe = {
        "token_signing_secret": "s" * 48,
        "auth_cookie_secure": True,
        "database_url": (
            "postgresql+psycopg://pilot_user:pilot-password@db:5432/pilot_db"
        ),
    }
    with pytest.raises(ValidationError, match="STORAGE_BACKEND"):
        Settings(
            app_environment="pilot",
            storage_backend="csv",
            **safe,
        )
    with pytest.raises(ValidationError, match="release identity"):
        Settings(app_environment="pilot", **safe)


def test_disk_capacity_thresholds_are_ordered() -> None:
    with pytest.raises(ValidationError, match="must be lower"):
        Settings(
            operational_disk_warning_free_percent=10,
            operational_disk_critical_free_percent=10,
        )


def test_repository_factory_never_falls_back_from_unavailable_postgresql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "postgresql")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://maintenance:maintenance@127.0.0.1:1/unavailable",
    )
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "1")
    _clear_runtime_caches()
    try:
        service = get_processed_data_service()
        assert service.repository.backend_name == "postgresql"
        with pytest.raises(StorageUnavailableError, match="unavailable"):
            service.repository.check_health()
    finally:
        _clear_runtime_caches()


def test_api_startup_fails_clearly_when_primary_database_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "postgresql")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://maintenance:maintenance@127.0.0.1:1/unavailable",
    )
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "1")
    _clear_runtime_caches()
    try:
        with pytest.raises(RuntimeError, match="no CSV fallback"):
            with TestClient(create_app()):
                pass
    finally:
        _clear_runtime_caches()


def _clear_runtime_caches() -> None:
    get_processed_data_service.cache_clear()
    get_settings.cache_clear()
    clear_database_caches()
