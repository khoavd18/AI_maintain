"""Read-only PM7 jobs, executions, outbox, notification, and health queries."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import (
    JobExecution,
    Notification,
    NotificationAlertState,
    OutboxDeliveryAttempt,
    OutboxEvent,
    ReliabilityValidationRecord,
    ScheduledJob,
    User,
    WorkerHeartbeat,
)
from src.operations.domain import JobExecutionStatus, OutboxStatus
from src.repositories.contracts import (
    IntegrityViolationError,
    RecordNotFoundError,
    StorageUnavailableError,
)
from src.security.principal import CurrentUser


class OperationsQueryRepository:
    """Own ordinary reads for durable PM7 operational state."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        job_values: Callable[..., dict[str, Any]],
        execution_values: Callable[..., dict[str, Any]],
        outbox_values: Callable[..., dict[str, Any]],
        notification_values: Callable[..., dict[str, Any]],
        current_user: Callable[..., CurrentUser],
        aware_utc: Callable[..., datetime],
        utc_now: Callable[..., datetime],
        claimable_execution_statuses: set[str],
        claimable_outbox_statuses: set[str],
    ) -> None:
        self.session_factory = session_factory
        self._job_values = job_values
        self._execution_values = execution_values
        self._outbox_values = outbox_values
        self._notification_values = notification_values
        self._current_user = current_user
        self._aware_utc = aware_utc
        self._utc_now = utc_now
        self._claimable_execution_statuses = claimable_execution_statuses
        self._claimable_outbox_statuses = claimable_outbox_statuses

    def list_jobs(self) -> list[dict[str, Any]]:
        try:
            with self.session_factory() as session:
                jobs = session.scalars(
                    select(ScheduledJob).order_by(ScheduledJob.job_key)
                ).all()
                return [self._job_values(job) for job in jobs]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể đọc danh sách background job."
            ) from exc

    def load_execution_actor(self, execution_id: UUID) -> CurrentUser:
        try:
            with self.session_factory() as session:
                execution = session.get(JobExecution, execution_id)
                if execution is None:
                    raise RecordNotFoundError(
                        f"Không tìm thấy job execution: {execution_id}"
                    )
                job = session.get(ScheduledJob, execution.job_key)
                user_id = execution.requested_by_user_id or (
                    job.run_as_user_id if job else None
                )
                user = session.get(User, user_id) if user_id else None
                if user is None or not user.is_active:
                    raise IntegrityViolationError(
                        "Background job chưa có run-as user đang hoạt động."
                    )
                return self._current_user(user)
        except (IntegrityViolationError, RecordNotFoundError):
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể tải run-as user của background job."
            ) from exc

    def list_executions(
        self,
        *,
        status: str | None,
        job_key: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        try:
            with self.session_factory() as session:
                statement = select(JobExecution)
                if status:
                    JobExecutionStatus(status)
                    statement = statement.where(JobExecution.status == status)
                if job_key:
                    statement = statement.where(JobExecution.job_key == job_key)
                total = int(
                    session.scalar(
                        select(func.count()).select_from(statement.subquery())
                    )
                    or 0
                )
                items = session.scalars(
                    statement.order_by(
                        JobExecution.created_at.desc(), JobExecution.id.desc()
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
                return {
                    "items": [self._execution_values(item) for item in items],
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                }
        except ValueError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc job executions.") from exc

    def list_outbox(
        self,
        *,
        status: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        try:
            with self.session_factory() as session:
                statement = select(OutboxEvent)
                if status:
                    OutboxStatus(status)
                    statement = statement.where(OutboxEvent.status == status)
                total = int(
                    session.scalar(
                        select(func.count()).select_from(statement.subquery())
                    )
                    or 0
                )
                items = session.scalars(
                    statement.order_by(
                        OutboxEvent.created_at.desc(), OutboxEvent.id.desc()
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
                return {
                    "items": [self._outbox_values(item) for item in items],
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                }
        except ValueError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc transactional outbox.") from exc

    def list_notifications(
        self,
        *,
        recipient_user_id: UUID,
        unread_only: bool,
        severity: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        try:
            with self.session_factory() as session:
                statement = select(Notification).where(
                    Notification.recipient_user_id == recipient_user_id,
                    Notification.dismissed_at.is_(None),
                )
                if unread_only:
                    statement = statement.where(Notification.read_at.is_(None))
                if severity:
                    if severity not in {"info", "warning", "critical"}:
                        raise ValueError("Notification severity không hợp lệ.")
                    statement = statement.where(Notification.severity == severity)
                total = int(
                    session.scalar(
                        select(func.count()).select_from(statement.subquery())
                    )
                    or 0
                )
                items = session.scalars(
                    statement.order_by(
                        Notification.created_at.desc(), Notification.id.desc()
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
                return {
                    "items": [self._notification_values(item) for item in items],
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                }
        except ValueError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc notifications.") from exc

    def unread_notification_count(self, recipient_user_id: UUID) -> int:
        try:
            with self.session_factory() as session:
                return int(
                    session.scalar(
                        select(func.count())
                        .select_from(Notification)
                        .where(
                            Notification.recipient_user_id == recipient_user_id,
                            Notification.read_at.is_(None),
                            Notification.dismissed_at.is_(None),
                        )
                    )
                    or 0
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể đọc số notification chưa xem."
            ) from exc

    def worker_health(
        self, *, stale_after_seconds: int, now: datetime | None = None
    ) -> dict[str, Any]:
        current = self._aware_utc(now or self._utc_now())
        try:
            with self.session_factory() as session:
                fresh_ready = session.scalar(
                    select(WorkerHeartbeat)
                    .where(
                        WorkerHeartbeat.status == "ready",
                        WorkerHeartbeat.last_seen_at
                        >= current - timedelta(seconds=stale_after_seconds),
                    )
                    .order_by(WorkerHeartbeat.last_seen_at.desc())
                )
                heartbeat = fresh_ready or session.scalar(
                    select(WorkerHeartbeat).order_by(
                        WorkerHeartbeat.last_seen_at.desc()
                    )
                )
                if heartbeat is None:
                    return {
                        "status": "missing",
                        "ready": False,
                        "worker_identity": None,
                        "last_seen_at": None,
                        "age_seconds": None,
                    }
                age = max(0, int((current - heartbeat.last_seen_at).total_seconds()))
                ready = heartbeat.status == "ready" and age <= stale_after_seconds
                return {
                    "status": (
                        "ready"
                        if ready
                        else (
                            heartbeat.status
                            if age <= stale_after_seconds
                            else "stale"
                        )
                    ),
                    "ready": ready,
                    "worker_identity": heartbeat.worker_identity,
                    "last_seen_at": heartbeat.last_seen_at.isoformat(),
                    "age_seconds": age,
                }
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc worker heartbeat.") from exc

    def operational_metrics(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = self._aware_utc(now or self._utc_now())
        try:
            with self.session_factory() as session:
                pending_jobs = self._count_where(
                    session,
                    JobExecution,
                    JobExecution.status.in_(self._claimable_execution_statuses),
                )
                failed_jobs = self._count_where(
                    session,
                    JobExecution,
                    JobExecution.status == JobExecutionStatus.FAILED.value,
                )
                dead_jobs = self._count_where(
                    session,
                    JobExecution,
                    JobExecution.status == JobExecutionStatus.DEAD_LETTERED.value,
                )
                pending_outbox = self._count_where(
                    session,
                    OutboxEvent,
                    OutboxEvent.status.in_(self._claimable_outbox_statuses),
                )
                dead_outbox = self._count_where(
                    session,
                    OutboxEvent,
                    OutboxEvent.status == OutboxStatus.DEAD_LETTERED.value,
                )
                active_job_leases = self._count_where(
                    session,
                    JobExecution,
                    JobExecution.status == JobExecutionStatus.RUNNING.value,
                )
                active_outbox_leases = self._count_where(
                    session,
                    OutboxEvent,
                    OutboxEvent.status == OutboxStatus.PROCESSING.value,
                )
                outbox_retry_count = int(
                    session.scalar(
                        select(func.count())
                        .select_from(OutboxDeliveryAttempt)
                        .where(OutboxDeliveryAttempt.status == "failed")
                    )
                    or 0
                )
                expired_lease_recovery_count = int(
                    session.scalar(
                        select(func.count())
                        .select_from(OutboxDeliveryAttempt)
                        .where(
                            OutboxDeliveryAttempt.safe_error_code == "lease_expired"
                        )
                    )
                    or 0
                )
                notification_creation_count = int(
                    session.scalar(select(func.count()).select_from(Notification)) or 0
                )
                active_operational_alert_count = int(
                    session.scalar(
                        select(func.count())
                        .select_from(NotificationAlertState)
                        .where(
                            NotificationAlertState.alert_type != "inventory_low_stock",
                            NotificationAlertState.is_active.is_(True),
                        )
                    )
                    or 0
                )
                oldest = session.scalar(
                    select(func.min(OutboxEvent.created_at)).where(
                        OutboxEvent.status.in_(
                            {
                                OutboxStatus.PENDING.value,
                                OutboxStatus.RETRY_SCHEDULED.value,
                                OutboxStatus.PROCESSING.value,
                            }
                        )
                    )
                )
                jobs = session.scalars(
                    select(ScheduledJob).order_by(ScheduledJob.job_key)
                ).all()
                latest_backup = session.scalar(
                    select(ReliabilityValidationRecord.performed_at)
                    .where(
                        ReliabilityValidationRecord.validation_type == "backup_restore",
                        ReliabilityValidationRecord.status == "passed",
                    )
                    .order_by(ReliabilityValidationRecord.performed_at.desc())
                )
                return {
                    "as_of": current.isoformat(),
                    "pending_job_count": pending_jobs,
                    "failed_job_count": failed_jobs,
                    "dead_letter_job_count": dead_jobs,
                    "pending_outbox_count": pending_outbox,
                    "dead_letter_outbox_count": dead_outbox,
                    "active_job_lease_count": active_job_leases,
                    "active_outbox_lease_count": active_outbox_leases,
                    "outbox_retry_count": outbox_retry_count,
                    "expired_lease_recovery_count": expired_lease_recovery_count,
                    "notification_creation_count": notification_creation_count,
                    "active_operational_alert_count": active_operational_alert_count,
                    "oldest_pending_outbox_age_seconds": (
                        max(0, int((current - oldest).total_seconds()))
                        if oldest
                        else None
                    ),
                    "last_successful_run_by_job": {
                        job.job_key: (
                            job.last_successful_run_at.isoformat()
                            if job.last_successful_run_at
                            else None
                        )
                        for job in jobs
                    },
                    "last_validated_backup_at": (
                        latest_backup.isoformat() if latest_backup else None
                    ),
                    "last_validated_backup_age_seconds": (
                        max(0, int((current - latest_backup).total_seconds()))
                        if latest_backup
                        else None
                    ),
                }
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc operational metrics.") from exc

    @staticmethod
    def _count_where(session: Session, model: Any, condition: Any) -> int:
        return int(session.scalar(select(func.count()).select_from(model).where(condition)) or 0)
