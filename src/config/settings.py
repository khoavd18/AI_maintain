"""Application settings loaded from environment variables."""

import hashlib
import math
import re
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.release import APPLICATION_VERSION, CANONICAL_SCHEMA_REVISION, ReleaseIdentity

_GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_UNVERIFIED_RELEASE_VALUES = {"", "development", "unverified", "unset"}


class Settings(BaseSettings):
    """Runtime settings shared by API, dashboard, and background jobs."""

    app_name: str = "AI Maintenance Copilot"
    app_environment: Literal["development", "test", "pilot", "production"] = "development"
    release_identifier: str = "development"
    release_git_commit: str = "unverified"
    release_git_tag: str = "unverified"
    release_alembic_revision: str = CANONICAL_SCHEMA_REVISION
    storage_backend: Literal["postgresql", "csv"] = "postgresql"
    database_url: str = (
        "postgresql+psycopg://maintenance:maintenance@localhost:5432/maintenance_copilot"
    )
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout_seconds: int = Field(default=30, ge=1, le=120)
    database_statement_timeout_seconds: int = Field(default=30, ge=1, le=600)
    database_lock_timeout_seconds: int = Field(default=5, ge=1, le=60)
    database_idle_transaction_timeout_seconds: int = Field(default=60, ge=10, le=900)
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "maintenance_knowledge"
    qdrant_api_key: SecretStr = SecretStr("")
    qdrant_timeout_seconds: int = Field(default=5, ge=1, le=60)
    embedding_model_name: str = "intfloat/multilingual-e5-small"
    embedding_device: str = "auto"
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    embedding_dimensions: int = Field(default=384, ge=8, le=8192)
    rag_chunk_size: int = Field(default=800, ge=200, le=8000)
    rag_chunk_overlap: int = Field(default=80, ge=0, le=2000)
    rag_dense_candidates: int = Field(default=20, ge=5, le=100)
    rag_sparse_candidates: int = Field(default=20, ge=5, le=100)
    rag_fused_candidates: int = Field(default=20, ge=5, le=100)
    rag_final_top_k: int = Field(default=5, ge=1, le=20)
    rag_relevance_threshold: float = Field(default=0.55, ge=0.01, le=1.0)
    rag_dense_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    rag_sparse_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    rag_retrieval_weight: float = Field(default=0.55, ge=0.0, le=1.0)
    rag_reranker_weight: float = Field(default=0.40, ge=0.0, le=1.0)
    rag_metadata_weight: float = Field(default=0.05, ge=0.0, le=0.1)
    rag_reranker_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    rag_reranker_device: str = "auto"
    rag_sparse_max_chunks: int = Field(default=10000, ge=100, le=100000)
    rag_sparse_refresh_seconds: int = Field(default=60, ge=5, le=3600)
    rag_debug_enabled: bool = False
    llm_enabled: bool = False
    llm_provider: Literal["ollama", "openai_compatible"] = "ollama"
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_seconds: int = Field(default=30, ge=1, le=120)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    llm_max_tokens: int = Field(default=1200, ge=128, le=4096)
    llm_max_retries: int = Field(default=1, ge=0, le=2)
    llm_max_context_chars: int = Field(default=12000, ge=1000, le=50000)
    llm_min_relevant_documents: int = Field(default=1, ge=1, le=5)
    copilot_rate_limit_requests: int = Field(default=20, ge=1, le=100)
    copilot_rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    token_signing_secret: str = ""
    token_signing_previous_secret: str = ""
    access_token_lifetime_minutes: int = Field(default=15, ge=1, le=60)
    refresh_session_lifetime_days: int = Field(default=7, ge=1, le=30)
    refresh_cookie_name: str = "maintenance_refresh"
    csrf_cookie_name: str = "maintenance_csrf"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    login_rate_limit_attempts: int = Field(default=5, ge=1, le=100)
    login_rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
    attachment_storage_backend: Literal["local"] = "local"
    attachment_storage_root: Path = Path("data/attachments")
    attachment_max_size_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
        le=50 * 1024 * 1024,
    )
    frontend_base_url: str = "http://localhost:3000"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    worker_poll_interval_seconds: int = Field(default=2, ge=1, le=60)
    worker_heartbeat_interval_seconds: int = Field(default=10, ge=1, le=300)
    worker_heartbeat_stale_seconds: int = Field(default=60, ge=10, le=900)
    worker_outbox_lease_seconds: int = Field(default=120, ge=30, le=3600)
    worker_batch_size: int = Field(default=20, ge=1, le=200)
    operational_outbox_age_alert_seconds: int = Field(default=300, ge=60, le=86400)
    operational_repeated_job_failure_threshold: int = Field(default=3, ge=2, le=10)
    operational_analytics_stale_seconds: int = Field(default=172800, ge=3600, le=2592000)
    operational_backup_overdue_seconds: int = Field(default=604800, ge=3600, le=7776000)
    operational_disk_warning_free_percent: int = Field(default=20, ge=5, le=50)
    operational_disk_critical_free_percent: int = Field(default=10, ge=1, le=40)
    analytics_source_dir: Path = Path("data/raw")
    analytics_processed_dir: Path = Path("data/processed")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_primary_storage(self) -> "Settings":
        """Reject ambiguous or unsupported product storage configuration."""

        if self.storage_backend == "postgresql" and not self.database_url.startswith(
            "postgresql+psycopg://"
        ):
            raise ValueError(
                "DATABASE_URL must use postgresql+psycopg:// when STORAGE_BACKEND=postgresql."
            )
        if self.app_environment in {"pilot", "production"}:
            if self.storage_backend != "postgresql":
                raise ValueError("STORAGE_BACKEND must be postgresql outside development/test.")
            if len(self.token_signing_secret) < 32:
                raise ValueError(
                    "TOKEN_SIGNING_SECRET must contain at least 32 characters outside "
                    "development/test."
                )
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true outside development/test.")
            database_url = urlsplit(self.database_url)
            if (
                not database_url.hostname
                or not database_url.username
                or not database_url.password
                or not database_url.path.strip("/")
            ):
                raise ValueError(
                    "DATABASE_URL must include host, database, username, and password "
                    "outside development/test."
                )
            if database_url.username == "maintenance" and database_url.password == "maintenance":
                raise ValueError(
                    "DATABASE_URL must not use the development database credentials "
                    "outside development/test."
                )
            database_components = (
                unquote(database_url.username or ""),
                unquote(database_url.password or ""),
                unquote(database_url.path.strip("/")),
            )
            if any(
                component.lower().startswith("replace_with_") for component in database_components
            ):
                raise ValueError(
                    "DATABASE_URL must replace every example placeholder outside development/test."
                )
            if (
                self.release_identifier.lower() in _UNVERIFIED_RELEASE_VALUES
                or self.release_git_tag.lower() in _UNVERIFIED_RELEASE_VALUES
                or not _GIT_COMMIT_PATTERN.fullmatch(self.release_git_commit)
            ):
                raise ValueError(
                    "Pilot release identity requires an identifier, tag, and "
                    "40-character Git commit."
                )
            if self.release_alembic_revision != CANONICAL_SCHEMA_REVISION:
                raise ValueError("RELEASE_ALEMBIC_REVISION must match the application schema head.")
        elif not self.token_signing_secret:
            # Local tokens intentionally stop working after a process restart.
            self.token_signing_secret = secrets.token_urlsafe(48)
        if self.token_signing_previous_secret:
            if len(self.token_signing_previous_secret) < 32:
                raise ValueError(
                    "TOKEN_SIGNING_PREVIOUS_SECRET must contain at least 32 characters."
                )
            if self.token_signing_previous_secret == self.token_signing_secret:
                raise ValueError(
                    "TOKEN_SIGNING_PREVIOUS_SECRET must differ from TOKEN_SIGNING_SECRET."
                )
        if self.auth_cookie_samesite == "none" and not self.auth_cookie_secure:
            raise ValueError("SameSite=None requires AUTH_COOKIE_SECURE=true.")
        qdrant_url = urlsplit(self.qdrant_url)
        if (
            qdrant_url.scheme not in {"http", "https"}
            or not qdrant_url.netloc
            or qdrant_url.username
            or qdrant_url.password
            or qdrant_url.query
            or qdrant_url.fragment
        ):
            raise ValueError(
                "QDRANT_URL must be an http(s) origin/path without credentials, query, or fragment."
            )
        self.qdrant_url = self.qdrant_url.rstrip("/")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,255}", self.qdrant_collection):
            raise ValueError(
                "QDRANT_COLLECTION must contain only letters, numbers, underscores, or hyphens."
            )
        self.embedding_model_name = self.embedding_model_name.strip()
        if not self.embedding_model_name:
            raise ValueError("EMBEDDING_MODEL_NAME must not be empty.")
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE.")
        if self.rag_fused_candidates < self.rag_final_top_k:
            raise ValueError("RAG_FUSED_CANDIDATES must be at least RAG_FINAL_TOP_K.")
        if not math.isclose(
            self.rag_dense_weight + self.rag_sparse_weight,
            1.0,
            abs_tol=1e-9,
        ):
            raise ValueError("RAG_DENSE_WEIGHT and RAG_SPARSE_WEIGHT must sum to 1.0.")
        if not math.isclose(
            self.rag_retrieval_weight + self.rag_reranker_weight + self.rag_metadata_weight,
            1.0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                "RAG_RETRIEVAL_WEIGHT, RAG_RERANKER_WEIGHT, and RAG_METADATA_WEIGHT "
                "must sum to 1.0."
            )
        for field_name, device in {
            "EMBEDDING_DEVICE": self.embedding_device,
            "RAG_RERANKER_DEVICE": self.rag_reranker_device,
        }.items():
            if not re.fullmatch(r"(?:auto|cpu|cuda(?::\d+)?|mps)", device):
                raise ValueError(f"{field_name} must be auto, cpu, cuda[:index], or mps.")
        self.rag_reranker_model = self.rag_reranker_model.strip()
        if not self.rag_reranker_model:
            raise ValueError("RAG_RERANKER_MODEL must not be empty.")
        if self.llm_enabled:
            if not self.llm_model.strip():
                raise ValueError("LLM_MODEL is required when LLM_ENABLED=true.")
            if not self.llm_base_url.strip():
                raise ValueError("LLM_BASE_URL is required when LLM_ENABLED=true.")
        if self.llm_base_url:
            llm_url = urlsplit(self.llm_base_url)
            if (
                llm_url.scheme not in {"http", "https"}
                or not llm_url.netloc
                or llm_url.username
                or llm_url.password
                or llm_url.query
                or llm_url.fragment
            ):
                raise ValueError(
                    "LLM_BASE_URL must be an http(s) API origin/path without "
                    "credentials, query, or fragment."
                )
            self.llm_base_url = self.llm_base_url.rstrip("/")
        self.llm_model = self.llm_model.strip()
        if self.worker_heartbeat_stale_seconds <= self.worker_heartbeat_interval_seconds:
            raise ValueError(
                "WORKER_HEARTBEAT_STALE_SECONDS must exceed WORKER_HEARTBEAT_INTERVAL_SECONDS."
            )
        if (
            self.operational_disk_critical_free_percent
            >= self.operational_disk_warning_free_percent
        ):
            raise ValueError(
                "OPERATIONAL_DISK_CRITICAL_FREE_PERCENT must be lower than "
                "OPERATIONAL_DISK_WARNING_FREE_PERCENT."
            )
        frontend_url = urlsplit(self.frontend_base_url)
        if (
            frontend_url.scheme not in {"http", "https"}
            or not frontend_url.netloc
            or frontend_url.username
            or frontend_url.password
            or frontend_url.query
            or frontend_url.fragment
        ):
            raise ValueError(
                "FRONTEND_BASE_URL must be an http(s) origin without credentials, query, or fragment."
            )
        self.frontend_base_url = self.frontend_base_url.rstrip("/")
        return self

    def get_cors_allowed_origins(self) -> list[str]:
        """Return normalized, explicitly configured browser origins."""

        origins = [
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]
        if "*" in origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must list explicit origins; '*' is not allowed.")
        return list(dict.fromkeys(origins))

    def get_trusted_hosts(self) -> list[str]:
        """Return explicit host names accepted by the API."""

        hosts = [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]
        if not hosts or "*" in hosts:
            raise ValueError("TRUSTED_HOSTS must contain explicit host names.")
        return list(dict.fromkeys(hosts))

    @property
    def docs_enabled(self) -> bool:
        """Expose interactive API documentation only for local development and tests."""

        return self.app_environment in {"development", "test"}

    @property
    def release_identity(self) -> ReleaseIdentity:
        """Return the public release identity without inspecting Git at runtime."""

        return ReleaseIdentity(
            identifier=self.release_identifier,
            application_version=APPLICATION_VERSION,
            git_commit=self.release_git_commit,
            git_tag=self.release_git_tag,
            alembic_revision=self.release_alembic_revision,
        )

    @property
    def test_database_fingerprint(self) -> str | None:
        """Identify only an explicitly isolated test database without exposing its name."""

        if self.app_environment != "test" or self.storage_backend != "postgresql":
            return None
        database_name = unquote(urlsplit(self.database_url).path.strip("/"))
        if not database_name.endswith("_test"):
            return None
        return hashlib.sha256(f"pm9-test-database:{database_name}".encode("utf-8")).hexdigest()


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
