"""FastAPI contracts for PM7 operations and notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    id: UUID
    notification_type: str
    title: str
    body: str
    structured_content: dict[str, Any] | None
    severity: Literal["info", "warning", "critical"]
    related_entity_type: str | None
    related_entity_id: str | None
    created_at: datetime
    read_at: datetime | None
    dismissed_at: datetime | None
    version: int


class NotificationPage(BaseModel):
    items: list[NotificationResponse]
    page: int
    page_size: int
    total: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class NotificationVersionRequest(BaseModel):
    expected_version: int = Field(ge=1)


class ReadAllResponse(BaseModel):
    updated_count: int


class ScheduledJobResponse(BaseModel):
    job_key: str
    job_type: str
    display_name: str
    enabled: bool
    interval_seconds: int
    timezone: str
    next_run_at: datetime
    last_successful_run_at: datetime | None
    concurrency_policy: str
    run_as_user_id: UUID | None
    max_attempts: int
    retry_backoff_seconds: int
    lease_seconds: int
    created_at: datetime
    updated_at: datetime
    version: int


class JobEnabledRequest(BaseModel):
    enabled: bool
    expected_version: int = Field(ge=1)


class JobExecutionResponse(BaseModel):
    id: UUID
    job_key: str
    scheduled_for: datetime
    trigger_type: Literal["scheduled", "manual"]
    requested_by_user_id: UUID | None
    status: Literal[
        "pending",
        "running",
        "succeeded",
        "failed",
        "retry_scheduled",
        "dead_lettered",
        "cancelled",
        "skipped",
    ]
    attempt_number: int
    worker_identity: str | None
    available_after: datetime
    lease_expires_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    execution_summary: dict[str, Any] | None
    safe_error_code: str | None
    safe_error_summary: str | None
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    version: int


class JobExecutionPage(BaseModel):
    items: list[JobExecutionResponse]
    page: int
    page_size: int
    total: int


class ManualTriggerResponse(BaseModel):
    execution: JobExecutionResponse
    created: bool


class OutboxEventResponse(BaseModel):
    id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: str
    scope_id: str | None
    created_at: datetime
    available_after: datetime
    status: Literal[
        "pending", "processing", "processed", "retry_scheduled", "dead_lettered"
    ]
    attempt_count: int
    lease_owner: str | None
    lease_expires_at: datetime | None
    processed_at: datetime | None
    last_safe_error_code: str | None
    last_safe_error_summary: str | None
    updated_at: datetime
    version: int


class OutboxEventPage(BaseModel):
    items: list[OutboxEventResponse]
    page: int
    page_size: int
    total: int


class OperationalMetricsResponse(BaseModel):
    as_of: datetime
    pending_job_count: int
    failed_job_count: int
    dead_letter_job_count: int
    pending_outbox_count: int
    dead_letter_outbox_count: int
    oldest_pending_outbox_age_seconds: int | None
    last_successful_run_by_job: dict[str, datetime | None]


class LivenessResponse(BaseModel):
    status: Literal["alive"]


class WorkerHealthResponse(BaseModel):
    status: Literal["ready", "starting", "stopping", "error", "stale", "missing"]
    ready: bool
    worker_identity: str | None
    last_seen_at: datetime | None
    age_seconds: int | None


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded"]
    database_ready: bool
    worker_ready: bool
    worker: WorkerHealthResponse
