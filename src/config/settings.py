"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by API, dashboard, and background jobs."""

    app_name: str = "AI Maintenance Copilot"
    app_env: str = "local"
    database_url: str = (
        "postgresql+psycopg://maintenance:maintenance@localhost:5432/maintenance_copilot"
    )
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "maintenance_knowledge"
    embedding_model_name: str = "intfloat/multilingual-e5-small"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
