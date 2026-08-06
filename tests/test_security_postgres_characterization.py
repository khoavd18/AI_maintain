"""PostgreSQL characterization of persistent authentication state transitions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from src.config.settings import Settings
from src.database.models import AuditLog, RefreshSession, User
from src.database.session import get_session_factory
from src.repositories.contracts import StorageUnavailableError
from src.security import service as security_service_module
from src.security import session_service as session_service_module
from src.security.contracts import SessionRevocationPort
from src.security.permissions import Role
from src.security.session_service import SessionRevocationService
from src.security.service import AuthenticationError, AuthService, CsrfValidationError
from src.security.tokens import create_access_token, hash_token


PASSWORD = "Internal-Test-Password-42!"
NEW_PASSWORD = "Changed-Internal-Password-84!"
SIGNING_SECRET = "test-only-signing-secret-with-more-than-32-characters"


@pytest.fixture
def security_postgres_system(clean_postgres_database: str) -> dict[str, Any]:
    settings = Settings(
        app_environment="test",
        database_url=clean_postgres_database,
        token_signing_secret=SIGNING_SECRET,
        access_token_lifetime_minutes=15,
        refresh_session_lifetime_days=7,
    )
    session_factory = get_session_factory(clean_postgres_database)
    return {
        "auth": AuthService(session_factory, settings),
        "session_factory": session_factory,
        "settings": settings,
    }


def _bootstrap(
    auth: AuthService,
    *,
    username: str = "operator.test",
    role: Role = Role.HELPDESK,
) -> dict[str, Any]:
    return auth.bootstrap_user(
        username=username,
        email=f"{username}@example.invalid",
        password=PASSWORD,
        display_name=username,
        role=role,
    )


def _login(auth: AuthService, *, identifier: str = "operator.test"):
    return auth.login(
        identifier=identifier,
        password=PASSWORD,
        user_agent="characterization-agent",
        request_id=f"login-{uuid4()}",
    )


def _sessions(session_factory, user_id: UUID) -> list[RefreshSession]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(RefreshSession)
                .where(RefreshSession.user_id == user_id)
                .order_by(RefreshSession.created_at, RefreshSession.id)
            ).all()
        )


def _audits(session_factory, *, action: str, request_id: str | None = None) -> list[AuditLog]:
    with session_factory() as session:
        statement = select(AuditLog).where(AuditLog.action == action)
        if request_id is not None:
            statement = statement.where(AuditLog.request_id == request_id)
        return list(session.scalars(statement.order_by(AuditLog.occurred_at, AuditLog.id)).all())


@pytest.mark.postgres
def test_login_persists_hashed_session_and_success_audit(
    security_postgres_system: dict[str, Any],
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]
    user = _bootstrap(auth)

    result = auth.login(
        identifier="OPERATOR.TEST",
        password=PASSWORD,
        user_agent="  characterization-agent  ",
        request_id="login-persistence",
    )

    with session_factory() as session:
        persisted_user = session.get(User, result.user.id)
        persisted_session = session.get(RefreshSession, result.user.session_id)
        event = session.scalar(
            select(AuditLog).where(AuditLog.request_id == "login-persistence")
        )

    assert persisted_user is not None
    assert persisted_user.id == user["id"]
    assert persisted_user.last_login_at is not None
    assert persisted_session is not None
    assert persisted_session.user_id == persisted_user.id
    assert persisted_session.token_hash == hash_token(result.refresh_token)
    assert persisted_session.csrf_token_hash == hash_token(result.csrf_token)
    assert result.refresh_token not in persisted_session.token_hash
    assert result.csrf_token not in persisted_session.csrf_token_hash
    assert persisted_session.expires_at == result.refresh_expires_at
    assert persisted_session.revoked_at is None
    assert persisted_session.user_agent == "characterization-agent"
    assert event is not None
    assert event.action == "auth.login_succeeded"
    assert event.resource_id == str(result.user.session_id)
    assert event.actor_user_id == persisted_user.id
    assert event.outcome == "success"
    assert event.event_metadata is None
    assert persisted_session.created_at <= event.occurred_at


@pytest.mark.postgres
def test_failed_and_inactive_login_are_generic_and_do_not_create_sessions(
    security_postgres_system: dict[str, Any],
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]
    user = _bootstrap(auth)

    with pytest.raises(AuthenticationError) as wrong_error:
        auth.login(
            identifier="operator.test",
            password="wrong-password",
            user_agent="pytest",
            request_id="wrong-password",
        )
    with pytest.raises(AuthenticationError) as unknown_error:
        auth.login(
            identifier="unknown.test",
            password="wrong-password",
            user_agent="pytest",
            request_id="unknown-user",
        )

    with session_factory() as session, session.begin():
        session.execute(update(User).where(User.id == user["id"]).values(is_active=False))
    with pytest.raises(AuthenticationError) as inactive_error:
        auth.login(
            identifier="operator.test",
            password=PASSWORD,
            user_agent="pytest",
            request_id="inactive-user",
        )

    assert str(wrong_error.value) == str(unknown_error.value)
    assert str(unknown_error.value) == str(inactive_error.value)
    assert len(_sessions(session_factory, user["id"])) == 0
    failed_events = _audits(session_factory, action="auth.login_failed")
    assert {event.request_id for event in failed_events} == {
        "wrong-password",
        "unknown-user",
        "inactive-user",
    }
    for event in failed_events:
        assert event.event_metadata is not None
        assert "identifier_fingerprint" in event.event_metadata
        assert PASSWORD not in str(event.event_metadata)
        assert "operator.test" not in str(event.event_metadata)


@pytest.mark.postgres
def test_refresh_rotation_revokes_old_session_and_sequential_replay_is_rejected(
    security_postgres_system: dict[str, Any],
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]
    _bootstrap(auth)
    first = _login(auth)

    rotated = auth.refresh(
        refresh_token=first.refresh_token,
        csrf_token=first.csrf_token,
        user_agent="rotated-agent",
        request_id="refresh-rotation",
    )

    sessions = _sessions(session_factory, first.user.id)
    old_session = next(session for session in sessions if session.id == first.user.session_id)
    new_session = next(session for session in sessions if session.id == rotated.user.session_id)
    refreshed_events = _audits(session_factory, action="auth.refreshed")

    assert len(sessions) == 2
    assert old_session.revoked_at is not None
    assert new_session.revoked_at is None
    assert new_session.user_id == old_session.user_id == first.user.id
    assert new_session.token_hash == hash_token(rotated.refresh_token)
    assert new_session.csrf_token_hash == hash_token(rotated.csrf_token)
    assert new_session.token_hash != old_session.token_hash
    assert new_session.created_at >= old_session.created_at
    assert new_session.user_agent == "rotated-agent"
    assert not hasattr(old_session, "replaced_by")
    assert len(refreshed_events) == 1
    assert refreshed_events[0].resource_id == str(new_session.id)
    assert refreshed_events[0].event_metadata == {
        "rotated_session_id": str(old_session.id)
    }

    with pytest.raises(AuthenticationError):
        auth.refresh(
            refresh_token=first.refresh_token,
            csrf_token=first.csrf_token,
            user_agent="replay-agent",
            request_id="refresh-replay",
        )

    assert len(_sessions(session_factory, first.user.id)) == 2
    assert len(_audits(session_factory, action="auth.refreshed")) == 1


@pytest.mark.postgres
def test_failed_refresh_for_bad_csrf_expired_and_revoked_sessions_is_atomic(
    security_postgres_system: dict[str, Any],
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]
    _bootstrap(auth)
    _bootstrap(auth, username="other.test")

    active = _login(auth)
    other = _login(auth, identifier="other.test")
    with pytest.raises(CsrfValidationError):
        auth.refresh(
            refresh_token=active.refresh_token,
            csrf_token=other.csrf_token,
            user_agent="pytest",
            request_id="cross-user-csrf",
        )
    with pytest.raises(CsrfValidationError):
        auth.refresh(
            refresh_token=active.refresh_token,
            csrf_token="bad-csrf-token",
            user_agent="pytest",
            request_id="bad-csrf",
        )
    active_sessions = _sessions(session_factory, active.user.id)
    assert len(active_sessions) == 1
    assert active_sessions[0].revoked_at is None

    expired = _login(auth)
    with session_factory() as session, session.begin():
        session.execute(
            update(RefreshSession)
            .where(RefreshSession.id == expired.user.session_id)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
    with pytest.raises(AuthenticationError):
        auth.refresh(
            refresh_token=expired.refresh_token,
            csrf_token=expired.csrf_token,
            user_agent="pytest",
            request_id="expired-refresh",
        )

    revoked = _login(auth)
    with session_factory() as session, session.begin():
        session.execute(
            update(RefreshSession)
            .where(RefreshSession.id == revoked.user.session_id)
            .values(revoked_at=datetime.now(timezone.utc))
        )
    with pytest.raises(AuthenticationError):
        auth.refresh(
            refresh_token=revoked.refresh_token,
            csrf_token=revoked.csrf_token,
            user_agent="pytest",
            request_id="revoked-refresh",
        )

    sessions = _sessions(session_factory, active.user.id)
    assert len(sessions) == 3
    assert sum(session.revoked_at is None for session in sessions) == 2
    assert sum(session.revoked_at is not None for session in sessions) == 1
    assert any(session.expires_at <= datetime.now(timezone.utc) for session in sessions)
    assert not _audits(session_factory, action="auth.refreshed")


@pytest.mark.postgres
def test_logout_is_single_session_idempotent_and_isolated_between_users(
    security_postgres_system: dict[str, Any],
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]
    _bootstrap(auth, username="first.test")
    _bootstrap(auth, username="second.test")
    first = _login(auth, identifier="first.test")
    second = _login(auth, identifier="second.test")

    auth.logout(
        refresh_token=first.refresh_token,
        csrf_token=first.csrf_token,
        request_id="logout-first",
    )
    auth.logout(
        refresh_token=first.refresh_token,
        csrf_token=first.csrf_token,
        request_id="logout-first-replay",
    )
    auth.logout(
        refresh_token=create_unknown_refresh_token(),
        csrf_token=None,
        request_id="logout-missing",
    )

    first_session = _sessions(session_factory, first.user.id)[0]
    second_session = _sessions(session_factory, second.user.id)[0]
    logout_events = _audits(session_factory, action="auth.logout")
    assert first_session.revoked_at is not None
    assert second_session.revoked_at is None
    assert len(logout_events) == 1
    assert logout_events[0].request_id == "logout-first"


@pytest.mark.postgres
def test_change_password_revokes_all_sessions_and_invalid_change_is_non_mutating(
    security_postgres_system: dict[str, Any],
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]
    user = _bootstrap(auth)
    first = _login(auth)
    second = _login(auth)

    with pytest.raises(AuthenticationError):
        auth.change_password(
            actor=first.user,
            current_password="wrong-current-password",
            new_password=NEW_PASSWORD,
            request_id="password-invalid",
        )
    assert sum(session.revoked_at is None for session in _sessions(session_factory, user["id"])) == 2
    assert not _audits(session_factory, action="auth.password_changed")

    auth.change_password(
        actor=first.user,
        current_password=PASSWORD,
        new_password=NEW_PASSWORD,
        request_id="password-change",
    )
    sessions = _sessions(session_factory, user["id"])
    assert len(sessions) == 2
    assert all(session.revoked_at is not None for session in sessions)
    events = _audits(session_factory, action="auth.password_changed")
    assert len(events) == 1
    assert events[0].request_id == "password-change"
    assert events[0].event_metadata == {"sessions_revoked": True}

    with pytest.raises(AuthenticationError):
        auth.authenticate_access(first.access_token)
    with pytest.raises(AuthenticationError):
        auth.authenticate_access(second.access_token)
    changed_login = auth.login(
        identifier="operator.test",
        password=NEW_PASSWORD,
        user_agent="pytest",
        request_id="changed-password-login",
    )
    assert changed_login.user.id == user["id"]


@pytest.mark.postgres
def test_access_validation_rejects_session_user_role_and_version_mismatches(
    security_postgres_system: dict[str, Any],
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]
    _bootstrap(auth, username="admin.test", role=Role.ADMINISTRATOR)
    _bootstrap(auth, username="first.test")
    _bootstrap(auth, username="second.test")
    administrator = _login(auth, identifier="admin.test")
    first = _login(auth, identifier="first.test")
    second = _login(auth, identifier="second.test")
    settings: Settings = security_postgres_system["settings"]

    invalid_tokens = (
        create_access_token(
            user_id=first.user.id,
            session_id=first.user.session_id,
            role=Role.ADMINISTRATOR.value,
            user_version=first.user.version,
            signing_secret=settings.token_signing_secret,
            lifetime_minutes=15,
        )[0],
        create_access_token(
            user_id=first.user.id,
            session_id=first.user.session_id,
            role=first.user.role.value,
            user_version=first.user.version + 1,
            signing_secret=settings.token_signing_secret,
            lifetime_minutes=15,
        )[0],
        create_access_token(
            user_id=second.user.id,
            session_id=first.user.session_id,
            role=second.user.role.value,
            user_version=second.user.version,
            signing_secret=settings.token_signing_secret,
            lifetime_minutes=15,
        )[0],
    )
    for token in invalid_tokens:
        with pytest.raises(AuthenticationError):
            auth.authenticate_access(token)

    auth.update_user(
        actor=administrator.user,
        user_id=first.user.id,
        updates={"role": Role.PROPERTY_MANAGER.value},
        request_id="role-change-after-issuance",
    )
    with pytest.raises(AuthenticationError):
        auth.authenticate_access(first.access_token)
    assert _sessions(session_factory, first.user.id)[0].revoked_at is not None
    assert len(_audits(session_factory, action="user.role_changed")) == 1

    with session_factory() as session, session.begin():
        session.execute(update(User).where(User.id == first.user.id).values(is_active=False))
    with pytest.raises(AuthenticationError):
        auth.authenticate_access(first.access_token)


@pytest.mark.postgres
def test_refresh_failure_rolls_back_old_revocation_new_session_and_audit(
    security_postgres_system: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]
    _bootstrap(auth)
    original = _login(auth)

    def fail_audit(*args: Any, **kwargs: Any) -> None:
        raise SQLAlchemyError("characterization audit failure")

    monkeypatch.setattr(security_service_module, "_append_audit", fail_audit)
    with pytest.raises(StorageUnavailableError):
        auth.refresh(
            refresh_token=original.refresh_token,
            csrf_token=original.csrf_token,
            user_agent="pytest",
            request_id="refresh-audit-failure",
        )

    sessions = _sessions(session_factory, original.user.id)
    assert len(sessions) == 1
    assert sessions[0].id == original.user.session_id
    assert sessions[0].revoked_at is None
    assert not _audits(session_factory, action="auth.refreshed")


@pytest.mark.postgres
def test_refresh_failure_before_replacement_persistence_rolls_back_old_session(
    security_postgres_system: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]
    _bootstrap(auth)
    original = _login(auth)

    def fail_replacement(*args: Any, **kwargs: Any) -> None:
        raise SQLAlchemyError("replacement persistence failure")

    monkeypatch.setattr(auth, "_create_session_result", fail_replacement)
    with pytest.raises(StorageUnavailableError):
        auth.refresh(
            refresh_token=original.refresh_token,
            csrf_token=original.csrf_token,
            user_agent="pytest",
            request_id="replacement-failure",
        )

    sessions = _sessions(session_factory, original.user.id)
    assert len(sessions) == 1
    assert sessions[0].id == original.user.session_id
    assert sessions[0].revoked_at is None
    assert not _audits(session_factory, action="auth.refreshed")


@pytest.mark.postgres
def test_refresh_rejects_after_inactive_password_and_role_invalidation(
    security_postgres_system: dict[str, Any],
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]

    _bootstrap(auth, username="inactive.test")
    inactive = _login(auth, identifier="inactive.test")
    with session_factory() as session, session.begin():
        session.execute(
            update(User).where(User.id == inactive.user.id).values(is_active=False)
        )
    with pytest.raises(AuthenticationError):
        auth.refresh(
            refresh_token=inactive.refresh_token,
            csrf_token=inactive.csrf_token,
            user_agent="pytest",
            request_id="inactive-refresh",
        )
    assert _sessions(session_factory, inactive.user.id)[0].revoked_at is None

    _bootstrap(auth, username="password.test")
    password_user = _login(auth, identifier="password.test")
    auth.change_password(
        actor=password_user.user,
        current_password=PASSWORD,
        new_password=NEW_PASSWORD,
        request_id="refresh-password-invalidation",
    )
    with pytest.raises(AuthenticationError):
        auth.refresh(
            refresh_token=password_user.refresh_token,
            csrf_token=password_user.csrf_token,
            user_agent="pytest",
            request_id="password-invalidated-refresh",
        )
    assert _sessions(session_factory, password_user.user.id)[0].revoked_at is not None

    _bootstrap(auth, username="admin.test", role=Role.ADMINISTRATOR)
    _bootstrap(auth, username="role.test")
    administrator = _login(auth, identifier="admin.test")
    role_user = _login(auth, identifier="role.test")
    auth.update_user(
        actor=administrator.user,
        user_id=role_user.user.id,
        updates={"role": Role.PROPERTY_MANAGER.value},
        request_id="refresh-role-invalidation",
    )
    with pytest.raises(AuthenticationError):
        auth.refresh(
            refresh_token=role_user.refresh_token,
            csrf_token=role_user.csrf_token,
            user_agent="pytest",
            request_id="role-invalidated-refresh",
        )
    assert _sessions(session_factory, role_user.user.id)[0].revoked_at is not None


@pytest.mark.postgres
def test_concurrent_refresh_persists_one_replacement_and_one_audit(
    security_postgres_system: dict[str, Any],
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]
    _bootstrap(auth)
    original = _login(auth)

    def rotate(index: int) -> bool:
        try:
            auth.refresh(
                refresh_token=original.refresh_token,
                csrf_token=original.csrf_token,
                user_agent=f"concurrent-{index}",
                request_id=f"concurrent-characterization-{index}",
            )
            return True
        except AuthenticationError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(rotate, range(2)))

    assert sorted(outcomes) == [False, True]
    sessions = _sessions(session_factory, original.user.id)
    assert len(sessions) == 2
    assert sum(session.revoked_at is not None for session in sessions) == 1
    assert len(_audits(session_factory, action="auth.refreshed")) == 1


@pytest.mark.postgres
def test_bootstrap_user_is_active_and_audit_has_no_actor_or_plaintext_credentials(
    security_postgres_system: dict[str, Any],
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]

    created = auth.bootstrap_user(
        username="cli.bootstrap",
        email="CLI.BOOTSTRAP@EXAMPLE.INVALID",
        password=PASSWORD,
        display_name="CLI bootstrap",
        role=Role.ADMINISTRATOR,
    )

    with session_factory() as session:
        user = session.get(User, created["id"])
        event = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "user.created",
                AuditLog.request_id == "cli-bootstrap",
            )
        )
    assert user is not None
    assert user.is_active
    assert user.username == "cli.bootstrap"
    assert user.email == "cli.bootstrap@example.invalid"
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash
    assert event is not None
    assert event.actor_user_id is None
    assert event.actor_display_name is None
    assert event.after_state is not None
    assert PASSWORD not in str(event.after_state)


@pytest.mark.postgres
def test_logout_contract_uses_one_session_and_rolls_back_audit_failure(
    security_postgres_system: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth: AuthService = security_postgres_system["auth"]
    session_factory = security_postgres_system["session_factory"]
    _bootstrap(auth)
    successful = _login(auth)

    class CountingSessionFactory:
        def __init__(self, delegate) -> None:
            self.delegate = delegate
            self.calls = 0

        def __call__(self):
            self.calls += 1
            return self.delegate()

    counting_factory = CountingSessionFactory(session_factory)
    component: SessionRevocationPort = SessionRevocationService(counting_factory)
    component.logout(
        refresh_token=successful.refresh_token,
        csrf_token=successful.csrf_token,
        request_id="contract-logout",
    )
    assert counting_factory.calls == 1
    assert _sessions(session_factory, successful.user.id)[0].revoked_at is not None

    failing = _login(auth)

    def fail_audit(*args: Any, **kwargs: Any) -> None:
        raise SQLAlchemyError("contract audit failure")

    monkeypatch.setattr(session_service_module, "append_security_audit", fail_audit)
    with pytest.raises(StorageUnavailableError):
        component.logout(
            refresh_token=failing.refresh_token,
            csrf_token=failing.csrf_token,
            request_id="contract-logout-failure",
        )

    assert counting_factory.calls == 2
    failing_session = next(
        session
        for session in _sessions(session_factory, failing.user.id)
        if session.id == failing.user.session_id
    )
    assert failing_session.revoked_at is None
    assert not _audits(session_factory, action="auth.logout", request_id="contract-logout-failure")


def create_unknown_refresh_token() -> str:
    """Create a syntactically valid token with no persistent session row."""

    return f"{uuid4()}.{'x' * 48}"
