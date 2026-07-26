"""Application service for PM7 notifications and operator controls."""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from uuid import UUID

from src.config.settings import get_settings
from src.database.session import get_session_factory
from src.repositories.postgres_operations import PostgresOperationsRepository
from src.security.audit import AuditContext
from src.security.permissions import Permission
from src.security.service import CurrentUser


class OperationsAuthorizationError(ValueError):
    """Raised when a caller bypasses the FastAPI permission dependency."""


class OperationsService:
    """Keep notification ownership and job permissions outside route functions."""

    def __init__(
        self,
        repository: PostgresOperationsRepository,
        *,
        worker_stale_seconds: int,
    ) -> None:
        self.repository = repository
        self.worker_stale_seconds = worker_stale_seconds

    def list_notifications(
        self,
        *,
        actor: CurrentUser,
        unread_only: bool,
        severity: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        self._require(actor, Permission.NOTIFICATIONS_READ)
        return self.repository.list_notifications(
            recipient_user_id=actor.id,
            unread_only=unread_only,
            severity=severity,
            page=page,
            page_size=page_size,
        )

    def unread_count(self, *, actor: CurrentUser) -> dict[str, int]:
        self._require(actor, Permission.NOTIFICATIONS_READ)
        return {
            "unread_count": self.repository.unread_notification_count(actor.id)
        }

    def mutate_notification(
        self,
        notification_id: UUID,
        *,
        action: str,
        expected_version: int,
        actor: CurrentUser,
    ) -> dict[str, Any]:
        self._require(actor, Permission.NOTIFICATIONS_READ)
        return self.repository.mutate_notification(
            notification_id,
            recipient_user_id=actor.id,
            action=action,
            expected_version=expected_version,
        )

    def read_all(self, *, actor: CurrentUser) -> dict[str, int]:
        self._require(actor, Permission.NOTIFICATIONS_READ)
        return {
            "updated_count": self.repository.read_all_notifications(actor.id)
        }

    def list_jobs(self, *, actor: CurrentUser) -> list[dict[str, Any]]:
        self._require(actor, Permission.JOB_OPERATIONS_READ)
        return self.repository.list_jobs()

    def set_job_enabled(
        self,
        job_key: str,
        *,
        enabled: bool,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require(actor, Permission.JOB_OPERATIONS_MANAGE)
        return self.repository.set_job_enabled(
            job_key,
            enabled=enabled,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
        )

    def trigger_job(
        self,
        job_key: str,
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require(actor, Permission.JOB_OPERATIONS_MANAGE)
        execution, created = self.repository.trigger_job(
            job_key,
            idempotency_key=idempotency_key,
            actor=actor,
            audit_context=audit_context,
        )
        return {"execution": execution, "created": created}

    def retry_execution(
        self,
        execution_id: UUID,
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require(actor, Permission.JOB_OPERATIONS_MANAGE)
        execution, created = self.repository.retry_execution(
            execution_id,
            idempotency_key=idempotency_key,
            actor=actor,
            audit_context=audit_context,
        )
        return {"execution": execution, "created": created}

    def list_executions(
        self,
        *,
        actor: CurrentUser,
        status: str | None,
        job_key: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        self._require(actor, Permission.JOB_OPERATIONS_READ)
        return self.repository.list_executions(
            status=status,
            job_key=job_key,
            page=page,
            page_size=page_size,
        )

    def list_outbox(
        self,
        *,
        actor: CurrentUser,
        status: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        self._require(actor, Permission.JOB_OPERATIONS_READ)
        return self.repository.list_outbox(
            status=status,
            page=page,
            page_size=page_size,
        )

    def metrics(self, *, actor: CurrentUser) -> dict[str, Any]:
        self._require(actor, Permission.JOB_OPERATIONS_READ)
        return self.repository.operational_metrics()

    def worker_health(self) -> dict[str, Any]:
        return self.repository.worker_health(
            stale_after_seconds=self.worker_stale_seconds
        )

    def readiness(self) -> dict[str, Any]:
        self.repository.check_health()
        worker = self.worker_health()
        return {
            "status": "ready" if worker["ready"] else "degraded",
            "database_ready": True,
            "worker_ready": worker["ready"],
            "worker": worker,
        }

    @staticmethod
    def _require(actor: CurrentUser, permission: Permission) -> None:
        if not actor.has(permission):
            raise OperationsAuthorizationError(
                "Bạn không có quyền thực hiện thao tác vận hành này."
            )


@lru_cache(maxsize=1)
def build_operations_service() -> OperationsService:
    settings = get_settings()
    if settings.storage_backend != "postgresql":
        raise RuntimeError("PM7 operations require STORAGE_BACKEND=postgresql.")
    return OperationsService(
        PostgresOperationsRepository(
            get_session_factory(settings.database_url)
        ),
        worker_stale_seconds=settings.worker_heartbeat_stale_seconds,
    )
