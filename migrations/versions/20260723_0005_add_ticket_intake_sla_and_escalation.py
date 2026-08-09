"""Add ticket intake, SLA tracking, comments, and escalation.

Revision ID: 20260723_0005
Revises: 20260720_0004
Create Date: 2026-07-23 09:42:33.317123
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260723_0005"
down_revision: str | None = "20260720_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the Product Milestone 5 ticket-operations schema."""
    op.create_table(
        "support_groups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("code = upper(btrim(code))", name="ck_support_groups_code"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_support_groups_code"),
    )
    op.create_index("ix_support_groups_active", "support_groups", ["is_active"], unique=False)
    op.create_table(
        "ticket_categories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("code = lower(btrim(code))", name="ck_ticket_categories_code"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_ticket_categories_code"),
    )
    op.create_index("ix_ticket_categories_active", "ticket_categories", ["is_active"], unique=False)
    op.create_table(
        "ticket_intake_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("code = lower(btrim(code))", name="ck_ticket_sources_code"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_ticket_sources_code"),
    )
    op.create_index(
        "ix_ticket_sources_active", "ticket_intake_sources", ["is_active"], unique=False
    )
    op.create_table(
        "business_calendars",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("code = upper(btrim(code))", name="ck_business_calendars_code"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_business_calendars_code"),
    )
    op.create_index(
        "ix_business_calendars_active", "business_calendars", ["is_active"], unique=False
    )
    op.create_table(
        "ticket_subcategories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("code = lower(btrim(code))", name="ck_ticket_subcategories_code"),
        sa.ForeignKeyConstraint(["category_id"], ["ticket_categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "code", name="uq_ticket_subcategories_code"),
        sa.UniqueConstraint("id", "category_id", name="uq_ticket_subcategories_id_category"),
    )
    op.create_index(
        "ix_ticket_subcategories_active", "ticket_subcategories", ["is_active"], unique=False
    )
    op.create_index(
        "ix_ticket_subcategories_category", "ticket_subcategories", ["category_id"], unique=False
    )
    op.create_table(
        "business_calendar_holidays",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("calendar_id", sa.UUID(), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.ForeignKeyConstraint(["calendar_id"], ["business_calendars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("calendar_id", "holiday_date", name="uq_calendar_holiday"),
    )
    op.create_index(
        "ix_calendar_holidays_calendar", "business_calendar_holidays", ["calendar_id"], unique=False
    )
    op.create_index(
        "ix_calendar_holidays_date", "business_calendar_holidays", ["holiday_date"], unique=False
    )
    op.create_table(
        "business_working_periods",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("calendar_id", sa.UUID(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.CheckConstraint("start_time < end_time", name="ck_working_periods_chronology"),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_working_periods_weekday"),
        sa.ForeignKeyConstraint(["calendar_id"], ["business_calendars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("calendar_id", "weekday", "start_time", name="uq_working_period_start"),
    )
    op.create_index(
        "ix_working_periods_calendar", "business_working_periods", ["calendar_id"], unique=False
    )
    op.create_table(
        "sla_policies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("calendar_id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("pause_on_waiting", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("due_soon_percent", sa.Integer(), server_default=sa.text("20"), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("code = upper(btrim(code))", name="ck_sla_policies_code"),
        sa.CheckConstraint("due_soon_percent BETWEEN 1 AND 100", name="ck_sla_due_soon_percent"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_sla_policies_effective_range",
        ),
        sa.ForeignKeyConstraint(["calendar_id"], ["business_calendars.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["ticket_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_sla_policies_code"),
    )
    op.create_index("ix_sla_policies_active", "sla_policies", ["is_active"], unique=False)
    op.create_index("ix_sla_policies_category", "sla_policies", ["category_id"], unique=False)
    op.create_index(
        "ix_sla_policies_effective",
        "sla_policies",
        ["effective_from", "effective_to"],
        unique=False,
    )
    op.create_table(
        "sla_policy_targets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("policy_id", sa.UUID(), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("first_response_minutes", sa.Integer(), nullable=False),
        sa.Column("resolution_minutes", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')", name="ck_sla_targets_priority"
        ),
        sa.CheckConstraint(
            "first_response_minutes > 0 AND resolution_minutes > 0", name="ck_sla_targets_minutes"
        ),
        sa.ForeignKeyConstraint(["policy_id"], ["sla_policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "priority", name="uq_sla_policy_priority"),
    )
    op.create_index("ix_sla_targets_policy", "sla_policy_targets", ["policy_id"], unique=False)
    op.create_table(
        "ticket_comments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.String(length=50), nullable=False),
        sa.Column("author_user_id", sa.UUID(), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "visibility IN ('internal', 'requester')", name="ck_ticket_comments_visibility"
        ),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["maintenance_tickets.ticket_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ticket_comments_author", "ticket_comments", ["author_user_id"], unique=False
    )
    op.create_index(
        "ix_ticket_comments_ticket", "ticket_comments", ["ticket_id", "created_at"], unique=False
    )
    op.create_table(
        "ticket_sla_states",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.String(length=50), nullable=False),
        sa.Column("policy_id", sa.UUID(), nullable=False),
        sa.Column("policy_code", sa.String(length=50), nullable=False),
        sa.Column("policy_name", sa.String(length=200), nullable=False),
        sa.Column("calendar_id", sa.UUID(), nullable=False),
        sa.Column("calendar_code", sa.String(length=50), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("calendar_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pause_on_waiting", sa.Boolean(), nullable=False),
        sa.Column("due_soon_percent", sa.Integer(), nullable=False),
        sa.Column("first_response_target_minutes", sa.Integer(), nullable=False),
        sa.Column("resolution_target_minutes", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_response_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolution_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_response_remaining_minutes", sa.Integer(), nullable=True),
        sa.Column("resolution_remaining_minutes", sa.Integer(), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurrence_number", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "due_soon_percent BETWEEN 1 AND 100", name="ck_ticket_sla_due_soon_percent"
        ),
        sa.CheckConstraint(
            "first_response_due_at >= started_at AND resolution_due_at >= started_at",
            name="ck_ticket_sla_due_chronology",
        ),
        sa.CheckConstraint(
            "first_response_remaining_minutes IS NULL OR first_response_remaining_minutes >= 0",
            name="ck_ticket_sla_response_remaining",
        ),
        sa.CheckConstraint(
            "first_response_target_minutes > 0 AND resolution_target_minutes > 0",
            name="ck_ticket_sla_target_minutes",
        ),
        sa.CheckConstraint("occurrence_number > 0", name="ck_ticket_sla_occurrence"),
        sa.CheckConstraint(
            "resolution_remaining_minutes IS NULL OR resolution_remaining_minutes >= 0",
            name="ck_ticket_sla_resolution_remaining",
        ),
        sa.ForeignKeyConstraint(["calendar_id"], ["business_calendars.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["policy_id"], ["sla_policies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["maintenance_tickets.ticket_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", name="uq_ticket_sla_ticket"),
    )
    op.create_index("ix_ticket_sla_policy", "ticket_sla_states", ["policy_id"], unique=False)
    op.create_index(
        "ix_ticket_sla_resolution_due", "ticket_sla_states", ["resolution_due_at"], unique=False
    )
    op.create_index(
        "ix_ticket_sla_response_due", "ticket_sla_states", ["first_response_due_at"], unique=False
    )
    op.create_table(
        "ticket_escalation_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.String(length=50), nullable=False),
        sa.Column("ticket_sla_id", sa.UUID(), nullable=True),
        sa.Column("rule_code", sa.String(length=50), nullable=False),
        sa.Column("clock_type", sa.String(length=30), nullable=True),
        sa.Column("occurrence_number", sa.Integer(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "clock_type IS NULL OR clock_type IN ('first_response', 'resolution')",
            name="ck_ticket_escalations_clock",
        ),
        sa.CheckConstraint(
            "rule_code IN ('first_response_due_soon', 'first_response_breached', 'resolution_due_soon', 'resolution_breached', 'repeated_reopen', 'critical_priority')",
            name="ck_ticket_escalations_rule",
        ),
        sa.CheckConstraint("occurrence_number > 0", name="ck_ticket_escalations_occurrence"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["maintenance_tickets.ticket_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["ticket_sla_id"], ["ticket_sla_states.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ticket_id",
            "rule_code",
            "occurrence_number",
            name="uq_ticket_escalation_rule_occurrence",
        ),
    )
    op.create_index(
        "ix_ticket_escalations_rule", "ticket_escalation_events", ["rule_code"], unique=False
    )
    op.create_index(
        "ix_ticket_escalations_ticket",
        "ticket_escalation_events",
        ["ticket_id", "detected_at"],
        unique=False,
    )
    op.create_table(
        "ticket_sla_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_sla_id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.String(length=50), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("clock_type", sa.String(length=30), nullable=True),
        sa.Column("occurrence_number", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "clock_type IS NULL OR clock_type IN ('first_response', 'resolution')",
            name="ck_ticket_sla_events_clock",
        ),
        sa.CheckConstraint(
            "event_type IN ('policy_applied', 'clock_started', 'paused', 'resumed', 'first_response_recorded', 'target_met', 'breach_detected', 'resolved', 'reopened', 'stopped')",
            name="ck_ticket_sla_events_type",
        ),
        sa.CheckConstraint("occurrence_number > 0", name="ck_ticket_sla_events_occurrence"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["maintenance_tickets.ticket_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["ticket_sla_id"], ["ticket_sla_states.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ticket_sla_events_state", "ticket_sla_events", ["ticket_sla_id"], unique=False
    )
    op.create_index(
        "ix_ticket_sla_events_ticket",
        "ticket_sla_events",
        ["ticket_id", "occurred_at"],
        unique=False,
    )
    op.create_index("ix_ticket_sla_events_type", "ticket_sla_events", ["event_type"], unique=False)
    op.create_table(
        "ticket_comment_attachments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("comment_id", sa.UUID(), nullable=False),
        sa.Column("asset_attachment_id", sa.UUID(), nullable=True),
        sa.Column("work_order_attachment_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "((asset_attachment_id IS NOT NULL AND work_order_attachment_id IS NULL) OR (asset_attachment_id IS NULL AND work_order_attachment_id IS NOT NULL))",
            name="ck_ticket_comment_attachment_source",
        ),
        sa.ForeignKeyConstraint(
            ["asset_attachment_id"], ["asset_attachments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["comment_id"], ["ticket_comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["work_order_attachment_id"], ["work_order_attachments.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "comment_id", "asset_attachment_id", name="uq_ticket_comment_asset_attachment"
        ),
        sa.UniqueConstraint(
            "comment_id", "work_order_attachment_id", name="uq_ticket_comment_work_order_attachment"
        ),
    )
    op.create_index(
        "ix_ticket_comment_attachments_comment",
        "ticket_comment_attachments",
        ["comment_id"],
        unique=False,
    )
    op.add_column(
        "maintenance_tickets", sa.Column("reporter_name", sa.String(length=200), nullable=True)
    )
    op.add_column(
        "maintenance_tickets", sa.Column("reporter_email", sa.String(length=254), nullable=True)
    )
    op.add_column(
        "maintenance_tickets", sa.Column("reporter_phone", sa.String(length=40), nullable=True)
    )
    op.add_column("maintenance_tickets", sa.Column("category_id", sa.UUID(), nullable=True))
    op.add_column("maintenance_tickets", sa.Column("subcategory_id", sa.UUID(), nullable=True))
    op.add_column(
        "maintenance_tickets",
        sa.Column(
            "impact", sa.String(length=20), server_default=sa.text("'medium'"), nullable=False
        ),
    )
    op.add_column(
        "maintenance_tickets",
        sa.Column(
            "urgency", sa.String(length=20), server_default=sa.text("'medium'"), nullable=False
        ),
    )
    op.add_column("maintenance_tickets", sa.Column("intake_source_id", sa.UUID(), nullable=True))
    op.add_column("maintenance_tickets", sa.Column("support_group_id", sa.UUID(), nullable=True))
    op.add_column("maintenance_tickets", sa.Column("assigned_user_id", sa.UUID(), nullable=True))
    op.add_column(
        "maintenance_tickets",
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("maintenance_tickets", sa.Column("waiting_reason", sa.Text(), nullable=True))
    op.add_column(
        "maintenance_tickets",
        sa.Column("waiting_previous_status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "maintenance_tickets", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "maintenance_tickets", sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "maintenance_tickets", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("maintenance_tickets", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.add_column(
        "maintenance_tickets",
        sa.Column("reopen_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.execute(
        """
        UPDATE maintenance_tickets
        SET impact = CASE priority
                WHEN 'low' THEN 'low'
                WHEN 'medium' THEN 'medium'
                WHEN 'high' THEN 'high'
                ELSE 'critical'
            END,
            urgency = CASE priority
                WHEN 'low' THEN 'low'
                WHEN 'medium' THEN 'medium'
                WHEN 'high' THEN 'high'
                ELSE 'immediate'
            END
        """
    )
    op.drop_constraint("ck_tickets_status", "maintenance_tickets", type_="check")
    op.drop_constraint("ck_tickets_resolution_state", "maintenance_tickets", type_="check")
    op.create_check_constraint(
        "ck_tickets_status",
        "maintenance_tickets",
        "status IN ('open', 'assigned', 'in_progress', 'waiting', 'resolved', "
        "'closed', 'cancelled', 'reopened')",
    )
    op.create_check_constraint(
        "ck_tickets_impact",
        "maintenance_tickets",
        "impact IN ('low', 'medium', 'high', 'critical')",
    )
    op.create_check_constraint(
        "ck_tickets_urgency",
        "maintenance_tickets",
        "urgency IN ('low', 'medium', 'high', 'immediate')",
    )
    op.create_check_constraint(
        "ck_tickets_priority_matrix",
        "maintenance_tickets",
        "((impact = 'low' AND urgency = 'low' AND priority = 'low') OR "
        "(impact = 'low' AND urgency = 'medium' AND priority = 'low') OR "
        "(impact = 'low' AND urgency = 'high' AND priority = 'medium') OR "
        "(impact = 'low' AND urgency = 'immediate' AND priority = 'high') OR "
        "(impact = 'medium' AND urgency = 'low' AND priority = 'low') OR "
        "(impact = 'medium' AND urgency = 'medium' AND priority = 'medium') OR "
        "(impact = 'medium' AND urgency = 'high' AND priority = 'high') OR "
        "(impact = 'medium' AND urgency = 'immediate' AND priority = 'high') OR "
        "(impact = 'high' AND urgency = 'low' AND priority = 'medium') OR "
        "(impact = 'high' AND urgency = 'medium' AND priority = 'high') OR "
        "(impact = 'high' AND urgency = 'high' AND priority = 'high') OR "
        "(impact = 'high' AND urgency = 'immediate' AND priority = 'critical') OR "
        "(impact = 'critical' AND urgency = 'low' AND priority = 'high') OR "
        "(impact = 'critical' AND urgency = 'medium' AND priority = 'high') OR "
        "(impact = 'critical' AND urgency = 'high' AND priority = 'critical') OR "
        "(impact = 'critical' AND urgency = 'immediate' AND priority = 'critical'))",
    )
    op.create_check_constraint(
        "ck_tickets_resolution_state",
        "maintenance_tickets",
        "((status IN ('resolved', 'closed') AND resolved_at IS NOT NULL) OR "
        "(status NOT IN ('resolved', 'closed') AND resolved_at IS NULL))",
    )
    op.create_check_constraint(
        "ck_tickets_closed_state",
        "maintenance_tickets",
        "((status = 'closed' AND closed_at IS NOT NULL) OR "
        "(status <> 'closed' AND closed_at IS NULL))",
    )
    op.create_check_constraint(
        "ck_tickets_closed_chronology",
        "maintenance_tickets",
        "closed_at IS NULL OR (resolved_at IS NOT NULL AND closed_at >= resolved_at)",
    )
    op.create_check_constraint(
        "ck_tickets_cancelled_state",
        "maintenance_tickets",
        "((status = 'cancelled' AND cancelled_at IS NOT NULL "
        "AND cancellation_reason IS NOT NULL) OR "
        "(status <> 'cancelled' AND cancelled_at IS NULL "
        "AND cancellation_reason IS NULL))",
    )
    op.create_check_constraint(
        "ck_tickets_waiting_state",
        "maintenance_tickets",
        "((status = 'waiting' AND waiting_reason IS NOT NULL "
        "AND waiting_previous_status IN ('assigned', 'in_progress')) OR "
        "(status <> 'waiting' AND waiting_reason IS NULL "
        "AND waiting_previous_status IS NULL))",
    )
    op.create_check_constraint(
        "ck_tickets_reopen_count", "maintenance_tickets", "reopen_count >= 0"
    )
    op.create_check_constraint(
        "ck_tickets_first_response_chronology",
        "maintenance_tickets",
        "first_response_at IS NULL OR first_response_at >= created_at",
    )
    op.create_check_constraint(
        "ck_tickets_subcategory_requires_category",
        "maintenance_tickets",
        "subcategory_id IS NULL OR category_id IS NOT NULL",
    )
    op.create_index(
        "ix_tickets_assigned_user", "maintenance_tickets", ["assigned_user_id"], unique=False
    )
    op.create_index("ix_tickets_category", "maintenance_tickets", ["category_id"], unique=False)
    op.create_index("ix_tickets_priority", "maintenance_tickets", ["priority"], unique=False)
    op.create_index(
        "ix_tickets_support_group", "maintenance_tickets", ["support_group_id"], unique=False
    )
    op.create_foreign_key(
        "fk_tickets_category",
        "maintenance_tickets",
        "ticket_categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_tickets_subcategory_category",
        "maintenance_tickets",
        "ticket_subcategories",
        ["subcategory_id", "category_id"],
        ["id", "category_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_tickets_intake_source",
        "maintenance_tickets",
        "ticket_intake_sources",
        ["intake_source_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_tickets_assigned_user",
        "maintenance_tickets",
        "users",
        ["assigned_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_tickets_support_group",
        "maintenance_tickets",
        "support_groups",
        ["support_group_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        CREATE FUNCTION reject_ticket_history_mutation() RETURNS trigger AS $$
        BEGIN
            IF current_setting('app.demo_reset', true) = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'ticket history is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table_name in (
        "ticket_comments",
        "ticket_sla_events",
        "ticket_escalation_events",
    ):
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_append_only
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_ticket_history_mutation()
            """
        )


def downgrade() -> None:
    """Remove PM5 ticket operations and restore the legacy ticket contract."""

    for table_name in (
        "ticket_escalation_events",
        "ticket_sla_events",
        "ticket_comments",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table_name}_append_only ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS reject_ticket_history_mutation()")

    for constraint_name in (
        "ck_tickets_subcategory_requires_category",
        "ck_tickets_first_response_chronology",
        "ck_tickets_reopen_count",
        "ck_tickets_waiting_state",
        "ck_tickets_cancelled_state",
        "ck_tickets_closed_chronology",
        "ck_tickets_closed_state",
        "ck_tickets_resolution_state",
        "ck_tickets_priority_matrix",
        "ck_tickets_urgency",
        "ck_tickets_impact",
        "ck_tickets_status",
    ):
        op.drop_constraint(constraint_name, "maintenance_tickets", type_="check")

    op.execute(
        """
        UPDATE maintenance_tickets
        SET status = CASE
                WHEN status IN ('assigned', 'reopened') THEN 'open'
                WHEN status = 'waiting' THEN 'in_progress'
                WHEN status IN ('closed', 'cancelled') THEN 'resolved'
                ELSE status
            END,
            resolved_at = CASE
                WHEN status IN ('closed', 'cancelled')
                    THEN COALESCE(resolved_at, closed_at, cancelled_at, updated_at, created_at)
                ELSE resolved_at
            END,
            waiting_reason = NULL,
            waiting_previous_status = NULL,
            closed_at = NULL,
            cancelled_at = NULL,
            cancellation_reason = NULL
        """
    )

    op.drop_constraint("fk_tickets_support_group", "maintenance_tickets", type_="foreignkey")
    op.drop_constraint("fk_tickets_assigned_user", "maintenance_tickets", type_="foreignkey")
    op.drop_constraint("fk_tickets_intake_source", "maintenance_tickets", type_="foreignkey")
    op.drop_constraint("fk_tickets_subcategory_category", "maintenance_tickets", type_="foreignkey")
    op.drop_constraint("fk_tickets_category", "maintenance_tickets", type_="foreignkey")
    op.drop_index("ix_tickets_support_group", table_name="maintenance_tickets")
    op.drop_index("ix_tickets_priority", table_name="maintenance_tickets")
    op.drop_index("ix_tickets_category", table_name="maintenance_tickets")
    op.drop_index("ix_tickets_assigned_user", table_name="maintenance_tickets")
    op.drop_column("maintenance_tickets", "reopen_count")
    op.drop_column("maintenance_tickets", "cancellation_reason")
    op.drop_column("maintenance_tickets", "cancelled_at")
    op.drop_column("maintenance_tickets", "reopened_at")
    op.drop_column("maintenance_tickets", "closed_at")
    op.drop_column("maintenance_tickets", "waiting_previous_status")
    op.drop_column("maintenance_tickets", "waiting_reason")
    op.drop_column("maintenance_tickets", "first_response_at")
    op.drop_column("maintenance_tickets", "assigned_user_id")
    op.drop_column("maintenance_tickets", "support_group_id")
    op.drop_column("maintenance_tickets", "intake_source_id")
    op.drop_column("maintenance_tickets", "urgency")
    op.drop_column("maintenance_tickets", "impact")
    op.drop_column("maintenance_tickets", "subcategory_id")
    op.drop_column("maintenance_tickets", "category_id")
    op.drop_column("maintenance_tickets", "reporter_phone")
    op.drop_column("maintenance_tickets", "reporter_email")
    op.drop_column("maintenance_tickets", "reporter_name")
    op.create_check_constraint(
        "ck_tickets_status",
        "maintenance_tickets",
        "status IN ('open', 'in_progress', 'resolved')",
    )
    op.create_check_constraint(
        "ck_tickets_resolution_state",
        "maintenance_tickets",
        "((status = 'resolved' AND resolved_at IS NOT NULL) OR "
        "(status <> 'resolved' AND resolved_at IS NULL))",
    )
    op.drop_index("ix_ticket_comment_attachments_comment", table_name="ticket_comment_attachments")
    op.drop_table("ticket_comment_attachments")
    op.drop_index("ix_ticket_sla_events_type", table_name="ticket_sla_events")
    op.drop_index("ix_ticket_sla_events_ticket", table_name="ticket_sla_events")
    op.drop_index("ix_ticket_sla_events_state", table_name="ticket_sla_events")
    op.drop_table("ticket_sla_events")
    op.drop_index("ix_ticket_escalations_ticket", table_name="ticket_escalation_events")
    op.drop_index("ix_ticket_escalations_rule", table_name="ticket_escalation_events")
    op.drop_table("ticket_escalation_events")
    op.drop_index("ix_ticket_sla_response_due", table_name="ticket_sla_states")
    op.drop_index("ix_ticket_sla_resolution_due", table_name="ticket_sla_states")
    op.drop_index("ix_ticket_sla_policy", table_name="ticket_sla_states")
    op.drop_table("ticket_sla_states")
    op.drop_index("ix_ticket_comments_ticket", table_name="ticket_comments")
    op.drop_index("ix_ticket_comments_author", table_name="ticket_comments")
    op.drop_table("ticket_comments")
    op.drop_index("ix_sla_targets_policy", table_name="sla_policy_targets")
    op.drop_table("sla_policy_targets")
    op.drop_index("ix_sla_policies_effective", table_name="sla_policies")
    op.drop_index("ix_sla_policies_category", table_name="sla_policies")
    op.drop_index("ix_sla_policies_active", table_name="sla_policies")
    op.drop_table("sla_policies")
    op.drop_index("ix_working_periods_calendar", table_name="business_working_periods")
    op.drop_table("business_working_periods")
    op.drop_index("ix_calendar_holidays_date", table_name="business_calendar_holidays")
    op.drop_index("ix_calendar_holidays_calendar", table_name="business_calendar_holidays")
    op.drop_table("business_calendar_holidays")
    op.drop_index("ix_ticket_subcategories_category", table_name="ticket_subcategories")
    op.drop_index("ix_ticket_subcategories_active", table_name="ticket_subcategories")
    op.drop_table("ticket_subcategories")
    op.drop_index("ix_business_calendars_active", table_name="business_calendars")
    op.drop_table("business_calendars")
    op.drop_index("ix_ticket_sources_active", table_name="ticket_intake_sources")
    op.drop_table("ticket_intake_sources")
    op.drop_index("ix_ticket_categories_active", table_name="ticket_categories")
    op.drop_table("ticket_categories")
    op.drop_index("ix_support_groups_active", table_name="support_groups")
    op.drop_table("support_groups")
