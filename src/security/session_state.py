"""Pure predicates for validating persisted authentication state."""

from __future__ import annotations

from datetime import datetime

from src.database.models import RefreshSession, User
from src.security.tokens import AccessClaims


def access_state_is_valid(
    user: User | None,
    refresh_session: RefreshSession | None,
    claims: AccessClaims,
    now: datetime,
) -> bool:
    """Require current user/session state before accepting an access token."""

    return bool(
        user
        and user.is_active
        and user.version == claims.user_version
        and user.role == claims.role
        and refresh_session
        and refresh_session.user_id == user.id
        and refresh_session.revoked_at is None
        and refresh_session.expires_at > now
    )
