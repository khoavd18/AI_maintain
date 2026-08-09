"""Application service for PM7 notifications and operator controls."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from src.operations.metrics import api_request_metrics
from src.operations.runtime import (
    DEFAULT_OPERATIONS_RUNTIME_CONTEXT,
    DatabasePoolMetrics,
    DatabasePoolMetricsProvider,
    OperationsRuntimeContext,
)
from src.operations.compatibility import build_operations_service
from src.repositories.contracts import OperationsRepository
from src.security.audit import AuditContext
from src.security.permissions import Permission
from src.security.principal import CurrentUser


class OperationsAuthorizationError(ValueError):
    """Raised when a caller bypasses the FastAPI permission dependency."""


__all__ = ["OperationsAuthorizationError", "OperationsService", "build_operations_service"]


class OperationsService:
    """Keep notification ownership and job permissions outside route functions."""

    def __init__(
        self,
        repository: OperationsRepository,
        *,
        worker_stale_seconds: int,
        outbox_age_alert_seconds: int = 300,
        repeated_job_failure_threshold: int = 3,
        analytics_stale_seconds: int = 172800,
        backup_overdue_seconds: int = 604800,
        database_pool_metrics: DatabasePoolMetricsProvider | None = None,
        runtime_context: OperationsRuntimeContext | None = None,
    ) -> None:
        self.repository = repository
        self.worker_stale_seconds = worker_stale_seconds
        self.outbox_age_alert_seconds = outbox_age_alert_seconds
        self.repeated_job_failure_threshold = repeated_job_failure_threshold
        self.analytics_stale_seconds = analytics_stale_seconds
        self.backup_overdue_seconds = backup_overdue_seconds
        self.database_pool_metrics = database_pool_metrics
        self.runtime_context = runtime_context or DEFAULT_OPERATIONS_RUNTIME_CONTEXT

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

    def redrive_outbox_event(
        self,
        event_id: UUID,
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require(actor, Permission.JOB_OPERATIONS_MANAGE)
        event, created = self.repository.redrive_outbox_event(
            event_id,
            idempotency_key=idempotency_key,
            actor=actor,
            audit_context=audit_context,
        )
        return {"event": event, "created": created}

    def evaluate_operational_alerts(
        self, *, actor: CurrentUser
    ) -> dict[str, int]:
        self._require(actor, Permission.JOB_OPERATIONS_MANAGE)
        return self.repository.evaluate_operational_alerts(
            outbox_age_threshold_seconds=self.outbox_age_alert_seconds,
            repeated_job_failure_threshold=self.repeated_job_failure_threshold,
            analytics_stale_seconds=self.analytics_stale_seconds,
            backup_overdue_seconds=self.backup_overdue_seconds,
            worker_stale_seconds=self.worker_stale_seconds,
        )

    def metrics(self, *, actor: CurrentUser) -> dict[str, Any]:
        self._require(actor, Permission.JOB_OPERATIONS_READ)
        result = self.repository.operational_metrics()
        result["database_pool"] = self._database_pool_metrics().as_dict()
        result["api_requests"] = api_request_metrics.snapshot()
        return result

    def worker_health(self) -> dict[str, Any]:
        return self.repository.worker_health(
            stale_after_seconds=self.worker_stale_seconds
        )

    def readiness(self) -> dict[str, Any]:
        self.repository.check_health()
        worker = self.worker_health()
        runtime_context = self._runtime_context()
        return {
            "status": "ready" if worker["ready"] else "degraded",
            "database_ready": True,
            "worker_ready": worker["ready"],
            "worker": worker,
            "release": runtime_context.release_identity.as_dict(),
        }

    def _database_pool_metrics(self) -> DatabasePoolMetrics:
        if self.database_pool_metrics is None:
            raise RuntimeError("Operations database-pool metrics provider is unavailable.")
        return self.database_pool_metrics.snapshot()

    def _runtime_context(self) -> OperationsRuntimeContext:
        return self.runtime_context

    @staticmethod
    def _require(actor: CurrentUser, permission: Permission) -> None:
        if not actor.has(permission):
            raise OperationsAuthorizationError(
                "Bạn không có quyền thực hiện thao tác vận hành này."
            )
