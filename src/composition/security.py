"""Construction of the authentication service graph."""

from __future__ import annotations

from functools import lru_cache

from src.config.settings import get_settings
from src.database.session import get_session_factory
from src.security.service import AuthService


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    """Return the process-scoped authentication service used by FastAPI."""

    settings = get_settings()
    return AuthService(get_session_factory(settings.database_url), settings)
