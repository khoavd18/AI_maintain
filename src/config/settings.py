"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by API, dashboard, and background jobs."""

    app_name: str = "AI Maintenance Copilot"
    database_url: str = (
        "postgresql+psycopg://maintenance:maintenance@localhost:5432/maintenance_copilot"
    )
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "maintenance_knowledge"
    embedding_model_name: str = "intfloat/multilingual-e5-small"
    cors_allowed_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
