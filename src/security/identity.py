"""Pure identity normalization and user/principal projections."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from src.database.models import User
from src.security.errors import AuthenticationError
from src.security.permissions import ROLE_DISPLAY_NAMES, Role, permissions_for_role
from src.security.principal import CurrentUser


def normalize_identifier(value: str) -> str:
    """Normalize a login identifier and reject an empty value."""

    normalized = value.strip().casefold()
    if not normalized:
        raise AuthenticationError("Thông tin đăng nhập không hợp lệ.")
    return normalized


def normalize_optional_identifier(value: str | None) -> str | None:
    """Normalize an optional login identifier when one was supplied."""

    return normalize_identifier(value) if value else None


def normalize_optional(value: object) -> str | None:
    """Trim an optional user-facing value and convert empty text to null."""

    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def user_response_values(user: User | CurrentUser) -> dict[str, Any]:
    """Serialize identity data without credentials or session secrets."""

    role = Role(user.role)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "role": role,
        "role_display_name": ROLE_DISPLAY_NAMES[role],
        "permissions": sorted(permission.value for permission in permissions_for_role(role)),
        "technician_id": user.technician_id,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login_at": user.last_login_at,
        "version": user.version,
    }


def current_user_from_user(user: User, session_id: UUID) -> CurrentUser:
    """Build the immutable principal from persisted identity state."""

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
        session_id=session_id,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )
