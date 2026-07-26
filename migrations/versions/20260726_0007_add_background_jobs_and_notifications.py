"""Add durable background jobs, transactional outbox, and notifications.

Revision ID: 20260726_0007
Revises: 20260723_0006
Create Date: 2026-07-26 10:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260726_0007"
down_revision: str | None = "20260723_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the Product Milestone 7 operational foundation."""

    op.create_table(
        "scheduled_jobs",
        sa.Column("job_key", sa.String(length=80), nullable=False),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default=sa.text("'Asia/Ho_Chi_Minh'"),
            nullable=False,
        ),
        sa.Column(
            "configuration_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "next_run_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_successful_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "concurrency_policy",
            sa.String(length=30),
            server_default=sa.text("'forbid_overlap'"),
            nullable=False,
        ),
        sa.Column("run_as_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False
        ),
        sa.Column(
            "retry_backoff_seconds",
            sa.Integer(),
            server_default=sa.text("30"),
            nullable=False,
        ),
        sa.Column(
            "lease_seconds",
            sa.Integer(),
            server_default=sa.text("300"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.CheckConstraint(
            "concurrency_policy = 'forbid_overlap'",
            name="ck_scheduled_jobs_concurrency",
        ),
        sa.CheckConstraint(
            "interval_seconds BETWEEN 30 AND 604800",
            name="ck_scheduled_jobs_interval",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(configuration_payload) = 'object'",
            name="ck_scheduled_jobs_configuration",
        ),
        sa.CheckConstraint(
            "job_type IN ('preventive_generation', 'sla_escalation', "
            "'analytics_refresh', 'inventory_reorder_detection')",
            name="ck_scheduled_jobs_type",
        ),
        sa.CheckConstraint(
            "lease_seconds BETWEEN 30 AND 3600",
            name="ck_scheduled_jobs_lease",
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 10",
            name="ck_scheduled_jobs_max_attempts",
        ),
        sa.CheckConstraint(
            "retry_backoff_seconds BETWEEN 1 AND 3600",
            name="ck_scheduled_jobs_retry_backoff",
        ),
        sa.ForeignKeyConstraint(
            ["run_as_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("job_key"),
        sa.UniqueConstraint("job_type", name="uq_scheduled_jobs_type"),
    )
    op.create_index(
        "ix_scheduled_jobs_due",
        "scheduled_jobs",
        ["enabled", "next_run_at"],
        unique=False,
    )

    op.create_table(
        "job_executions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_key", sa.String(length=80), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger_type", sa.String(length=20), nullable=False),
        sa.Column("requested_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_number",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("worker_identity", sa.String(length=100), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column(
            "available_after",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "execution_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("safe_error_code", sa.String(length=80), nullable=True),
        sa.Column("safe_error_summary", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.CheckConstraint(
            "attempt_number >= 0", name="ck_job_executions_attempt"
        ),
        sa.CheckConstraint(
            "execution_summary IS NULL OR "
            "jsonb_typeof(execution_summary) = 'object'",
            name="ck_job_executions_summary",
        ),
        sa.CheckConstraint(
            "safe_error_summary IS NULL OR "
            "char_length(safe_error_summary) <= 1000",
            name="ck_job_executions_error_length",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', "
            "'retry_scheduled', 'dead_lettered', 'cancelled', 'skipped')",
            name="ck_job_executions_status",
        ),
        sa.CheckConstraint(
            "trigger_type IN ('scheduled', 'manual')",
            name="ck_job_executions_trigger",
        ),
        sa.ForeignKeyConstraint(
            ["job_key"], ["scheduled_jobs.job_key"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_job_executions_idempotency"
        ),
    )
    op.create_index(
        "ix_job_executions_claim",
        "job_executions",
        ["status", "available_after"],
        unique=False,
    )
    op.create_index(
        "ix_job_executions_job_history",
        "job_executions",
        ["job_key", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_executions_lease",
        "job_executions",
        ["lease_expires_at"],
        unique=False,
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.String(length=120), nullable=False),
        sa.Column("scope_id", sa.String(length=100), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "available_after",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("last_safe_error_code", sa.String(length=80), nullable=True),
        sa.Column("last_safe_error_summary", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_outbox_events_attempts"
        ),
        sa.CheckConstraint(
            "char_length(payload_hash) = 64", name="ck_outbox_events_hash"
        ),
        sa.CheckConstraint(
            "last_safe_error_summary IS NULL OR "
            "char_length(last_safe_error_summary) <= 1000",
            name="ck_outbox_events_error_length",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND "
            "octet_length(payload::text) <= 16384",
            name="ck_outbox_events_payload",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'processed', "
            "'retry_scheduled', 'dead_lettered')",
            name="ck_outbox_events_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_outbox_events_idempotency"
        ),
    )
    op.create_index(
        "ix_outbox_events_aggregate",
        "outbox_events",
        ["aggregate_type", "aggregate_id"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_claim",
        "outbox_events",
        ["status", "available_after"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_created_at",
        "outbox_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_lease",
        "outbox_events",
        ["lease_expires_at"],
        unique=False,
    )

    op.create_table(
        "outbox_delivery_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("outbox_event_id", sa.UUID(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("worker_identity", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("safe_error_code", sa.String(length=80), nullable=True),
        sa.Column("safe_error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_number > 0",
            name="ck_outbox_delivery_attempts_number",
        ),
        sa.CheckConstraint(
            "safe_error_summary IS NULL OR "
            "char_length(safe_error_summary) <= 1000",
            name="ck_outbox_delivery_attempts_error_length",
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="ck_outbox_delivery_attempts_status",
        ),
        sa.ForeignKeyConstraint(
            ["outbox_event_id"], ["outbox_events.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "outbox_event_id",
            "attempt_number",
            name="uq_outbox_delivery_attempt_event_number",
        ),
    )
    op.create_index(
        "ix_outbox_delivery_attempts_event",
        "outbox_delivery_attempts",
        ["outbox_event_id", "attempt_number"],
        unique=False,
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("recipient_user_id", sa.UUID(), nullable=False),
        sa.Column("notification_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "structured_content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("related_entity_type", sa.String(length=80), nullable=True),
        sa.Column("related_entity_id", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deduplication_key", sa.String(length=200), nullable=False),
        sa.Column("source_outbox_event_id", sa.UUID(), nullable=True),
        sa.Column(
            "version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 1000",
            name="ck_notifications_body",
        ),
        sa.CheckConstraint(
            "structured_content IS NULL OR "
            "jsonb_typeof(structured_content) = 'object'",
            name="ck_notifications_content",
        ),
        sa.CheckConstraint(
            "(related_entity_type IS NULL) = (related_entity_id IS NULL)",
            name="ck_notifications_related_entity",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_notifications_severity",
        ),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 200",
            name="ck_notifications_title",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_outbox_event_id"], ["outbox_events.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recipient_user_id",
            "deduplication_key",
            name="uq_notifications_recipient_dedup",
        ),
    )
    op.create_index(
        "ix_notifications_recipient_created",
        "notifications",
        ["recipient_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_recipient_unread",
        "notifications",
        ["recipient_user_id", "read_at", "dismissed_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_source_event",
        "notifications",
        ["source_outbox_event_id"],
        unique=False,
    )

    op.create_table(
        "notification_alert_states",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("alert_type", sa.String(length=80), nullable=False),
        sa.Column("entity_key", sa.String(length=200), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "cycle_number",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.CheckConstraint(
            "alert_type = 'inventory_low_stock'",
            name="ck_notification_alert_states_type",
        ),
        sa.CheckConstraint(
            "cycle_number >= 0", name="ck_notification_alert_states_cycle"
        ),
        sa.CheckConstraint(
            "last_details IS NULL OR jsonb_typeof(last_details) = 'object'",
            name="ck_notification_alert_states_details",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "alert_type",
            "entity_key",
            name="uq_notification_alert_states_entity",
        ),
    )
    op.create_index(
        "ix_notification_alert_states_active",
        "notification_alert_states",
        ["alert_type", "is_active"],
        unique=False,
    )

    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_identity", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_execution_id", sa.UUID(), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.CheckConstraint(
            "metadata IS NULL OR jsonb_typeof(metadata) = 'object'",
            name="ck_worker_heartbeats_metadata",
        ),
        sa.CheckConstraint(
            "status IN ('starting', 'ready', 'stopping', 'error')",
            name="ck_worker_heartbeats_status",
        ),
        sa.ForeignKeyConstraint(
            ["current_execution_id"], ["job_executions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("worker_identity"),
    )
    op.create_index(
        "ix_worker_heartbeats_last_seen",
        "worker_heartbeats",
        ["last_seen_at"],
        unique=False,
    )

    op.execute(
        """
        CREATE FUNCTION reject_pm7_delivery_attempt_mutation() RETURNS trigger AS $$
        BEGIN
            IF current_setting('app.demo_reset', true) = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'outbox delivery attempts are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER outbox_delivery_attempts_append_only
        BEFORE UPDATE OR DELETE ON outbox_delivery_attempts
        FOR EACH ROW EXECUTE FUNCTION reject_pm7_delivery_attempt_mutation()
        """
    )

    op.execute(
        """
        INSERT INTO scheduled_jobs (
            job_key, job_type, enabled, interval_seconds, timezone,
            configuration_payload, next_run_at, concurrency_policy,
            max_attempts, retry_backoff_seconds, lease_seconds
        ) VALUES
            (
                'preventive_generation', 'preventive_generation', false, 3600,
                'Asia/Ho_Chi_Minh', '{}'::jsonb, now(), 'forbid_overlap', 3, 30, 300
            ),
            (
                'sla_escalation', 'sla_escalation', false, 300,
                'Asia/Ho_Chi_Minh', '{}'::jsonb, now(), 'forbid_overlap', 3, 30, 180
            ),
            (
                'analytics_refresh', 'analytics_refresh', false, 86400,
                'Asia/Ho_Chi_Minh', '{}'::jsonb, now(), 'forbid_overlap', 2, 120, 3600
            ),
            (
                'inventory_reorder_detection', 'inventory_reorder_detection',
                false, 900, 'Asia/Ho_Chi_Minh', '{}'::jsonb, now(),
                'forbid_overlap', 3, 30, 180
            )
        """
    )


def downgrade() -> None:
    """Remove PM7 operational entities without changing PM1-PM6 data."""

    op.execute(
        "DROP TRIGGER IF EXISTS outbox_delivery_attempts_append_only "
        "ON outbox_delivery_attempts"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_pm7_delivery_attempt_mutation()")

    op.drop_index(
        "ix_worker_heartbeats_last_seen", table_name="worker_heartbeats"
    )
    op.drop_table("worker_heartbeats")
    op.drop_index(
        "ix_notification_alert_states_active",
        table_name="notification_alert_states",
    )
    op.drop_table("notification_alert_states")
    op.drop_index("ix_notifications_source_event", table_name="notifications")
    op.drop_index(
        "ix_notifications_recipient_unread", table_name="notifications"
    )
    op.drop_index(
        "ix_notifications_recipient_created", table_name="notifications"
    )
    op.drop_table("notifications")
    op.drop_index(
        "ix_outbox_delivery_attempts_event",
        table_name="outbox_delivery_attempts",
    )
    op.drop_table("outbox_delivery_attempts")
    op.drop_index("ix_outbox_events_lease", table_name="outbox_events")
    op.drop_index("ix_outbox_events_created_at", table_name="outbox_events")
    op.drop_index("ix_outbox_events_claim", table_name="outbox_events")
    op.drop_index("ix_outbox_events_aggregate", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_job_executions_lease", table_name="job_executions")
    op.drop_index(
        "ix_job_executions_job_history", table_name="job_executions"
    )
    op.drop_index("ix_job_executions_claim", table_name="job_executions")
    op.drop_table("job_executions")
    op.drop_index("ix_scheduled_jobs_due", table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")
