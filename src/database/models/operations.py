"""Domain-owned SQLAlchemy models for transactional maintenance data."""

# Class bodies are preserved from the former canonical module.
# ruff: noqa: F401

from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, synonym

from src.database.models.base_mixins import _asset_qr_token, _utc_now
from src.database.session import Base

class ScheduledJob(Base):
    """Server-controlled recurring operation executed by the PM7 worker."""

    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('preventive_generation', 'sla_escalation', "
            "'analytics_refresh', 'inventory_reorder_detection')",
            name="ck_scheduled_jobs_type",
        ),
        CheckConstraint(
            "interval_seconds BETWEEN 30 AND 604800",
            name="ck_scheduled_jobs_interval",
        ),
        CheckConstraint(
            "concurrency_policy = 'forbid_overlap'",
            name="ck_scheduled_jobs_concurrency",
        ),
        CheckConstraint(
            "max_attempts BETWEEN 1 AND 10",
            name="ck_scheduled_jobs_max_attempts",
        ),
        CheckConstraint(
            "retry_backoff_seconds BETWEEN 1 AND 3600",
            name="ck_scheduled_jobs_retry_backoff",
        ),
        CheckConstraint(
            "lease_seconds BETWEEN 30 AND 3600",
            name="ck_scheduled_jobs_lease",
        ),
        CheckConstraint(
            "jsonb_typeof(configuration_payload) = 'object'",
            name="ck_scheduled_jobs_configuration",
        ),
        UniqueConstraint("job_type", name="uq_scheduled_jobs_type"),
        Index("ix_scheduled_jobs_due", "enabled", "next_run_at"),
    )

    job_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Ho_Chi_Minh"
    )
    configuration_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )
    last_successful_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    concurrency_policy: Mapped[str] = mapped_column(
        String(30), nullable=False, default="forbid_overlap", server_default="'forbid_overlap'"
    )
    run_as_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default=text("3")
    )
    retry_backoff_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default=text("30")
    )
    lease_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300, server_default=text("300")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}

class JobExecution(Base):
    """Durable execution state with lease-based worker ownership."""

    __tablename__ = "job_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', "
            "'retry_scheduled', 'dead_lettered', 'cancelled', 'skipped')",
            name="ck_job_executions_status",
        ),
        CheckConstraint(
            "trigger_type IN ('scheduled', 'manual')",
            name="ck_job_executions_trigger",
        ),
        CheckConstraint("attempt_number >= 0", name="ck_job_executions_attempt"),
        CheckConstraint(
            "execution_summary IS NULL OR jsonb_typeof(execution_summary) = 'object'",
            name="ck_job_executions_summary",
        ),
        CheckConstraint(
            "safe_error_summary IS NULL OR char_length(safe_error_summary) <= 1000",
            name="ck_job_executions_error_length",
        ),
        UniqueConstraint("idempotency_key", name="uq_job_executions_idempotency"),
        Index("ix_job_executions_claim", "status", "available_after"),
        Index("ix_job_executions_job_history", "job_key", "created_at"),
        Index("ix_job_executions_lease", "lease_expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    job_key: Mapped[str] = mapped_column(
        String(80), ForeignKey("scheduled_jobs.job_key", ondelete="RESTRICT"), nullable=False
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default="'pending'"
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    worker_identity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    available_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_summary: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    safe_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    safe_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}

