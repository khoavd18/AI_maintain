"""Fail-closed local configuration for the bounded Data Platform runtime."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import quote_plus


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "scale-postgres"}


@dataclass(frozen=True, slots=True)
class DataPlatformSettings:
    """One authoritative database and filesystem boundary for Stage 9."""

    host: str = "127.0.0.1"
    port: int = 25432
    database: str = "maintenance_copilot_scale"
    user: str = "maintenance_scale"
    password: str = "maintenance_scale_local_only"
    connect_timeout_seconds: int = 10
    statement_timeout_seconds: int = 1_800
    batch_size: int = 50_000
    data_root: Path = Path("data/scale")
    object_store: str = "local"
    s3_bucket: str | None = None

    @classmethod
    def from_env(cls) -> "DataPlatformSettings":
        """Build settings without reading the application's ``.env`` file."""

        return cls(
            host=os.getenv("DATA_PLATFORM_DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DATA_PLATFORM_DB_PORT", "25432")),
            database=os.getenv("DATA_PLATFORM_DB_NAME", "maintenance_copilot_scale"),
            user=os.getenv("DATA_PLATFORM_DB_USER", "maintenance_scale"),
            password=os.getenv("DATA_PLATFORM_DB_PASSWORD", "maintenance_scale_local_only"),
            connect_timeout_seconds=int(os.getenv("DATA_PLATFORM_CONNECT_TIMEOUT_SECONDS", "10")),
            statement_timeout_seconds=int(
                os.getenv("DATA_PLATFORM_STATEMENT_TIMEOUT_SECONDS", "1800")
            ),
            batch_size=int(os.getenv("DATA_PLATFORM_BATCH_SIZE", "50000")),
            data_root=Path(os.getenv("DATA_PLATFORM_DATA_ROOT", "data/scale")),
            object_store=os.getenv("DATA_PLATFORM_OBJECT_STORE", "local").lower(),
            s3_bucket=os.getenv("DATA_PLATFORM_S3_BUCKET") or None,
        ).validated()

    def validated(self) -> "DataPlatformSettings":
        """Reject any accidental connection to a non-isolated database."""

        if self.host not in _LOCAL_HOSTS:
            raise ValueError(
                "Data Platform scale database host must be loopback or scale-postgres."
            )
        if not self.database.endswith("_scale"):
            raise ValueError("Data Platform database name must end with '_scale'.")
        if "scale" not in self.user:
            raise ValueError("Data Platform database user must be scale-specific.")
        if not 1 <= self.port <= 65_535:
            raise ValueError("Data Platform database port is invalid.")
        if self.batch_size < 1_000 or self.batch_size > 200_000:
            raise ValueError("DATA_PLATFORM_BATCH_SIZE must be between 1,000 and 200,000.")
        if self.object_store not in {"local", "s3"}:
            raise ValueError("DATA_PLATFORM_OBJECT_STORE must be 'local' or 's3'.")
        if self.object_store == "s3" and not self.s3_bucket:
            raise ValueError("DATA_PLATFORM_S3_BUCKET is required when S3 is enabled.")
        return self

    @property
    def psycopg_kwargs(self) -> dict[str, object]:
        """Return connection kwargs so credentials never need to be logged in a URI."""

        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.database,
            "user": self.user,
            "password": self.password,
            "connect_timeout": self.connect_timeout_seconds,
            "options": (
                f"-c statement_timeout={self.statement_timeout_seconds * 1000} -c timezone=UTC"
            ),
        }

    @property
    def sqlalchemy_url(self) -> str:
        """Return a URL for Alembic/dbt subprocesses; callers must not log it."""

        return (
            "postgresql+psycopg://"
            f"{quote_plus(self.user)}:{quote_plus(self.password)}@"
            f"{self.host}:{self.port}/{quote_plus(self.database)}"
        )


def safe_database_label(settings: DataPlatformSettings) -> str:
    """Produce a credential-free label suitable for logs and reports."""

    return f"{settings.host}:{settings.port}/{settings.database}"
