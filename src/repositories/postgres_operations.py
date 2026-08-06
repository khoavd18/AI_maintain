"""PostgreSQL repository for jobs, outbox delivery, and in-app notifications."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.database.models import (
    JobExecution,
    Notification,
    NotificationAlertState,
    OutboxDeliveryAttempt,
    OutboxEvent,
    OutboxRedriveRequest,
    ReliabilityValidationRecord,
    ScheduledJob,
    User,
    WorkerHeartbeat,
)
from src.operations.domain import (
    EVENT_CATALOG,
    JOB_CATALOG,
    MAX_OUTBOX_ATTEMPTS,
    OUTBOX_RETRY_BACKOFF_SECONDS,
    JobExecutionStatus,
    JobType,
    OutboxStatus,
    validate_job_configuration,
)
from src.operations.outbox import enqueue_outbox_event
from src.repositories.contracts import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    RecordNotFoundError,
    StaleRecordError,
    StorageUnavailableError,
)
from src.repositories.postgres.operations.queries import OperationsQueryRepository
from src.security.audit import AuditContext
from src.security.permissions import Role, permissions_for_role
from src.security.service import CurrentUser, append_audit_event

ACTIVE_EXECUTION_STATUSES = {
    JobExecutionStatus.PENDING.value,
    JobExecutionStatus.RUNNING.value,
    JobExecutionStatus.RETRY_SCHEDULED.value,
}
CLAIMABLE_EXECUTION_STATUSES = {
    JobExecutionStatus.PENDING.value,
    JobExecutionStatus.RETRY_SCHEDULED.value,
}
CLAIMABLE_OUTBOX_STATUSES = {
    OutboxStatus.PENDING.value,
    OutboxStatus.RETRY_SCHEDULED.value,
}


class PostgresOperationsRepository:
    """Own all PM7 persistence and claim transactions."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self.queries = OperationsQueryRepository(
            session_factory,
            job_values=_job_values,
            execution_values=_execution_values,
            outbox_values=_outbox_values,
            notification_values=_notification_values,
            current_user=_current_user,
            aware_utc=_aware_utc,
            utc_now=_utc_now,
            claimable_execution_statuses=CLAIMABLE_EXECUTION_STATUSES,
            claimable_outbox_statuses=CLAIMABLE_OUTBOX_STATUSES,
        )

    def check_health(self) -> None:
        try:
            with self.session_factory() as session:
                session.execute(text("SELECT 1"))
                session.scalar(select(func.count()).select_from(ScheduledJob))
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "PostgreSQL PM7 schema is unavailable. Run Alembic migrations."
            ) from exc

    def list_jobs(self) -> list[dict[str, Any]]:
        return self.queries.list_jobs()

    def set_job_enabled(
        self,
        job_key: str,
        *,
        enabled: bool,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        try:
            with self.session_factory() as session, session.begin():
                job = session.get(ScheduledJob, job_key, with_for_update=True)
                if job is None:
                    raise RecordNotFoundError(f"Không tìm thấy background job: {job_key}")
                _require_version(job.version, expected_version, job_key)
                validate_job_configuration(
                    job.job_type,
                    interval_seconds=job.interval_seconds,
                    timezone_name=job.timezone,
                    configuration_payload=dict(job.configuration_payload),
                )
                before = _job_values(job)
                job.enabled = enabled
                if enabled:
                    job.run_as_user_id = actor.id
                    job.next_run_at = min(job.next_run_at, _utc_now())
                job.updated_at = _utc_now()
                session.flush()
                result = _job_values(job)
                _audit(
                    session,
                    audit_context,
                    action="background_job.enabled" if enabled else "background_job.disabled",
                    resource_type="scheduled_job",
                    resource_id=job_key,
                    before=before,
                    after=result,
                )
            return result
        except (RecordNotFoundError, StaleRecordError):
            raise
        except StaleDataError as exc:
            raise StaleRecordError(
                "Background job đã thay đổi. Hãy tải lại trước khi cập nhật."
            ) from exc
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể cập nhật background job."
            ) from exc

    def trigger_job(
        self,
        job_key: str,
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], bool]:
        current = _aware_utc(now or _utc_now())
        normalized_key = _manual_key(job_key, idempotency_key)
        try:
            with self.session_factory() as session, session.begin():
                job = session.get(ScheduledJob, job_key, with_for_update=True)
                if job is None:
                    raise RecordNotFoundError(f"Không tìm thấy background job: {job_key}")
                _validate_job(job)
                execution_id = uuid4()
                created_id = session.scalar(
                    insert(JobExecution)
                    .values(
                        id=execution_id,
                        job_key=job.job_key,
                        scheduled_for=current,
                        trigger_type="manual",
                        requested_by_user_id=actor.id,
                        status=JobExecutionStatus.PENDING.value,
                        attempt_number=0,
                        idempotency_key=normalized_key,
                        available_after=current,
                        correlation_id=f"job-{execution_id}",
                        created_at=current,
                        updated_at=current,
                        version=1,
                    )
                    .on_conflict_do_nothing(
                        constraint="uq_job_executions_idempotency"
                    )
                    .returning(JobExecution.id)
                )
                created = created_id is not None
                execution = session.get(
                    JobExecution, created_id or execution_id
                )
                if not created:
                    execution = session.scalar(
                        select(JobExecution).where(
                            JobExecution.idempotency_key == normalized_key
                        )
                    )
                    if (
                        execution is None
                        or execution.job_key != job_key
                        or execution.requested_by_user_id != actor.id
                    ):
                        raise DuplicateIdentifierError(
                            "Idempotency-Key đã được dùng cho manual job khác."
                        )
                if execution is None:  # pragma: no cover - insert/query invariant
                    raise IntegrityViolationError(
                        "Không thể xác nhận background job execution."
                    )
                if created:
                    _audit(
                        session,
                        audit_context,
                        action="background_job.triggered",
                        resource_type="job_execution",
                        resource_id=str(execution.id),
                        after=_execution_values(execution),
                        metadata={"job_key": job_key},
                    )
                result = _execution_values(execution)
            return result, created
        except (
            DuplicateIdentifierError,
            IntegrityViolationError,
            RecordNotFoundError,
        ):
            raise
        except IntegrityError as exc:
            raise DuplicateIdentifierError(
                "Manual background job đã được tạo với cùng idempotency key."
            ) from exc
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo manual job execution.") from exc

    def retry_execution(
        self,
        execution_id: UUID,
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], bool]:
        current = _aware_utc(now or _utc_now())
        normalized_key = _manual_key(f"retry-{execution_id}", idempotency_key)
        try:
            with self.session_factory() as session, session.begin():
                source = session.get(JobExecution, execution_id, with_for_update=True)
                if source is None:
                    raise RecordNotFoundError(
                        f"Không tìm thấy job execution: {execution_id}"
                    )
                if source.status not in {
                    JobExecutionStatus.FAILED.value,
                    JobExecutionStatus.DEAD_LETTERED.value,
                }:
                    raise IntegrityViolationError(
                        "Chỉ execution failed hoặc dead-lettered mới có thể retry thủ công."
                    )
                new_id = uuid4()
                created_id = session.scalar(
                    insert(JobExecution)
                    .values(
                        id=new_id,
                        job_key=source.job_key,
                        scheduled_for=current,
                        trigger_type="manual",
                        requested_by_user_id=actor.id,
                        status=JobExecutionStatus.PENDING.value,
                        attempt_number=0,
                        idempotency_key=normalized_key,
                        available_after=current,
                        correlation_id=f"job-{new_id}",
                        execution_summary={"retry_of_execution_id": str(source.id)},
                        created_at=current,
                        updated_at=current,
                        version=1,
                    )
                    .on_conflict_do_nothing(
                        constraint="uq_job_executions_idempotency"
                    )
                    .returning(JobExecution.id)
                )
                created = created_id is not None
                execution = (
                    session.get(JobExecution, created_id)
                    if created_id
                    else session.scalar(
                        select(JobExecution).where(
                            JobExecution.idempotency_key == normalized_key
                        )
                    )
                )
                if (
                    execution is None
                    or execution.job_key != source.job_key
                    or execution.requested_by_user_id != actor.id
                ):
                    raise DuplicateIdentifierError(
                        "Idempotency-Key đã được dùng cho retry khác."
                    )
                if created:
                    _audit(
                        session,
                        audit_context,
                        action="background_job.retry_requested",
                        resource_type="job_execution",
                        resource_id=str(execution.id),
                        after=_execution_values(execution),
                        metadata={"retry_of_execution_id": str(source.id)},
                    )
                result = _execution_values(execution)
            return result, created
        except (
            DuplicateIdentifierError,
            IntegrityViolationError,
            RecordNotFoundError,
        ):
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể retry job execution.") from exc

    def materialize_due_jobs(
        self, *, now: datetime | None = None, limit: int = 20
    ) -> dict[str, int]:
        current = _aware_utc(now or _utc_now())
        created_count = 0
        skipped_count = 0
        try:
            with self.session_factory() as session, session.begin():
                jobs = session.scalars(
                    select(ScheduledJob)
                    .where(
                        ScheduledJob.enabled.is_(True),
                        ScheduledJob.run_as_user_id.is_not(None),
                        ScheduledJob.next_run_at <= current,
                    )
                    .order_by(ScheduledJob.next_run_at, ScheduledJob.job_key)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                ).all()
                for job in jobs:
                    _validate_job(job)
                    scheduled_for = job.next_run_at
                    key = f"schedule:{job.job_key}:{scheduled_for.isoformat()}"
                    active = session.scalar(
                        select(JobExecution.id)
                        .where(
                            JobExecution.job_key == job.job_key,
                            JobExecution.status.in_(ACTIVE_EXECUTION_STATUSES),
                        )
                        .limit(1)
                    )
                    execution_id = uuid4()
                    status = (
                        JobExecutionStatus.SKIPPED.value
                        if active is not None
                        else JobExecutionStatus.PENDING.value
                    )
                    summary = (
                        {"reason": "concurrency_policy_forbid_overlap"}
                        if active is not None
                        else None
                    )
                    created_id = session.scalar(
                        insert(JobExecution)
                        .values(
                            id=execution_id,
                            job_key=job.job_key,
                            scheduled_for=scheduled_for,
                            trigger_type="scheduled",
                            requested_by_user_id=None,
                            status=status,
                            attempt_number=0,
                            idempotency_key=key,
                            available_after=current,
                            completed_at=current if active is not None else None,
                            execution_summary=summary,
                            correlation_id=f"job-{execution_id}",
                            created_at=current,
                            updated_at=current,
                            version=1,
                        )
                        .on_conflict_do_nothing(
                            constraint="uq_job_executions_idempotency"
                        )
                        .returning(JobExecution.id)
                    )
                    if created_id is not None:
                        if active is None:
                            created_count += 1
                        else:
                            skipped_count += 1
                    job.next_run_at = _next_due(
                        scheduled_for, job.interval_seconds, current
                    )
                    job.updated_at = current
            return {"created_count": created_count, "skipped_count": skipped_count}
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể lập lịch background job.") from exc

    def recover_expired_execution_leases(
        self, *, now: datetime | None = None, limit: int = 100
    ) -> int:
        current = _aware_utc(now or _utc_now())
        recovered = 0
        try:
            with self.session_factory() as session, session.begin():
                executions = session.scalars(
                    select(JobExecution)
                    .where(
                        JobExecution.status == JobExecutionStatus.RUNNING.value,
                        JobExecution.lease_expires_at < current,
                    )
                    .order_by(JobExecution.lease_expires_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                ).all()
                for execution in executions:
                    job = session.get(ScheduledJob, execution.job_key)
                    if job is None:  # pragma: no cover - protected by FK
                        continue
                    _schedule_execution_failure(
                        execution,
                        job,
                        current=current,
                        error_code="lease_expired",
                        error_summary="Worker lease hết hạn trước khi tác vụ hoàn tất.",
                    )
                    recovered += 1
            return recovered
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể khôi phục execution lease.") from exc

    def claim_execution(
        self,
        *,
        worker_identity: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        current = _aware_utc(now or _utc_now())
        worker = _worker_identity(worker_identity)
        try:
            with self.session_factory() as session, session.begin():
                candidates = session.scalars(
                    select(JobExecution)
                    .where(
                        JobExecution.status.in_(CLAIMABLE_EXECUTION_STATUSES),
                        JobExecution.available_after <= current,
                    )
                    .order_by(
                        JobExecution.available_after,
                        JobExecution.scheduled_for,
                        JobExecution.created_at,
                    )
                    .limit(20)
                    .with_for_update(skip_locked=True)
                ).all()
                for execution in candidates:
                    job = session.get(ScheduledJob, execution.job_key)
                    if job is None:  # pragma: no cover - protected by FK
                        continue
                    if execution.trigger_type == "scheduled" and not job.enabled:
                        execution.status = JobExecutionStatus.CANCELLED.value
                        execution.completed_at = current
                        execution.execution_summary = {
                            "reason": "job_disabled_before_claim"
                        }
                        execution.updated_at = current
                        continue
                    overlapping = session.scalar(
                        select(JobExecution.id)
                        .where(
                            JobExecution.job_key == execution.job_key,
                            JobExecution.id != execution.id,
                            JobExecution.status == JobExecutionStatus.RUNNING.value,
                            JobExecution.lease_expires_at >= current,
                        )
                        .limit(1)
                    )
                    if overlapping is not None:
                        continue
                    execution.status = JobExecutionStatus.RUNNING.value
                    execution.attempt_number += 1
                    execution.worker_identity = worker
                    execution.started_at = execution.started_at or current
                    execution.completed_at = None
                    execution.lease_expires_at = current + timedelta(
                        seconds=job.lease_seconds
                    )
                    execution.updated_at = current
                    session.flush()
                    result = _execution_values(execution)
                    result["job_type"] = job.job_type
                    result["actor_user_id"] = str(
                        execution.requested_by_user_id or job.run_as_user_id
                    )
                    result["max_attempts"] = job.max_attempts
                    result["retry_backoff_seconds"] = job.retry_backoff_seconds
                    return result
            return None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể claim background job.") from exc

    def complete_execution(
        self,
        execution_id: UUID,
        *,
        worker_identity: str,
        summary: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _aware_utc(now or _utc_now())
        worker = _worker_identity(worker_identity)
        try:
            with self.session_factory() as session, session.begin():
                execution = _locked_running_execution(
                    session, execution_id, worker_identity=worker
                )
                job = session.get(
                    ScheduledJob, execution.job_key, with_for_update=True
                )
                if job is None:  # pragma: no cover - protected by FK
                    raise RecordNotFoundError(f"Không tìm thấy job: {execution.job_key}")
                execution.status = JobExecutionStatus.SUCCEEDED.value
                execution.completed_at = current
                execution.execution_summary = _bounded_summary(summary)
                execution.safe_error_code = None
                execution.safe_error_summary = None
                execution.lease_expires_at = None
                execution.updated_at = current
                job.last_successful_run_at = current
                job.updated_at = current
                session.flush()
                return _execution_values(execution)
        except (IntegrityViolationError, RecordNotFoundError):
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể hoàn tất background job execution."
            ) from exc

    def renew_execution_lease(
        self,
        execution_id: UUID,
        *,
        worker_identity: str,
        now: datetime | None = None,
    ) -> None:
        current = _aware_utc(now or _utc_now())
        worker = _worker_identity(worker_identity)
        try:
            with self.session_factory() as session, session.begin():
                execution = _locked_running_execution(
                    session, execution_id, worker_identity=worker
                )
                job = session.get(ScheduledJob, execution.job_key)
                if job is None:  # pragma: no cover - protected by FK
                    raise RecordNotFoundError(
                        f"Không tìm thấy job: {execution.job_key}"
                    )
                execution.lease_expires_at = current + timedelta(
                    seconds=job.lease_seconds
                )
                execution.updated_at = current
        except (IntegrityViolationError, RecordNotFoundError):
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể gia hạn background job lease."
            ) from exc

    def fail_execution(
        self,
        execution_id: UUID,
        *,
        worker_identity: str,
        error_code: str,
        error_summary: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _aware_utc(now or _utc_now())
        worker = _worker_identity(worker_identity)
        try:
            with self.session_factory() as session, session.begin():
                execution = _locked_running_execution(
                    session, execution_id, worker_identity=worker
                )
                job = session.get(ScheduledJob, execution.job_key)
                if job is None:  # pragma: no cover - protected by FK
                    raise RecordNotFoundError(f"Không tìm thấy job: {execution.job_key}")
                _schedule_execution_failure(
                    execution,
                    job,
                    current=current,
                    error_code=error_code,
                    error_summary=error_summary,
                )
                if (
                    job.job_type == JobType.ANALYTICS_REFRESH.value
                    and execution.status == JobExecutionStatus.DEAD_LETTERED.value
                ):
                    enqueue_outbox_event(
                        session,
                        event_type="analytics.refresh_failed",
                        aggregate_type="job_execution",
                        aggregate_id=str(execution.id),
                        payload={
                            "execution_id": str(execution.id),
                            "error_code": execution.safe_error_code or "analytics_failed",
                        },
                        idempotency_key=f"job-result:{execution.id}:analytics-failed",
                    )
                session.flush()
                return _execution_values(execution)
        except (IntegrityViolationError, RecordNotFoundError):
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể ghi nhận background job failure."
            ) from exc

    def load_execution_actor(self, execution_id: UUID) -> CurrentUser:
        return self.queries.load_execution_actor(execution_id)

    def list_executions(
        self,
        *,
        status: str | None,
        job_key: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.queries.list_executions(
            status=status,
            job_key=job_key,
            page=page,
            page_size=page_size,
        )

    def list_outbox(
        self,
        *,
        status: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.queries.list_outbox(
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
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Create one audited, caller-idempotent retry cycle for a dead letter."""

        current = _aware_utc(now or _utc_now())
        normalized_key = _manual_key(f"outbox-redrive-{event_id}", idempotency_key)
        try:
            with self.session_factory() as session, session.begin():
                existing = session.scalar(
                    select(OutboxRedriveRequest).where(
                        OutboxRedriveRequest.idempotency_key == normalized_key
                    )
                )
                if existing is not None:
                    if (
                        existing.outbox_event_id != event_id
                        or existing.requested_by_user_id != actor.id
                    ):
                        raise DuplicateIdentifierError(
                            "Idempotency-Key đã được dùng cho yêu cầu retry khác."
                        )
                    event = session.get(OutboxEvent, event_id)
                    if event is None:  # pragma: no cover - protected by FK
                        raise RecordNotFoundError(
                            f"Không tìm thấy outbox event: {event_id}"
                        )
                    return _outbox_values(event), False

                event = session.get(OutboxEvent, event_id, with_for_update=True)
                if event is None:
                    raise RecordNotFoundError(
                        f"Không tìm thấy outbox event: {event_id}"
                    )
                existing = session.scalar(
                    select(OutboxRedriveRequest).where(
                        OutboxRedriveRequest.idempotency_key == normalized_key
                    )
                )
                if existing is not None:
                    if (
                        existing.outbox_event_id != event_id
                        or existing.requested_by_user_id != actor.id
                    ):
                        raise DuplicateIdentifierError(
                            "Idempotency-Key đã được dùng cho yêu cầu retry khác."
                        )
                    return _outbox_values(event), False
                if event.status != OutboxStatus.DEAD_LETTERED.value:
                    raise IntegrityViolationError(
                        "Chỉ outbox event dead-lettered mới có thể retry thủ công."
                    )
                prior_attempts = event.attempt_count
                next_redrive = event.redrive_count + 1
                session.add(
                    OutboxRedriveRequest(
                        id=uuid4(),
                        outbox_event_id=event.id,
                        requested_by_user_id=actor.id,
                        idempotency_key=normalized_key,
                        prior_attempt_count=prior_attempts,
                        redrive_number=next_redrive,
                        request_id=audit_context.request_id,
                        requested_at=current,
                    )
                )
                event.redrive_count = next_redrive
                event.attempt_count = 0
                event.status = OutboxStatus.RETRY_SCHEDULED.value
                event.available_after = current
                event.lease_owner = None
                event.lease_expires_at = None
                event.processed_at = None
                event.last_safe_error_code = None
                event.last_safe_error_summary = None
                event.updated_at = current
                session.flush()
                result = _outbox_values(event)
                _audit(
                    session,
                    audit_context,
                    action="outbox.dead_letter_retry_requested",
                    resource_type="outbox_event",
                    resource_id=str(event.id),
                    after=result,
                    metadata={
                        "redrive_number": next_redrive,
                        "prior_attempt_count": prior_attempts,
                    },
                )
                return result, True
        except (
            DuplicateIdentifierError,
            IntegrityViolationError,
            RecordNotFoundError,
        ):
            raise
        except IntegrityError as exc:
            raise DuplicateIdentifierError(
                "Yêu cầu retry outbox trùng hoặc đang được xử lý."
            ) from exc
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể tạo yêu cầu retry outbox."
            ) from exc

    def evaluate_operational_alerts(
        self,
        *,
        outbox_age_threshold_seconds: int,
        repeated_job_failure_threshold: int,
        analytics_stale_seconds: int,
        backup_overdue_seconds: int,
        worker_stale_seconds: int,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Update deduplicated alert cycles from safe aggregate conditions."""

        current = _aware_utc(now or _utc_now())
        conditions = self._operational_conditions(
            current=current,
            outbox_age_threshold_seconds=outbox_age_threshold_seconds,
            repeated_job_failure_threshold=repeated_job_failure_threshold,
            analytics_stale_seconds=analytics_stale_seconds,
            backup_overdue_seconds=backup_overdue_seconds,
            worker_stale_seconds=worker_stale_seconds,
        )
        raised = 0
        recovered = 0
        try:
            with self.session_factory() as session, session.begin():
                for condition in conditions:
                    session.execute(
                        insert(NotificationAlertState)
                        .values(
                            id=uuid4(),
                            alert_type=condition["alert_type"],
                            entity_key=condition["entity_key"],
                            is_active=False,
                            cycle_number=0,
                            updated_at=current,
                            version=1,
                        )
                        .on_conflict_do_nothing(
                            index_elements=["alert_type", "entity_key"]
                        )
                    )
                    state = session.scalar(
                        select(NotificationAlertState)
                        .where(
                            NotificationAlertState.alert_type
                            == condition["alert_type"],
                            NotificationAlertState.entity_key
                            == condition["entity_key"],
                        )
                        .with_for_update()
                    )
                    if state is None:  # pragma: no cover - protected by insert/select
                        raise RuntimeError("Operational alert state was not persisted.")
                    breached = bool(condition["breached"])
                    observed = int(condition["observed_value"])
                    threshold = int(condition["threshold_value"])
                    details = {
                        "observed_value": observed,
                        "threshold_value": threshold,
                    }
                    if breached and not state.is_active:
                        state.is_active = True
                        state.cycle_number += 1
                        state.last_detected_at = current
                        event_type = "operations.alert_raised"
                        raised += 1
                    elif not breached and state.is_active:
                        state.is_active = False
                        state.last_recovered_at = current
                        event_type = "operations.alert_recovered"
                        recovered += 1
                    else:
                        if breached:
                            state.last_detected_at = current
                        state.last_details = details
                        state.updated_at = current
                        continue
                    state.last_details = details
                    state.updated_at = current
                    payload = {
                        "alert_type": condition["alert_type"],
                        "alert_name": condition["alert_name"],
                        "entity_key": condition["entity_key"],
                        "cycle_number": state.cycle_number,
                        "observed_value": observed,
                        "threshold_value": threshold,
                    }
                    enqueue_outbox_event(
                        session,
                        event_type=event_type,
                        aggregate_type="operational_alert",
                        aggregate_id=(
                            f"{condition['alert_type']}:{condition['entity_key']}"
                        )[:120],
                        payload=payload,
                        idempotency_key=(
                            f"operational-alert:{condition['alert_type']}:"
                            f"{condition['entity_key']}:{state.cycle_number}:{event_type}"
                        )[:200],
                    )
            return {
                "evaluated_count": len(conditions),
                "raised_count": raised,
                "recovered_count": recovered,
            }
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể đánh giá cảnh báo độ tin cậy."
            ) from exc

    def _operational_conditions(
        self,
        *,
        current: datetime,
        outbox_age_threshold_seconds: int,
        repeated_job_failure_threshold: int,
        analytics_stale_seconds: int,
        backup_overdue_seconds: int,
        worker_stale_seconds: int,
    ) -> list[dict[str, Any]]:
        try:
            with self.session_factory() as session:
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
                oldest_age = (
                    max(0, int((current - oldest).total_seconds())) if oldest else 0
                )
                dead_letters = _count_where(
                    session,
                    OutboxEvent,
                    OutboxEvent.status == OutboxStatus.DEAD_LETTERED.value,
                ) + _count_where(
                    session,
                    JobExecution,
                    JobExecution.status == JobExecutionStatus.DEAD_LETTERED.value,
                )
                latest_heartbeat = session.scalar(
                    select(WorkerHeartbeat).order_by(
                        WorkerHeartbeat.last_seen_at.desc()
                    )
                )
                heartbeat_age = (
                    max(
                        0,
                        int(
                            (current - latest_heartbeat.last_seen_at).total_seconds()
                        ),
                    )
                    if latest_heartbeat
                    else worker_stale_seconds + 1
                )
                analytics = session.get(
                    ScheduledJob, JobType.ANALYTICS_REFRESH.value
                )
                analytics_age = 0
                analytics_breached = False
                if analytics and analytics.enabled:
                    reference = (
                        analytics.last_successful_run_at or analytics.created_at
                    )
                    analytics_age = max(
                        0, int((current - reference).total_seconds())
                    )
                    analytics_breached = analytics_age > analytics_stale_seconds
                latest_backup = session.scalar(
                    select(ReliabilityValidationRecord)
                    .where(
                        ReliabilityValidationRecord.validation_type
                        == "backup_restore",
                        ReliabilityValidationRecord.status == "passed",
                    )
                    .order_by(ReliabilityValidationRecord.performed_at.desc())
                )
                backup_age = (
                    max(
                        0,
                        int((current - latest_backup.performed_at).total_seconds()),
                    )
                    if latest_backup
                    else backup_overdue_seconds + 1
                )
                conditions: list[dict[str, Any]] = [
                    _alert_condition(
                        "worker_heartbeat_stale",
                        "primary",
                        "Worker heartbeat quá hạn",
                        heartbeat_age,
                        worker_stale_seconds,
                    ),
                    _alert_condition(
                        "outbox_backlog_old",
                        "primary",
                        "Outbox tồn đọng quá lâu",
                        oldest_age,
                        outbox_age_threshold_seconds,
                    ),
                    _alert_condition(
                        "dead_letter_present",
                        "primary",
                        "Có bản ghi dead-letter chưa xử lý",
                        dead_letters,
                        0,
                    ),
                    _alert_condition(
                        "analytics_refresh_stale",
                        "analytics_refresh",
                        "Analytics chưa được làm mới đúng hạn",
                        analytics_age,
                        analytics_stale_seconds,
                        breached=analytics_breached,
                    ),
                    _alert_condition(
                        "backup_validation_overdue",
                        "backup_restore",
                        "Backup chưa được restore-validate đúng hạn",
                        backup_age,
                        backup_overdue_seconds,
                    ),
                ]
                for job in session.scalars(
                    select(ScheduledJob).order_by(ScheduledJob.job_key)
                ).all():
                    recent_statuses = session.scalars(
                        select(JobExecution.status)
                        .where(JobExecution.job_key == job.job_key)
                        .order_by(JobExecution.created_at.desc())
                        .limit(repeated_job_failure_threshold)
                    ).all()
                    consecutive_failures = 0
                    for status in recent_statuses:
                        if status not in {
                            JobExecutionStatus.FAILED.value,
                            JobExecutionStatus.DEAD_LETTERED.value,
                        }:
                            break
                        consecutive_failures += 1
                    conditions.append(
                        _alert_condition(
                            "scheduled_job_repeated_failure",
                            job.job_key,
                            f"Job {job.job_key} lỗi liên tiếp",
                            consecutive_failures,
                            repeated_job_failure_threshold,
                            breached=(
                                consecutive_failures
                                >= repeated_job_failure_threshold
                            ),
                        )
                    )
                return conditions
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể đọc điều kiện cảnh báo độ tin cậy."
            ) from exc

    def recover_expired_outbox_leases(
        self, *, now: datetime | None = None, limit: int = 100
    ) -> int:
        current = _aware_utc(now or _utc_now())
        recovered = 0
        try:
            with self.session_factory() as session, session.begin():
                events = session.scalars(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.status == OutboxStatus.PROCESSING.value,
                        OutboxEvent.lease_expires_at < current,
                    )
                    .order_by(OutboxEvent.lease_expires_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                ).all()
                for event in events:
                    _record_delivery_attempt(
                        session,
                        event,
                        worker_identity=event.lease_owner or "expired-worker",
                        status="failed",
                        error_code="lease_expired",
                        error_summary="Outbox lease hết hạn trước khi xử lý hoàn tất.",
                        now=current,
                    )
                    _schedule_outbox_failure(
                        event,
                        current=current,
                        error_code="lease_expired",
                        error_summary="Outbox lease hết hạn trước khi xử lý hoàn tất.",
                    )
                    recovered += 1
            return recovered
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể khôi phục outbox lease.") from exc

    def claim_outbox_event(
        self,
        *,
        worker_identity: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        current = _aware_utc(now or _utc_now())
        worker = _worker_identity(worker_identity)
        if not 30 <= lease_seconds <= 3600:
            raise ValueError("Outbox lease phải nằm trong 30–3600 giây.")
        try:
            with self.session_factory() as session, session.begin():
                event = session.scalar(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.status.in_(CLAIMABLE_OUTBOX_STATUSES),
                        OutboxEvent.available_after <= current,
                    )
                    .order_by(OutboxEvent.available_after, OutboxEvent.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                if event is None:
                    return None
                event.status = OutboxStatus.PROCESSING.value
                event.attempt_count += 1
                event.lease_owner = worker
                event.lease_expires_at = current + timedelta(seconds=lease_seconds)
                event.updated_at = current
                session.flush()
                return _outbox_values(event, include_payload=True)
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể claim outbox event.") from exc

    def deliver_outbox_event(
        self,
        event_id: UUID,
        *,
        worker_identity: str,
        now: datetime | None = None,
    ) -> dict[str, int]:
        current = _aware_utc(now or _utc_now())
        worker = _worker_identity(worker_identity)
        try:
            with self.session_factory() as session, session.begin():
                event = session.get(OutboxEvent, event_id, with_for_update=True)
                if event is None:
                    raise RecordNotFoundError(f"Không tìm thấy outbox event: {event_id}")
                _require_outbox_owner(event, worker)
                spec = EVENT_CATALOG.get(event.event_type)
                if spec is None:
                    raise IntegrityViolationError(
                        f"Unsupported outbox event type: {event.event_type}"
                    )
                recipients = _resolve_recipients(
                    session, event.payload, spec.recipient_roles, spec.explicit_recipient_fields
                )
                created_count = 0
                related_id = _related_entity_id(
                    spec.related_entity_type, event.payload, event.aggregate_id
                )
                for recipient_id in sorted(recipients, key=str):
                    notification_id = uuid4()
                    created_id = session.scalar(
                        insert(Notification)
                        .values(
                            id=notification_id,
                            recipient_user_id=recipient_id,
                            notification_type=event.event_type,
                            title=spec.title,
                            body=spec.body_template.format_map(event.payload),
                            structured_content=_notification_content(event.payload),
                            severity=spec.severity.value,
                            related_entity_type=spec.related_entity_type,
                            related_entity_id=related_id,
                            created_at=current,
                            deduplication_key=f"{event.id}:{recipient_id}",
                            source_outbox_event_id=event.id,
                            version=1,
                        )
                        .on_conflict_do_nothing(
                            constraint="uq_notifications_recipient_dedup"
                        )
                        .returning(Notification.id)
                    )
                    created_count += int(created_id is not None)
                _record_delivery_attempt(
                    session,
                    event,
                    worker_identity=worker,
                    status="succeeded",
                    error_code=None,
                    error_summary=None,
                    now=current,
                )
                event.status = OutboxStatus.PROCESSED.value
                event.processed_at = current
                event.lease_owner = None
                event.lease_expires_at = None
                event.last_safe_error_code = None
                event.last_safe_error_summary = None
                event.updated_at = current
                return {
                    "recipient_count": len(recipients),
                    "created_notification_count": created_count,
                }
        except (IntegrityViolationError, RecordNotFoundError):
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể xử lý outbox event.") from exc

    def fail_outbox_event(
        self,
        event_id: UUID,
        *,
        worker_identity: str,
        error_code: str,
        error_summary: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _aware_utc(now or _utc_now())
        worker = _worker_identity(worker_identity)
        try:
            with self.session_factory() as session, session.begin():
                event = session.get(OutboxEvent, event_id, with_for_update=True)
                if event is None:
                    raise RecordNotFoundError(f"Không tìm thấy outbox event: {event_id}")
                _require_outbox_owner(event, worker)
                _record_delivery_attempt(
                    session,
                    event,
                    worker_identity=worker,
                    status="failed",
                    error_code=error_code,
                    error_summary=error_summary,
                    now=current,
                )
                _schedule_outbox_failure(
                    event,
                    current=current,
                    error_code=error_code,
                    error_summary=error_summary,
                )
                session.flush()
                return _outbox_values(event)
        except (IntegrityViolationError, RecordNotFoundError):
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể ghi nhận outbox failure.") from exc

    def record_low_stock_cycles(
        self,
        *,
        low_stock_items: list[dict[str, Any]],
        observed_entity_keys: set[str],
        execution_id: UUID,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _aware_utc(now or _utc_now())
        created_count = 0
        recovered_count = 0
        try:
            with self.session_factory() as session, session.begin():
                states = {
                    state.entity_key: state
                    for state in session.scalars(
                        select(NotificationAlertState)
                        .where(
                            NotificationAlertState.alert_type
                            == "inventory_low_stock"
                        )
                        .with_for_update()
                    ).all()
                }
                low_keys: set[str] = set()
                for item in low_stock_items:
                    key = _inventory_entity_key(item)
                    if key not in observed_entity_keys:
                        raise IntegrityViolationError(
                            f"Low-stock entity was not present in observed balances: {key}"
                        )
                    low_keys.add(key)
                    state = states.get(key)
                    if state is None:
                        state = NotificationAlertState(
                            id=uuid4(),
                            alert_type="inventory_low_stock",
                            entity_key=key,
                            is_active=False,
                            cycle_number=0,
                            updated_at=current,
                            version=1,
                        )
                        session.add(state)
                        session.flush()
                        states[key] = state
                    details = _low_stock_payload(item, state.cycle_number)
                    if not state.is_active:
                        state.is_active = True
                        state.cycle_number += 1
                        state.last_detected_at = current
                        details["cycle_number"] = state.cycle_number
                        enqueue_outbox_event(
                            session,
                            event_type="inventory.stock_below_reorder",
                            aggregate_type="inventory_position",
                            aggregate_id=key,
                            payload=details,
                            idempotency_key=(
                                f"inventory-low:{key}:cycle:{state.cycle_number}"
                            ),
                        )
                        created_count += 1
                    state.last_details = details
                    state.updated_at = current
                for key, state in states.items():
                    if (
                        state.is_active
                        and key in observed_entity_keys
                        and key not in low_keys
                    ):
                        state.is_active = False
                        state.last_recovered_at = current
                        state.updated_at = current
                        recovered_count += 1
                session.flush()
            return {
                "alert_candidate_count": created_count,
                "recovered_count": recovered_count,
                "low_stock_count": len(low_keys),
                "observed_position_count": len(observed_entity_keys),
                "execution_id": str(execution_id),
            }
        except IntegrityViolationError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể cập nhật low-stock alert cycle."
            ) from exc

    def list_notifications(
        self,
        *,
        recipient_user_id: UUID,
        unread_only: bool,
        severity: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.queries.list_notifications(
            recipient_user_id=recipient_user_id,
            unread_only=unread_only,
            severity=severity,
            page=page,
            page_size=page_size,
        )

    def unread_notification_count(self, recipient_user_id: UUID) -> int:
        return self.queries.unread_notification_count(recipient_user_id)

    def mutate_notification(
        self,
        notification_id: UUID,
        *,
        recipient_user_id: UUID,
        action: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _aware_utc(now or _utc_now())
        if action not in {"read", "unread", "dismiss"}:
            raise ValueError("Notification action không được hỗ trợ.")
        try:
            with self.session_factory() as session, session.begin():
                notification = session.get(
                    Notification, notification_id, with_for_update=True
                )
                if (
                    notification is None
                    or notification.recipient_user_id != recipient_user_id
                ):
                    raise RecordNotFoundError(
                        f"Không tìm thấy notification: {notification_id}"
                    )
                _require_version(
                    notification.version, expected_version, str(notification_id)
                )
                if action == "read":
                    notification.read_at = current
                elif action == "unread":
                    notification.read_at = None
                else:
                    notification.dismissed_at = current
                    notification.read_at = notification.read_at or current
                session.flush()
                return _notification_values(notification)
        except (RecordNotFoundError, StaleRecordError):
            raise
        except StaleDataError as exc:
            raise StaleRecordError(
                "Notification đã thay đổi. Hãy tải lại trước khi cập nhật."
            ) from exc
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể cập nhật notification.") from exc

    def read_all_notifications(
        self, recipient_user_id: UUID, *, now: datetime | None = None
    ) -> int:
        current = _aware_utc(now or _utc_now())
        try:
            with self.session_factory() as session, session.begin():
                notifications = session.scalars(
                    select(Notification)
                    .where(
                        Notification.recipient_user_id == recipient_user_id,
                        Notification.read_at.is_(None),
                        Notification.dismissed_at.is_(None),
                    )
                    .with_for_update()
                ).all()
                for notification in notifications:
                    notification.read_at = current
                return len(notifications)
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể đánh dấu toàn bộ notification đã xem."
            ) from exc

    def heartbeat(
        self,
        *,
        worker_identity: str,
        started_at: datetime,
        status: str,
        current_execution_id: UUID | None,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> None:
        current = _aware_utc(now or _utc_now())
        worker = _worker_identity(worker_identity)
        if status not in {"starting", "ready", "stopping", "error"}:
            raise ValueError("Worker heartbeat status không hợp lệ.")
        try:
            with self.session_factory() as session, session.begin():
                heartbeat_table = WorkerHeartbeat.__table__
                session.execute(
                    insert(heartbeat_table)
                    .values(
                        worker_identity=worker,
                        started_at=_aware_utc(started_at),
                        last_seen_at=current,
                        status=status,
                        current_execution_id=current_execution_id,
                        metadata=metadata or {},
                    )
                    .on_conflict_do_update(
                        index_elements=[heartbeat_table.c.worker_identity],
                        set_={
                            "last_seen_at": current,
                            "status": status,
                            "current_execution_id": current_execution_id,
                            "metadata": metadata or {},
                        },
                    )
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể ghi worker heartbeat.") from exc

    def worker_health(
        self,
        *,
        stale_after_seconds: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self.queries.worker_health(
            stale_after_seconds=stale_after_seconds,
            now=now,
        )

    def operational_metrics(self, *, now: datetime | None = None) -> dict[str, Any]:
        return self.queries.operational_metrics(now=now)


def _job_values(job: ScheduledJob) -> dict[str, Any]:
    return {
        "job_key": job.job_key,
        "job_type": job.job_type,
        "display_name": JOB_CATALOG[JobType(job.job_type)].display_name,
        "enabled": job.enabled,
        "interval_seconds": job.interval_seconds,
        "timezone": job.timezone,
        "next_run_at": job.next_run_at.isoformat(),
        "last_successful_run_at": (
            job.last_successful_run_at.isoformat()
            if job.last_successful_run_at
            else None
        ),
        "concurrency_policy": job.concurrency_policy,
        "run_as_user_id": str(job.run_as_user_id) if job.run_as_user_id else None,
        "max_attempts": job.max_attempts,
        "retry_backoff_seconds": job.retry_backoff_seconds,
        "lease_seconds": job.lease_seconds,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "version": job.version,
    }


def _execution_values(execution: JobExecution) -> dict[str, Any]:
    return {
        "id": str(execution.id),
        "job_key": execution.job_key,
        "scheduled_for": execution.scheduled_for.isoformat(),
        "trigger_type": execution.trigger_type,
        "requested_by_user_id": (
            str(execution.requested_by_user_id)
            if execution.requested_by_user_id
            else None
        ),
        "status": execution.status,
        "attempt_number": execution.attempt_number,
        "worker_identity": execution.worker_identity,
        "available_after": execution.available_after.isoformat(),
        "lease_expires_at": (
            execution.lease_expires_at.isoformat()
            if execution.lease_expires_at
            else None
        ),
        "started_at": (
            execution.started_at.isoformat() if execution.started_at else None
        ),
        "completed_at": (
            execution.completed_at.isoformat() if execution.completed_at else None
        ),
        "execution_summary": execution.execution_summary,
        "safe_error_code": execution.safe_error_code,
        "safe_error_summary": execution.safe_error_summary,
        "correlation_id": execution.correlation_id,
        "created_at": execution.created_at.isoformat(),
        "updated_at": execution.updated_at.isoformat(),
        "version": execution.version,
    }


def _outbox_values(
    event: OutboxEvent, *, include_payload: bool = False
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": str(event.id),
        "event_type": event.event_type,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": event.aggregate_id,
        "scope_id": event.scope_id,
        "created_at": event.created_at.isoformat(),
        "available_after": event.available_after.isoformat(),
        "status": event.status,
        "attempt_count": event.attempt_count,
        "redrive_count": event.redrive_count,
        "lease_owner": event.lease_owner,
        "lease_expires_at": (
            event.lease_expires_at.isoformat() if event.lease_expires_at else None
        ),
        "processed_at": (
            event.processed_at.isoformat() if event.processed_at else None
        ),
        "last_safe_error_code": event.last_safe_error_code,
        "last_safe_error_summary": event.last_safe_error_summary,
        "updated_at": event.updated_at.isoformat(),
        "version": event.version,
    }
    if include_payload:
        values["payload"] = dict(event.payload)
    return values


def _notification_values(notification: Notification) -> dict[str, Any]:
    return {
        "id": str(notification.id),
        "notification_type": notification.notification_type,
        "title": notification.title,
        "body": notification.body,
        "structured_content": notification.structured_content,
        "severity": notification.severity,
        "related_entity_type": notification.related_entity_type,
        "related_entity_id": notification.related_entity_id,
        "created_at": notification.created_at.isoformat(),
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "dismissed_at": (
            notification.dismissed_at.isoformat()
            if notification.dismissed_at
            else None
        ),
        "version": notification.version,
    }


def _validate_job(job: ScheduledJob) -> None:
    validate_job_configuration(
        job.job_type,
        interval_seconds=job.interval_seconds,
        timezone_name=job.timezone,
        configuration_payload=dict(job.configuration_payload),
    )
    if job.concurrency_policy != "forbid_overlap":
        raise IntegrityViolationError("Unsupported background job concurrency policy.")


def _next_due(scheduled_for: datetime, interval_seconds: int, now: datetime) -> datetime:
    elapsed_seconds = max(0, (now - scheduled_for).total_seconds())
    intervals_to_advance = int(elapsed_seconds // interval_seconds) + 1
    return scheduled_for + timedelta(
        seconds=intervals_to_advance * interval_seconds
    )


def _schedule_execution_failure(
    execution: JobExecution,
    job: ScheduledJob,
    *,
    current: datetime,
    error_code: str,
    error_summary: str,
) -> None:
    execution.safe_error_code = str(error_code)[:80]
    execution.safe_error_summary = str(error_summary)[:1000]
    execution.worker_identity = None
    execution.lease_expires_at = None
    execution.updated_at = current
    if execution.attempt_number < job.max_attempts:
        delay = job.retry_backoff_seconds * (2 ** max(0, execution.attempt_number - 1))
        execution.status = JobExecutionStatus.RETRY_SCHEDULED.value
        execution.available_after = current + timedelta(seconds=min(delay, 3600))
        execution.completed_at = None
    else:
        execution.status = JobExecutionStatus.DEAD_LETTERED.value
        execution.completed_at = current


def _locked_running_execution(
    session: Session, execution_id: UUID, *, worker_identity: str
) -> JobExecution:
    execution = session.get(JobExecution, execution_id, with_for_update=True)
    if execution is None:
        raise RecordNotFoundError(f"Không tìm thấy job execution: {execution_id}")
    if (
        execution.status != JobExecutionStatus.RUNNING.value
        or execution.worker_identity != worker_identity
    ):
        raise IntegrityViolationError(
            "Job execution không còn thuộc worker hiện tại."
        )
    return execution


def _record_delivery_attempt(
    session: Session,
    event: OutboxEvent,
    *,
    worker_identity: str,
    status: str,
    error_code: str | None,
    error_summary: str | None,
    now: datetime,
) -> None:
    session.add(
        OutboxDeliveryAttempt(
            id=uuid4(),
            outbox_event_id=event.id,
            attempt_number=event.attempt_count,
            redrive_number=event.redrive_count,
            worker_identity=_worker_identity(worker_identity),
            started_at=_aware_utc(event.updated_at),
            completed_at=now,
            status=status,
            safe_error_code=str(error_code)[:80] if error_code else None,
            safe_error_summary=str(error_summary)[:1000] if error_summary else None,
            created_at=now,
        )
    )


def _schedule_outbox_failure(
    event: OutboxEvent,
    *,
    current: datetime,
    error_code: str,
    error_summary: str,
) -> None:
    event.last_safe_error_code = str(error_code)[:80]
    event.last_safe_error_summary = str(error_summary)[:1000]
    event.lease_owner = None
    event.lease_expires_at = None
    event.processed_at = None
    event.updated_at = current
    if event.attempt_count < MAX_OUTBOX_ATTEMPTS:
        delay = OUTBOX_RETRY_BACKOFF_SECONDS * (
            2 ** max(0, event.attempt_count - 1)
        )
        event.status = OutboxStatus.RETRY_SCHEDULED.value
        event.available_after = current + timedelta(seconds=min(delay, 3600))
    else:
        event.status = OutboxStatus.DEAD_LETTERED.value


def _require_outbox_owner(event: OutboxEvent, worker_identity: str) -> None:
    if (
        event.status != OutboxStatus.PROCESSING.value
        or event.lease_owner != worker_identity
    ):
        raise IntegrityViolationError(
            "Outbox event không còn thuộc worker hiện tại."
        )


def _resolve_recipients(
    session: Session,
    payload: dict[str, Any],
    roles: frozenset[Role],
    explicit_fields: tuple[str, ...],
) -> set[UUID]:
    recipients: set[UUID] = set()
    if roles:
        recipients.update(
            session.scalars(
                select(User.id).where(
                    User.is_active.is_(True),
                    User.role.in_([role.value for role in roles]),
                )
            ).all()
        )
    explicit_ids: set[UUID] = set()
    for field in explicit_fields:
        value = payload.get(field)
        if value:
            try:
                explicit_ids.add(UUID(str(value)))
            except ValueError as exc:
                raise IntegrityViolationError(
                    f"Outbox recipient field is not a UUID: {field}"
                ) from exc
    if explicit_ids:
        recipients.update(
            session.scalars(
                select(User.id).where(
                    User.id.in_(explicit_ids), User.is_active.is_(True)
                )
            ).all()
        )
    return recipients


def _related_entity_id(
    related_entity_type: str, payload: dict[str, Any], aggregate_id: str
) -> str:
    field_by_type = {
        "ticket": "ticket_id",
        "work_order": "work_order_id",
        "inventory_issue": "issue_id",
        "job_execution": "execution_id",
        "part": "part_id",
        "maintenance_plan": "plan_id",
        "operational_alert": "entity_key",
    }
    field = field_by_type.get(related_entity_type)
    return str(payload.get(field) or aggregate_id)[:120]


def _notification_content(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key
        in {
            "ticket_id",
            "asset_id",
            "priority",
            "rule_code",
            "clock_type",
            "work_order_id",
            "work_order_number",
            "part_id",
            "part_number",
            "stock_location_id",
            "stock_location_code",
            "available_quantity",
            "reorder_point",
            "stock_state",
            "execution_id",
            "plan_id",
            "plan_code",
            "generated_count",
            "skipped_count",
            "error_code",
            "alert_type",
            "alert_name",
            "entity_key",
            "cycle_number",
            "observed_value",
            "threshold_value",
        }
    }


def _alert_condition(
    alert_type: str,
    entity_key: str,
    alert_name: str,
    observed_value: int,
    threshold_value: int,
    *,
    breached: bool | None = None,
) -> dict[str, Any]:
    return {
        "alert_type": alert_type,
        "entity_key": entity_key,
        "alert_name": alert_name,
        "observed_value": observed_value,
        "threshold_value": threshold_value,
        "breached": observed_value > threshold_value if breached is None else breached,
    }


def _inventory_entity_key(item: dict[str, Any]) -> str:
    return f"{item['part_id']}:{item['stock_location_id']}"


def _low_stock_payload(
    item: dict[str, Any], current_cycle: int
) -> dict[str, Any]:
    return {
        "part_id": str(item["part_id"]),
        "part_number": str(item["part_number"])[:80],
        "stock_location_id": str(item["stock_location_id"]),
        "stock_location_code": str(item["stock_location_code"])[:50],
        "available_quantity": str(item["available_quantity"]),
        "reorder_point": str(item["reorder_point"]),
        "stock_state": str(item["stock_state"]),
        "cycle_number": current_cycle,
    }


def _bounded_summary(summary: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(summary, dict) or len(summary) > 50:
        raise IntegrityViolationError("Execution summary phải là object tối đa 50 fields.")
    safe: dict[str, Any] = {}
    for key, value in summary.items():
        normalized_key = str(key)[:100]
        if value is None or isinstance(value, (str, int, float, bool)):
            safe[normalized_key] = str(value)[:500] if isinstance(value, str) else value
        elif isinstance(value, dict):
            safe[normalized_key] = {
                str(child_key)[:100]: (
                    str(child_value)[:500]
                    if not isinstance(child_value, (int, float, bool))
                    else child_value
                )
                for child_key, child_value in list(value.items())[:50]
            }
        elif isinstance(value, (list, tuple)):
            safe[normalized_key] = [str(item)[:200] for item in list(value)[:100]]
        else:
            safe[normalized_key] = str(value)[:500]
    return safe


def _manual_key(job_key: str, idempotency_key: str) -> str:
    normalized = str(idempotency_key).strip()
    if not normalized or len(normalized) > 100:
        raise ValueError("Idempotency-Key phải chứa 1–100 ký tự.")
    return f"manual:{job_key}:{normalized}"[:200]


def _worker_identity(value: str) -> str:
    normalized = str(value).strip()
    if not normalized or len(normalized) > 100:
        raise ValueError("worker_identity phải chứa 1–100 ký tự.")
    return normalized


def _require_version(current: int, expected: int, identifier: str) -> None:
    if current != expected:
        raise StaleRecordError(
            f"Record {identifier} đã thay đổi. Hãy tải lại trước khi cập nhật."
        )


def _current_user(user: User) -> CurrentUser:
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
        session_id=uuid4(),
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


def _audit(
    session: Session,
    context: AuditContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    append_audit_event(
        session,
        actor_user_id=context.actor_user_id,
        actor_display_name=context.actor_display_name,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=context.request_id,
        before_state=before,
        after_state=after,
        metadata=metadata,
    )


def _count_where(session: Session, model, condition) -> int:
    return int(
        session.scalar(select(func.count()).select_from(model).where(condition))
        or 0
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamp phải có timezone.")
    return value.astimezone(timezone.utc)
