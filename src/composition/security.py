"""Construction of the authentication service graph."""

from __future__ import annotations

from functools import lru_cache

from src.config.settings import get_settings
from src.database.session import get_session_factory
from src.security.session_service import SessionRevocationService
from src.security.service import AuthService


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    """Return the process-scoped authentication service used by FastAPI."""

    settings = get_settings()
    session_factory = get_session_factory(settings.database_url)
    return AuthService(
        session_factory,
        settings,
        session_revocation=SessionRevocationService(session_factory),
    )
