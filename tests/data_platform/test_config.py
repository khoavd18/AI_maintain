from __future__ import annotations

from pathlib import Path

import pytest

from data_platform.config import DataPlatformSettings, safe_database_label


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"host": "db.example.com"}, "loopback"),
        ({"database": "maintenance_copilot"}, "'_scale'"),
        ({"user": "maintenance"}, "scale-specific"),
        ({"port": 0}, "port"),
        ({"batch_size": 999}, "BATCH_SIZE"),
        ({"batch_size": 200_001}, "BATCH_SIZE"),
        ({"object_store": "ftp"}, "OBJECT_STORE"),
        ({"object_store": "s3", "s3_bucket": None}, "S3_BUCKET"),
    ],
)
def test_scale_configuration_fails_closed(
    overrides: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 25432,
        "database": "maintenance_copilot_scale",
        "user": "maintenance_scale",
        "password": "local-test-only",
        "data_root": Path("data/scale"),
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        DataPlatformSettings(**values).validated()  # type: ignore[arg-type]


def test_environment_configuration_uses_only_dedicated_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://unsafe.example/current-development")
    monkeypatch.setenv("DB_HOST", "unsafe.example")
    monkeypatch.setenv("DATA_PLATFORM_DB_HOST", "localhost")
    monkeypatch.setenv("DATA_PLATFORM_DB_NAME", "isolated_benchmark_scale")
    monkeypatch.setenv("DATA_PLATFORM_DB_USER", "benchmark_scale_user")
    monkeypatch.setenv("DATA_PLATFORM_DB_PASSWORD", "local-test-only")

    settings = DataPlatformSettings.from_env()

    assert settings.host == "localhost"
    assert settings.database == "isolated_benchmark_scale"
    assert settings.user == "benchmark_scale_user"
    assert "unsafe.example" not in settings.sqlalchemy_url


def test_safe_label_never_contains_the_password() -> None:
    settings = DataPlatformSettings(password="do-not-log-this").validated()

    label = safe_database_label(settings)

    assert label == "127.0.0.1:25432/maintenance_copilot_scale"
    assert settings.password not in label
