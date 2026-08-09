"""Characterization tests for shared explicit-CLI actor loading."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from src.security import cli_context
from src.security.permissions import Permission, Role


class _FakeSession:
    def __init__(self, user: object | None, statements: list[object]) -> None:
        self.user = user
        self.statements = statements

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def scalar(self, statement: object) -> object | None:
        self.statements.append(statement)
        return self.user


def _configure_session(
    monkeypatch: pytest.MonkeyPatch,
    user: object | None,
) -> tuple[list[str], list[object]]:
    database_urls: list[str] = []
    statements: list[object] = []

    monkeypatch.setattr(
        cli_context,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql+psycopg://test/maintenance_test"),
    )

    def fake_session_factory(database_url: str):
        database_urls.append(database_url)
        return lambda: _FakeSession(user, statements)

    monkeypatch.setattr(cli_context, "get_session_factory", fake_session_factory)
    return database_urls, statements


def test_load_cli_actor_normalizes_username_and_builds_current_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    updated_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
    last_login_at = datetime(2026, 7, 3, tzinfo=timezone.utc)
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        username="manager.demo",
        email="manager@example.test",
        display_name="Quản lý demo",
        role=Role.PROPERTY_MANAGER.value,
        technician_id=None,
        is_active=True,
        version=4,
        created_at=created_at,
        updated_at=updated_at,
        last_login_at=last_login_at,
    )
    database_urls, statements = _configure_session(monkeypatch, user)

    actor = cli_context.load_cli_actor("  MANAGER.DEMO  ")

    assert database_urls == ["postgresql+psycopg://test/maintenance_test"]
    assert len(statements) == 1
    assert "manager.demo" in statements[0].compile().params.values()
    assert actor.id == user_id
    assert actor.username == "manager.demo"
    assert actor.email == "manager@example.test"
    assert actor.display_name == "Quản lý demo"
    assert actor.role is Role.PROPERTY_MANAGER
    assert Permission.ASSETS_READ in actor.permissions
    assert actor.technician_id is None
    assert actor.is_active is True
    assert actor.version == 4
    assert isinstance(actor.session_id, UUID)
    assert actor.created_at == created_at
    assert actor.updated_at == updated_at
    assert actor.last_login_at == last_login_at


@pytest.mark.parametrize("user", [None, SimpleNamespace(is_active=False)])
def test_load_cli_actor_rejects_missing_or_inactive_user(
    monkeypatch: pytest.MonkeyPatch,
    user: object | None,
) -> None:
    _configure_session(monkeypatch, user)

    with pytest.raises(SystemExit, match="^Active user not found: Missing.User$"):
        cli_context.load_cli_actor("Missing.User")


def test_load_cli_actor_uses_current_utc_time_when_last_login_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamp = datetime(2026, 7, 1, tzinfo=timezone.utc)
    user = SimpleNamespace(
        id=uuid4(),
        username="technician.demo",
        email=None,
        display_name="Kỹ thuật viên demo",
        role=Role.TECHNICIAN.value,
        technician_id="TECH_002",
        is_active=True,
        version=1,
        created_at=timestamp,
        updated_at=timestamp,
        last_login_at=None,
    )
    _configure_session(monkeypatch, user)
    before = datetime.now(timezone.utc)

    actor = cli_context.load_cli_actor("technician.demo")

    after = datetime.now(timezone.utc)
    assert actor.last_login_at is not None
    assert before <= actor.last_login_at <= after
