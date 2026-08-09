"""Explicit authentication dependency overrides for non-auth API tests."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import User
from src.security.dependencies import get_current_user
from src.security.permissions import Role, permissions_for_role
from src.security.service import CurrentUser

TEST_USER_ID = UUID("11111111-1111-4111-8111-111111111111")
TEST_SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")


def build_test_user(
    role: Role = Role.ADMINISTRATOR,
    *,
    technician_id: str | None = None,
) -> CurrentUser:
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    return CurrentUser(
        id=TEST_USER_ID,
        username="test.actor",
        email=None,
        display_name="Test actor",
        role=role,
        permissions=permissions_for_role(role),
        technician_id=technician_id,
        is_active=True,
        version=1,
        session_id=TEST_SESSION_ID,
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )


def authorize_app(app: FastAPI, user: CurrentUser | None = None) -> CurrentUser:
    actor = user or build_test_user()
    app.dependency_overrides[get_current_user] = lambda: actor
    return actor


def persist_test_user(
    session_factory: sessionmaker[Session],
    user: CurrentUser,
) -> None:
    with session_factory() as session, session.begin():
        if session.get(User, user.id) is None:
            session.add(
                User(
                    id=user.id,
                    username=user.username,
                    email=user.email,
                    password_hash="$argon2id$v=19$m=65536,t=3,p=4$invalid$invalid",
                    display_name=user.display_name,
                    role=user.role.value,
                    technician_id=user.technician_id,
                    is_active=True,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                    version=user.version,
                )
            )
