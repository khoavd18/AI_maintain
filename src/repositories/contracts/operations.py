"""Storage-neutral durable PM7 operations repository contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from src.security.audit_context import AuditContext
from src.security.principal import CurrentUser

class OperationsRepository(Protocol):
    """Job, lease, outbox, notification, and worker-health operations."""

    backend_name: str

    def check_health(self) -> None: ...

    def list_jobs(self) -> list[dict[str, Any]]: ...

    def set_job_enabled(
        self,
        job_key: str,
        *,
        enabled: bool,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]: ...

    def trigger_job(
        self,
        job_key: str,
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], bool]: ...

    def retry_execution(
        self,
        execution_id: UUID,
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], bool]: ...

    def materialize_due_jobs(
        self, *, now: datetime | None = None, limit: int = 20
    ) -> dict[str, int]: ...

    def recover_expired_execution_leases(
        self, *, now: datetime | None = None, limit: int = 100
    ) -> int: ...

    def claim_execution(
        self, *, worker_identity: str, now: datetime | None = None
    ) -> dict[str, Any] | None: ...

    def complete_execution(
        self,
        execution_id: UUID,
        *,
        worker_identity: str,
        summary: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def renew_execution_lease(
        self,
        execution_id: UUID,
        *,
        worker_identity: str,
        now: datetime | None = None,
    ) -> None: ...

    def fail_execution(
        self,
        execution_id: UUID,
        *,
        worker_identity: str,
        error_code: str,
        error_summary: str,
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def load_execution_actor(self, execution_id: UUID) -> CurrentUser: ...

    def list_executions(
        self,
        *,
        status: str | None,
        job_key: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]: ...

    def list_outbox(
        self, *, status: str | None, page: int, page_size: int
    ) -> dict[str, Any]: ...

    def redrive_outbox_event(
        self,
        event_id: UUID,
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], bool]: ...

    def evaluate_operational_alerts(
        self,
        *,
        outbox_age_threshold_seconds: int,
        repeated_job_failure_threshold: int,
        analytics_stale_seconds: int,
        backup_overdue_seconds: int,
        worker_stale_seconds: int,
        now: datetime | None = None,
    ) -> dict[str, int]: ...

    def recover_expired_outbox_leases(
        self, *, now: datetime | None = None, limit: int = 100
    ) -> int: ...

    def claim_outbox_event(
        self,
        *,
        worker_identity: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> dict[str, Any] | None: ...

    def deliver_outbox_event(
        self,
        event_id: UUID,
        *,
        worker_identity: str,
        now: datetime | None = None,
    ) -> dict[str, int]: ...

    def fail_outbox_event(
        self,
        event_id: UUID,
        *,
        worker_identity: str,
        error_code: str,
        error_summary: str,
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def record_low_stock_cycles(
        self,
        *,
        low_stock_items: list[dict[str, Any]],
        observed_entity_keys: set[str],
        execution_id: UUID,
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def list_notifications(
        self,
        *,
        recipient_user_id: UUID,
        unread_only: bool,
        severity: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]: ...

    def unread_notification_count(self, recipient_user_id: UUID) -> int: ...

    def mutate_notification(
        self,
        notification_id: UUID,
        *,
        recipient_user_id: UUID,
        action: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def read_all_notifications(
        self, recipient_user_id: UUID, *, now: datetime | None = None
    ) -> int: ...

    def heartbeat(
        self,
        *,
        worker_identity: str,
        started_at: datetime,
        status: str,
        current_execution_id: UUID | None,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> None: ...

    def worker_health(
        self, *, stale_after_seconds: int, now: datetime | None = None
    ) -> dict[str, Any]: ...

    def operational_metrics(self, *, now: datetime | None = None) -> dict[str, Any]: ...
