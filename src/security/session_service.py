"""PostgreSQL-backed complete single-session revocation transaction."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import RefreshSession, User
from src.repositories.contracts import StorageUnavailableError
from src.security.audit import append_security_audit
from src.security.contracts import SessionRevocationPort
from src.security.errors import CsrfValidationError
from src.security.tokens import refresh_session_id, token_hash_matches


class SessionRevocationService(SessionRevocationPort):
    """Own the complete logout transaction behind an ORM-free application port."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def logout(
        self,
        *,
        refresh_token: str | None,
        csrf_token: str | None,
        request_id: str,
    ) -> None:
        if not refresh_token:
            return
        try:
            session_id: UUID = refresh_session_id(refresh_token)
        except ValueError:
            return

        now = datetime.now(timezone.utc)
        try:
            with self.session_factory() as session, session.begin():
                refresh_session = session.get(
                    RefreshSession, session_id, with_for_update=True
                )
                if refresh_session is None or not token_hash_matches(
                    refresh_token, refresh_session.token_hash
                ):
                    return
                if not csrf_token or not token_hash_matches(
                    csrf_token, refresh_session.csrf_token_hash
                ):
                    raise CsrfValidationError("Yêu cầu đăng xuất không hợp lệ.")
                user = session.get(User, refresh_session.user_id)
                if refresh_session.revoked_at is None:
                    refresh_session.revoked_at = now
                    append_security_audit(
                        session,
                        actor=user,
                        action="auth.logout",
                        resource_type="refresh_session",
                        resource_id=str(refresh_session.id),
                        request_id=request_id,
                        outcome="success",
                    )
        except CsrfValidationError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể kết thúc phiên đăng nhập.") from exc
