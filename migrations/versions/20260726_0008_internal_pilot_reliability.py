"""Add internal-pilot reliability evidence and bounded outbox redrive.

Revision ID: 20260726_0008
Revises: 20260726_0007
Create Date: 2026-07-26 16:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260726_0008"
down_revision: str | None = "20260726_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add only PM8 reliability validation records and operator controls."""

    op.add_column(
        "outbox_events",
        sa.Column(
            "redrive_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_outbox_events_redrives", "outbox_events", "redrive_count >= 0"
    )
    op.add_column(
        "outbox_delivery_attempts",
        sa.Column(
            "redrive_number", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_outbox_delivery_attempts_redrives",
        "outbox_delivery_attempts",
        "redrive_number >= 0",
    )
    op.drop_constraint(
        "uq_outbox_delivery_attempt_event_number",
        "outbox_delivery_attempts",
        type_="unique",
    )
    op.drop_index(
        "ix_outbox_delivery_attempts_event",
        table_name="outbox_delivery_attempts",
    )
    op.create_unique_constraint(
        "uq_outbox_delivery_attempt_cycle_number",
        "outbox_delivery_attempts",
        ["outbox_event_id", "redrive_number", "attempt_number"],
    )
    op.create_index(
        "ix_outbox_delivery_attempts_event",
        "outbox_delivery_attempts",
        ["outbox_event_id", "redrive_number", "attempt_number"],
        unique=False,
    )

    op.drop_constraint(
        "ck_notification_alert_states_type",
        "notification_alert_states",
        type_="check",
    )
    op.create_check_constraint(
        "ck_notification_alert_states_type",
        "notification_alert_states",
        "alert_type IN ('inventory_low_stock', 'worker_heartbeat_stale', "
        "'outbox_backlog_old', 'dead_letter_present', "
        "'scheduled_job_repeated_failure', 'analytics_refresh_stale', "
        "'backup_validation_overdue')",
    )

    op.create_table(
        "outbox_redrive_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("outbox_event_id", sa.UUID(), nullable=False),
        sa.Column("requested_by_user_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("prior_attempt_count", sa.Integer(), nullable=False),
        sa.Column("redrive_number", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=100), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "prior_attempt_count > 0",
            name="ck_outbox_redrive_requests_prior_attempts",
        ),
        sa.CheckConstraint(
            "redrive_number > 0",
            name="ck_outbox_redrive_requests_redrive_number",
        ),
        sa.ForeignKeyConstraint(
            ["outbox_event_id"], ["outbox_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_outbox_redrive_requests_idempotency"
        ),
        sa.UniqueConstraint(
            "outbox_event_id",
            "redrive_number",
            name="uq_outbox_redrive_requests_event_cycle",
        ),
    )
    op.create_index(
        "ix_outbox_redrive_requests_event",
        "outbox_redrive_requests",
        ["outbox_event_id", "requested_at"],
        unique=False,
    )

    op.create_table(
        "reliability_validation_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("validation_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "performed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_revision", sa.String(length=80), nullable=False),
        sa.Column("backup_checksum", sa.String(length=64), nullable=True),
        sa.Column(
            "summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "validation_type IN ('backup_restore')",
            name="ck_reliability_validation_records_type",
        ),
        sa.CheckConstraint(
            "status IN ('passed', 'failed')",
            name="ck_reliability_validation_records_status",
        ),
        sa.CheckConstraint(
            "backup_checksum IS NULL OR "
            "backup_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_reliability_validation_records_checksum",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(summary) = 'object' "
            "AND octet_length(summary::text) <= 4096",
            name="ck_reliability_validation_records_summary",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reliability_validation_records_latest",
        "reliability_validation_records",
        ["validation_type", "status", "performed_at"],
        unique=False,
    )

    op.execute(
        """
        CREATE FUNCTION reject_pm8_append_only_mutation() RETURNS trigger AS $$
        BEGIN
            IF current_setting('app.demo_reset', true) = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'PM8 reliability evidence is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in ("outbox_redrive_requests", "reliability_validation_records"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_pm8_append_only_mutation();
            """
        )


def downgrade() -> None:
    """Remove PM8 evidence while preserving every PM1-PM7 table."""

    op.execute("SET LOCAL app.demo_reset = 'on'")
    op.execute(
        """
        DELETE FROM notifications
        WHERE source_outbox_event_id IN (
            SELECT id FROM outbox_events
            WHERE event_type IN (
                'operations.alert_raised', 'operations.alert_recovered'
            )
        )
        """
    )
    op.execute(
        """
        DELETE FROM outbox_delivery_attempts
        WHERE redrive_number > 0
           OR outbox_event_id IN (
                SELECT id FROM outbox_events
                WHERE event_type IN (
                    'operations.alert_raised', 'operations.alert_recovered'
                )
           )
        """
    )
    op.execute(
        """
        UPDATE outbox_events AS event
        SET attempt_count = GREATEST(
                COALESCE(
                    (
                        SELECT max(attempt.attempt_number)
                        FROM outbox_delivery_attempts AS attempt
                        WHERE attempt.outbox_event_id = event.id
                          AND attempt.redrive_number = 0
                    ),
                    0
                ),
                COALESCE(
                    (
                        SELECT max(request.prior_attempt_count)
                        FROM outbox_redrive_requests AS request
                        WHERE request.outbox_event_id = event.id
                    ),
                    0
                )
            ),
            status = CASE
                WHEN event.status = 'processed' THEN 'processed'
                ELSE 'dead_lettered'
            END,
            lease_owner = NULL,
            lease_expires_at = NULL,
            processed_at = CASE
                WHEN event.status = 'processed' THEN event.processed_at
                ELSE NULL
            END,
            last_safe_error_code = CASE
                WHEN event.status = 'processed' THEN event.last_safe_error_code
                ELSE 'pm8_redrive_rolled_back'
            END,
            last_safe_error_summary = CASE
                WHEN event.status = 'processed' THEN event.last_safe_error_summary
                ELSE 'Redrive PM8 chưa hoàn tất đã được trả về dead-letter khi rollback.'
            END,
            updated_at = now(),
            version = event.version + 1
        WHERE event.redrive_count > 0
          AND event.event_type NOT IN (
              'operations.alert_raised', 'operations.alert_recovered'
          )
        """
    )
    op.execute(
        """
        DELETE FROM notification_alert_states
        WHERE alert_type <> 'inventory_low_stock'
        """
    )
    for table in ("reliability_validation_records", "outbox_redrive_requests"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_pm8_append_only_mutation()")

    op.drop_index(
        "ix_reliability_validation_records_latest",
        table_name="reliability_validation_records",
    )
    op.drop_table("reliability_validation_records")
    op.drop_index(
        "ix_outbox_redrive_requests_event", table_name="outbox_redrive_requests"
    )
    op.drop_table("outbox_redrive_requests")
    op.execute(
        """
        DELETE FROM outbox_events
        WHERE event_type IN (
            'operations.alert_raised', 'operations.alert_recovered'
        )
        """
    )

    op.drop_constraint(
        "ck_notification_alert_states_type",
        "notification_alert_states",
        type_="check",
    )
    op.create_check_constraint(
        "ck_notification_alert_states_type",
        "notification_alert_states",
        "alert_type = 'inventory_low_stock'",
    )

    op.drop_constraint(
        "uq_outbox_delivery_attempt_cycle_number",
        "outbox_delivery_attempts",
        type_="unique",
    )
    op.drop_index(
        "ix_outbox_delivery_attempts_event",
        table_name="outbox_delivery_attempts",
    )
    op.create_unique_constraint(
        "uq_outbox_delivery_attempt_event_number",
        "outbox_delivery_attempts",
        ["outbox_event_id", "attempt_number"],
    )
    op.create_index(
        "ix_outbox_delivery_attempts_event",
        "outbox_delivery_attempts",
        ["outbox_event_id", "attempt_number"],
        unique=False,
    )
    op.drop_constraint(
        "ck_outbox_delivery_attempts_redrives",
        "outbox_delivery_attempts",
        type_="check",
    )
    op.drop_column("outbox_delivery_attempts", "redrive_number")
    op.drop_constraint(
        "ck_outbox_events_redrives", "outbox_events", type_="check"
    )
    op.drop_column("outbox_events", "redrive_count")
