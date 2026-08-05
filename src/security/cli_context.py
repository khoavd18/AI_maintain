"""Shared authenticated actor lookup for explicit administrative CLIs."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from src.config.settings import get_settings
from src.database.models import User
from src.database.session import get_session_factory
from src.security.permissions import Role, permissions_for_role
from src.security.service import CurrentUser


def load_cli_actor(username: str) -> CurrentUser:
    """Load one active database user as the actor for an explicit CLI command."""

    settings = get_settings()
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        user = session.scalar(select(User).where(User.username == username.strip().lower()))
        if user is None or not user.is_active:
            raise SystemExit(f"Active user not found: {username}")
        role = Role(user.role)
        return CurrentUser(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            role=role,
            permissions=permissions_for_role(role),
            technician_id=user.technician_id,
            is_active=user.is_active,
            version=user.version,
            session_id=uuid4(),
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at or datetime.now(timezone.utc),
        )