class OutboxEvent(Base):
    """Transactional event claimed and delivered by the background worker."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'processed', "
            "'retry_scheduled', 'dead_lettered')",
            name="ck_outbox_events_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_outbox_events_attempts"),
        CheckConstraint("redrive_count >= 0", name="ck_outbox_events_redrives"),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 16384",
            name="ck_outbox_events_payload",
        ),
        CheckConstraint("char_length(payload_hash) = 64", name="ck_outbox_events_hash"),
        CheckConstraint(
            "last_safe_error_summary IS NULL OR char_length(last_safe_error_summary) <= 1000",
            name="ck_outbox_events_error_length",
        ),
        UniqueConstraint("idempotency_key", name="uq_outbox_events_idempotency"),
        Index("ix_outbox_events_claim", "status", "available_after"),
        Index("ix_outbox_events_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_outbox_events_created_at", "created_at"),
        Index("ix_outbox_events_lease", "lease_expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(120), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )
    available_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default="'pending'"
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    redrive_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    last_safe_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_safe_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}

class OutboxDeliveryAttempt(Base):
    """Append-only history for each outbox processing attempt."""

    __tablename__ = "outbox_delivery_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="ck_outbox_delivery_attempts_status",
        ),
        CheckConstraint(
            "attempt_number > 0", name="ck_outbox_delivery_attempts_number"
        ),
        CheckConstraint(
            "redrive_number >= 0",
            name="ck_outbox_delivery_attempts_redrives",
        ),
        CheckConstraint(
            "safe_error_summary IS NULL OR char_length(safe_error_summary) <= 1000",
            name="ck_outbox_delivery_attempts_error_length",
        ),
        UniqueConstraint(
            "outbox_event_id",
            "redrive_number",
            "attempt_number",
            name="uq_outbox_delivery_attempt_cycle_number",
        ),
        Index(
            "ix_outbox_delivery_attempts_event",
            "outbox_event_id",
            "redrive_number",
            "attempt_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    outbox_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("outbox_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    redrive_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    worker_identity: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    safe_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    safe_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )

class Notification(Base):
    """Private in-app notification owned by one authenticated user."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_notifications_severity",
        ),
        CheckConstraint(
            "char_length(title) BETWEEN 1 AND 200",
            name="ck_notifications_title",
        ),
        CheckConstraint(
            "char_length(body) BETWEEN 1 AND 1000",
            name="ck_notifications_body",
        ),
        CheckConstraint(
            "structured_content IS NULL OR jsonb_typeof(structured_content) = 'object'",
            name="ck_notifications_content",
        ),
        CheckConstraint(
            "(related_entity_type IS NULL) = (related_entity_id IS NULL)",
            name="ck_notifications_related_entity",
        ),
        UniqueConstraint(
            "recipient_user_id",
            "deduplication_key",
            name="uq_notifications_recipient_dedup",
        ),
        Index("ix_notifications_recipient_created", "recipient_user_id", "created_at"),
        Index(
            "ix_notifications_recipient_unread",
            "recipient_user_id",
            "read_at",
            "dismissed_at",
        ),
        Index("ix_notifications_source_event", "source_outbox_event_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    recipient_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    notification_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    structured_content: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    related_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    related_entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deduplication_key: Mapped[str] = mapped_column(String(200), nullable=False)
    source_outbox_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("outbox_events.id", ondelete="RESTRICT"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}

class NotificationAlertState(Base):
    """Persistent recovery cycle for deduplicated operational alerts."""

    __tablename__ = "notification_alert_states"
    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('inventory_low_stock', 'worker_heartbeat_stale', "
            "'outbox_backlog_old', 'dead_letter_present', "
            "'scheduled_job_repeated_failure', 'analytics_refresh_stale', "
            "'backup_validation_overdue')",
            name="ck_notification_alert_states_type",
        ),
        CheckConstraint("cycle_number >= 0", name="ck_notification_alert_states_cycle"),
        CheckConstraint(
            "last_details IS NULL OR jsonb_typeof(last_details) = 'object'",
            name="ck_notification_alert_states_details",
        ),
        UniqueConstraint(
            "alert_type", "entity_key", name="uq_notification_alert_states_entity"
        ),
        Index("ix_notification_alert_states_active", "alert_type", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    alert_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_key: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    cycle_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_detected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_recovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_details: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}

class WorkerHeartbeat(Base):
    """Last-known worker process state for readiness and operator recovery."""

    __tablename__ = "worker_heartbeats"
    __table_args__ = (
        CheckConstraint(
            "status IN ('starting', 'ready', 'stopping', 'error')",
            name="ck_worker_heartbeats_status",
        ),
        CheckConstraint(
            "metadata IS NULL OR jsonb_typeof(metadata) = 'object'",
            name="ck_worker_heartbeats_metadata",
        ),
        Index("ix_worker_heartbeats_last_seen", "last_seen_at"),
    )

    worker_identity: Mapped[str] = mapped_column(String(100), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    current_execution_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("job_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_payload: Mapped[dict[str, object] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

class OutboxRedriveRequest(Base):
    """Append-only operator intent for one bounded dead-letter redrive cycle."""

    __tablename__ = "outbox_redrive_requests"
    __table_args__ = (
        CheckConstraint(
            "prior_attempt_count > 0",
            name="ck_outbox_redrive_requests_prior_attempts",
        ),
        CheckConstraint(
            "redrive_number > 0",
            name="ck_outbox_redrive_requests_redrive_number",
        ),
        UniqueConstraint(
            "idempotency_key", name="uq_outbox_redrive_requests_idempotency"
        ),
        UniqueConstraint(
            "outbox_event_id",
            "redrive_number",
            name="uq_outbox_redrive_requests_event_cycle",
        ),
        Index(
            "ix_outbox_redrive_requests_event",
            "outbox_event_id",
            "requested_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    outbox_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("outbox_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    prior_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    redrive_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )

