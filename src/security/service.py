"""Transactional local authentication, user administration, and audit reads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import math
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.config.settings import Settings
from src.database.models import AuditLog, RefreshSession, User
from src.repositories.contracts import StorageUnavailableError
from src.security.audit import append_security_audit, safe_metadata
from src.security.contracts import SessionRevocationPort
from src.security.errors import AuthenticationError, CsrfValidationError
from src.security.identity import (
    current_user_from_user,
    normalize_identifier,
    normalize_optional,
    normalize_optional_identifier,
    user_response_values,
)
from src.security.passwords import consume_dummy_verification, hash_password, verify_password
from src.security.permissions import (
    Permission,
    Role,
)
from src.security.principal import CurrentUser
from src.security.rate_limit import LoginRateLimiter, LoginRateLimitExceededError
from src.security.session_service import SessionRevocationService
from src.security.session_state import access_state_is_valid
from src.security.tokens import (
    InvalidAccessTokenError,
    create_access_token,
    create_csrf_token,
    create_refresh_token,
    decode_access_token,
    hash_token,
    refresh_session_id,
    token_hash_matches,
)


class DuplicateUserError(ValueError):
    """Raised when a normalized login identifier already exists."""


class UserNotFoundError(ValueError):
    """Raised for an unknown user administration identifier."""


class UserConflictError(ValueError):
    """Raised for stale or unsafe user administration changes."""


@dataclass(frozen=True)
class AuthResult:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    csrf_token: str
    refresh_expires_at: datetime
    user: CurrentUser


class AuthService:
    """Keep identity business rules outside FastAPI route functions."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        session_revocation: SessionRevocationPort | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.session_revocation = session_revocation or SessionRevocationService(session_factory)
        self.rate_limiter = LoginRateLimiter(
            max_attempts=settings.login_rate_limit_attempts,
            window_seconds=settings.login_rate_limit_window_seconds,
        )

    def login(
        self,
        *,
        identifier: str,
        password: str,
        user_agent: str | None,
        request_id: str,
    ) -> AuthResult:
        normalized = normalize_identifier(identifier)
        limiter_key = _identifier_fingerprint(normalized)
        try:
            self.rate_limiter.check(limiter_key)
        except LoginRateLimitExceededError as exc:
            raise AuthenticationError("Thông tin đăng nhập không hợp lệ.") from exc

        now = _utc_now()
        invalid = False
        result: AuthResult | None = None
        try:
            with self.session_factory() as session, session.begin():
                user = session.scalar(
                    select(User).where(
                        or_(User.username == normalized, User.email == normalized)
                    )
                )
                if user is None:
                    consume_dummy_verification(password)
                    invalid = True
                else:
                    password_valid = verify_password(password, user.password_hash)
                    invalid = not password_valid or not user.is_active

                if invalid:
                    _append_audit(
                        session,
                        actor=None,
                        action="auth.login_failed",
                        resource_type="authentication",
                        resource_id=None,
                        request_id=request_id,
                        metadata={"identifier_fingerprint": limiter_key},
                        outcome="rejected",
                    )
                else:
                    user.last_login_at = now
                    session.flush()
                    result = self._create_session_result(
                        session,
                        user=user,
                        now=now,
                        user_agent=user_agent,
                    )
                    _append_audit(
                        session,
                        actor=user,
                        action="auth.login_succeeded",
                        resource_type="refresh_session",
                        resource_id=str(result.user.session_id),
                        request_id=request_id,
                        outcome="success",
                    )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể truy cập dịch vụ xác thực PostgreSQL.") from exc

        if invalid or result is None:
            self.rate_limiter.record_failure(limiter_key)
            raise AuthenticationError("Thông tin đăng nhập không hợp lệ.")
        self.rate_limiter.clear(limiter_key)
        return result

    def authenticate_access(self, access_token: str) -> CurrentUser:
        try:
            claims = decode_access_token(
                access_token,
                self.settings.token_signing_secret,
                self.settings.token_signing_previous_secret,
            )
        except InvalidAccessTokenError as exc:
            raise AuthenticationError("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.") from exc

        now = _utc_now()
        try:
            with self.session_factory() as session:
                user = session.get(User, claims.user_id)
                refresh_session = session.get(RefreshSession, claims.session_id)
                if not access_state_is_valid(user, refresh_session, claims, now):
                    raise AuthenticationError("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
                return current_user_from_user(user, claims.session_id)
        except AuthenticationError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể kiểm tra phiên đăng nhập.") from exc

    def refresh(
        self,
        *,
        refresh_token: str,
        csrf_token: str,
        user_agent: str | None,
        request_id: str,
    ) -> AuthResult:
        try:
            session_id = refresh_session_id(refresh_token)
        except ValueError as exc:
            raise AuthenticationError("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.") from exc
        now = _utc_now()
        try:
            with self.session_factory() as session, session.begin():
                old_session = session.get(RefreshSession, session_id, with_for_update=True)
                if old_session is None or not token_hash_matches(
                    refresh_token, old_session.token_hash
                ):
                    raise AuthenticationError("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
                if not csrf_token or not token_hash_matches(
                    csrf_token, old_session.csrf_token_hash
                ):
                    raise CsrfValidationError("Yêu cầu làm mới phiên không hợp lệ.")
                user = session.get(User, old_session.user_id)
                if (
                    user is None
                    or not user.is_active
                    or old_session.revoked_at is not None
                    or old_session.expires_at <= now
                ):
                    raise AuthenticationError("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")

                old_session.revoked_at = now
                result = self._create_session_result(
                    session,
                    user=user,
                    now=now,
                    user_agent=user_agent,
                )
                _append_audit(
                    session,
                    actor=user,
                    action="auth.refreshed",
                    resource_type="refresh_session",
                    resource_id=str(result.user.session_id),
                    request_id=request_id,
                    metadata={"rotated_session_id": str(old_session.id)},
                    outcome="success",
                )
                return result
        except (AuthenticationError, CsrfValidationError):
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể làm mới phiên đăng nhập.") from exc

    def logout(
        self,
        *,
        refresh_token: str | None,
        csrf_token: str | None,
        request_id: str,
    ) -> None:
        self.session_revocation.logout(
            refresh_token=refresh_token,
            csrf_token=csrf_token,
            request_id=request_id,
        )

    def change_password(
        self,
        *,
        actor: CurrentUser,
        current_password: str,
        new_password: str,
        request_id: str,
    ) -> None:
        new_hash = hash_password(new_password)
        now = _utc_now()
        invalid = False
        try:
            with self.session_factory() as session, session.begin():
                user = session.get(User, actor.id, with_for_update=True)
                if user is None or not user.is_active or not verify_password(
                    current_password, user.password_hash
                ):
                    invalid = True
                else:
                    user.password_hash = new_hash
                    session.execute(
                        update(RefreshSession)
                        .where(
                            RefreshSession.user_id == user.id,
                            RefreshSession.revoked_at.is_(None),
                        )
                        .values(revoked_at=now)
                    )
                    _append_audit(
                        session,
                        actor=user,
                        action="auth.password_changed",
                        resource_type="user",
                        resource_id=str(user.id),
                        request_id=request_id,
                        metadata={"sessions_revoked": True},
                        outcome="success",
                    )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể thay đổi mật khẩu.") from exc
        if invalid:
            raise AuthenticationError("Mật khẩu hiện tại không hợp lệ.")

    def list_users(self) -> list[dict[str, Any]]:
        try:
            with self.session_factory() as session:
                users = session.scalars(select(User).order_by(User.username)).all()
                return [user_response_values(user) for user in users]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc danh sách người dùng.") from exc

    def create_user(
        self,
        *,
        actor: CurrentUser,
        request_id: str,
        username: str,
        email: str | None,
        password: str,
        display_name: str,
        role: Role,
        technician_id: str | None,
        is_active: bool,
    ) -> dict[str, Any]:
        return self._insert_user(
            actor=actor,
            request_id=request_id,
            username=username,
            email=email,
            password=password,
            display_name=display_name,
            role=role,
            technician_id=technician_id,
            is_active=is_active,
        )

    def bootstrap_user(
        self,
        *,
        username: str,
        email: str | None,
        password: str,
        display_name: str,
        role: Role,
        technician_id: str | None = None,
    ) -> dict[str, Any]:
        """Create an explicit CLI user without requiring an existing actor."""

        return self._insert_user(
            actor=None,
            request_id="cli-bootstrap",
            username=username,
            email=email,
            password=password,
            display_name=display_name,
            role=role,
            technician_id=technician_id,
            is_active=True,
        )

    def update_user(
        self,
        *,
        actor: CurrentUser,
        user_id: UUID,
        updates: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        try:
            with self.session_factory() as session, session.begin():
                user = session.get(User, user_id, with_for_update=True)
                if user is None:
                    raise UserNotFoundError("Không tìm thấy người dùng.")
                if user.id == actor.id and updates.get("is_active") is False:
                    raise UserConflictError("Không thể tự vô hiệu hóa tài khoản đang sử dụng.")
                before = _safe_user_state(user)
                previous_role = user.role
                previous_active = user.is_active
                for field, value in updates.items():
                    if field == "role" and value is not None:
                        user.role = Role(value).value
                    elif field == "technician_id":
                        user.technician_id = normalize_optional(value)
                    elif field == "display_name" and value is not None:
                        user.display_name = str(value).strip()
                    elif field == "is_active" and value is not None:
                        user.is_active = bool(value)
                _validate_technician_mapping(Role(user.role), user.technician_id)
                session.flush()
                changed_security_state = (
                    user.role != previous_role or user.is_active != previous_active
                )
                if changed_security_state:
                    session.execute(
                        update(RefreshSession)
                        .where(
                            RefreshSession.user_id == user.id,
                            RefreshSession.revoked_at.is_(None),
                        )
                        .values(revoked_at=_utc_now())
                    )
                after = _safe_user_state(user)
                for action in _user_update_actions(before, after):
                    _append_audit(
                        session,
                        actor=actor,
                        action=action,
                        resource_type="user",
                        resource_id=str(user.id),
                        request_id=request_id,
                        before_state=before,
                        after_state=after,
                        metadata={"sessions_revoked": changed_security_state},
                        outcome="success",
                    )
                return user_response_values(user)
        except (UserNotFoundError, UserConflictError):
            raise
        except (IntegrityError, StaleDataError) as exc:
            raise UserConflictError("Người dùng đã thay đổi hoặc định danh đã được sử dụng.") from exc
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể cập nhật người dùng.") from exc

    def list_audit_logs(
        self,
        *,
        page: int,
        page_size: int,
        action: str | None,
        resource_type: str | None,
        outcome: str | None,
        actor_user_id: UUID | None,
    ) -> dict[str, Any]:
        filters = []
        if action:
            filters.append(AuditLog.action == action)
        if resource_type:
            filters.append(AuditLog.resource_type == resource_type)
        if outcome:
            filters.append(AuditLog.outcome == outcome)
        if actor_user_id:
            filters.append(AuditLog.actor_user_id == actor_user_id)
        try:
            with self.session_factory() as session:
                total = int(
                    session.scalar(select(func.count()).select_from(AuditLog).where(*filters))
                    or 0
                )
                events = session.scalars(
                    select(AuditLog)
                    .where(*filters)
                    .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
                return {
                    "items": [_audit_response_values(event) for event in events],
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": math.ceil(total / page_size) if total else 0,
                }
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc nhật ký kiểm toán.") from exc

    def record_authorization_denied(
        self,
        *,
        actor: CurrentUser,
        permission: Permission,
        request_id: str,
        resource_type: str,
    ) -> None:
        try:
            with self.session_factory() as session, session.begin():
                _append_audit(
                    session,
                    actor=actor,
                    action="authorization.denied",
                    resource_type=resource_type,
                    resource_id=None,
                    request_id=request_id,
                    metadata={"required_permission": permission.value},
                    outcome="rejected",
                )
        except (OperationalError, SQLAlchemyError):
            # Authorization remains denied even if best-effort rejected-event logging fails.
            return

    def _insert_user(
        self,
        *,
        actor: CurrentUser | None,
        request_id: str,
        username: str,
        email: str | None,
        password: str,
        display_name: str,
        role: Role,
        technician_id: str | None,
        is_active: bool,
    ) -> dict[str, Any]:
        normalized_username = normalize_identifier(username)
        normalized_email = normalize_optional_identifier(email)
        normalized_technician = normalize_optional(technician_id)
        _validate_technician_mapping(role, normalized_technician)
        password_hash = hash_password(password)
        try:
            with self.session_factory() as session, session.begin():
                user = User(
                    id=uuid4(),
                    username=normalized_username,
                    email=normalized_email,
                    password_hash=password_hash,
                    display_name=display_name.strip(),
                    role=role.value,
                    technician_id=normalized_technician,
                    is_active=is_active,
                )
                session.add(user)
                session.flush()
                _append_audit(
                    session,
                    actor=actor,
                    action="user.created",
                    resource_type="user",
                    resource_id=str(user.id),
                    request_id=request_id,
                    after_state=_safe_user_state(user),
                    outcome="success",
                )
                return user_response_values(user)
        except IntegrityError as exc:
            raise DuplicateUserError("Username, email hoặc technician_id đã được sử dụng.") from exc
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo người dùng.") from exc

    def _create_session_result(
        self,
        session: Session,
        *,
        user: User,
        now: datetime,
        user_agent: str | None,
    ) -> AuthResult:
        session_id = uuid4()
        refresh_token = create_refresh_token(session_id)
        csrf_token = create_csrf_token()
        refresh_expires_at = now + timedelta(
            days=self.settings.refresh_session_lifetime_days
        )
        session.add(
            RefreshSession(
                id=session_id,
                user_id=user.id,
                token_hash=hash_token(refresh_token),
                csrf_token_hash=hash_token(csrf_token),
                created_at=now,
                expires_at=refresh_expires_at,
                user_agent=_safe_user_agent(user_agent),
            )
        )
        access_token, access_expires_at = create_access_token(
            user_id=user.id,
            session_id=session_id,
            role=user.role,
            user_version=user.version,
            signing_secret=self.settings.token_signing_secret,
            lifetime_minutes=self.settings.access_token_lifetime_minutes,
            now=now,
        )
        return AuthResult(
            access_token=access_token,
            access_expires_at=access_expires_at,
            refresh_token=refresh_token,
            csrf_token=csrf_token,
            refresh_expires_at=refresh_expires_at,
            user=current_user_from_user(user, session_id),
        )


_append_audit = append_security_audit


def append_audit_event(
    session: Session,
    *,
    actor_user_id: UUID,
    actor_display_name: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    request_id: str,
    before_state: dict[str, object] | None = None,
    after_state: dict[str, object] | None = None,
    metadata: dict[str, Any] | None = None,
    outcome: str = "success",
) -> None:
    """Append a workflow event inside an existing business transaction."""

    session.add(
        AuditLog(
            id=uuid4(),
            actor_user_id=actor_user_id,
            actor_display_name=actor_display_name[:200],
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id[:100],
            before_state=before_state,
            after_state=after_state,
            event_metadata=safe_metadata(metadata),
            outcome=outcome,
        )
    )


def _safe_user_state(user: User) -> dict[str, object]:
    return {
        "id": str(user.id),
        "username": user.username,
        "role": user.role,
        "technician_id": user.technician_id,
        "is_active": user.is_active,
    }


def _user_update_actions(
    before: dict[str, object],
    after: dict[str, object],
) -> list[str]:
    actions: list[str] = []
    if before.get("is_active") != after.get("is_active"):
        actions.append("user.activated" if after.get("is_active") else "user.deactivated")
    if before.get("role") != after.get("role"):
        actions.append("user.role_changed")
    return actions or ["user.updated"]


def _validate_technician_mapping(role: Role, technician_id: str | None) -> None:
    if role is Role.TECHNICIAN and not technician_id:
        raise UserConflictError("Vai trò technician cần technician_id để giới hạn công việc.")


def _safe_user_agent(value: str | None) -> str | None:
    normalized = value.strip() if value else ""
    return normalized[:300] or None


def _identifier_fingerprint(identifier: str) -> str:
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:16]


def _audit_response_values(event: AuditLog) -> dict[str, Any]:
    return {
        "id": event.id,
        "occurred_at": event.occurred_at,
        "actor_user_id": event.actor_user_id,
        "actor_display_name": event.actor_display_name,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "request_id": event.request_id,
        "before_state": event.before_state,
        "after_state": event.after_state,
        "metadata": event.event_metadata,
        "outcome": event.outcome,
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
