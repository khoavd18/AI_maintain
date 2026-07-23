"""Add preventive plans, versioned checklists, and standalone work orders.

Revision ID: 20260720_0004
Revises: 20260718_0003
Create Date: 2026-07-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0004"
down_revision: str | None = "20260718_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the Product Milestone 4 maintenance-planning schema."""

    op.create_table(
        "checklist_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("asset_type", sa.String(length=40), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("code = upper(btrim(code))", name="ck_checklist_templates_code"),
        sa.CheckConstraint(
            "version_number > 0", name="ck_checklist_templates_version"
        ),
        sa.CheckConstraint(
            "asset_type IS NULL OR asset_type IN ('hvac', 'pump', 'generator')",
            name="ck_checklist_templates_asset_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_checklist_templates_status",
        ),
        sa.CheckConstraint(
            "((status = 'archived' AND archived_at IS NOT NULL) OR "
            "(status = 'active' AND archived_at IS NULL))",
            name="ck_checklist_templates_archive_state",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", "version_number", name="uq_checklist_template_version"),
    )
    op.create_index("ix_checklist_templates_code", "checklist_templates", ["code"])
    op.create_index("ix_checklist_templates_status", "checklist_templates", ["status"])
    op.create_index(
        "ix_checklist_templates_asset_type", "checklist_templates", ["asset_type"]
    )

    op.create_table(
        "checklist_template_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("response_type", sa.String(length=20), nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("safety_critical", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "allow_not_applicable", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("expected_unit", sa.String(length=40), nullable=True),
        sa.Column("minimum_value", sa.Float(), nullable=True),
        sa.Column("maximum_value", sa.Float(), nullable=True),
        sa.Column("guidance", sa.Text(), nullable=True),
        sa.CheckConstraint("sequence > 0", name="ck_checklist_items_sequence"),
        sa.CheckConstraint(
            "response_type IN ('checkbox', 'pass_fail', 'numeric', 'text')",
            name="ck_checklist_items_response_type",
        ),
        sa.CheckConstraint(
            "minimum_value IS NULL OR maximum_value IS NULL OR "
            "minimum_value <= maximum_value",
            name="ck_checklist_items_numeric_range",
        ),
        sa.CheckConstraint(
            "response_type = 'numeric' OR "
            "(minimum_value IS NULL AND maximum_value IS NULL AND expected_unit IS NULL)",
            name="ck_checklist_items_numeric_fields",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["checklist_templates.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "sequence", name="uq_checklist_item_sequence"),
    )
    op.create_index(
        "ix_checklist_items_template", "checklist_template_items", ["template_id"]
    )

    op.create_table(
        "preventive_maintenance_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("asset_id", sa.String(length=50), nullable=False),
        sa.Column("schedule_type", sa.String(length=20), server_default="interval", nullable=False),
        sa.Column("interval_value", sa.Integer(), nullable=False),
        sa.Column("interval_unit", sa.String(length=10), nullable=False),
        sa.Column("recurrence_rule", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "local_timezone",
            sa.String(length=64),
            server_default="Asia/Ho_Chi_Minh",
            nullable=False,
        ),
        sa.Column("lead_time_days", sa.Integer(), server_default="7", nullable=False),
        sa.Column("grace_period_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_due_date", sa.Date(), nullable=True),
        sa.Column("last_generated_due_date", sa.Date(), nullable=True),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("default_priority", sa.String(length=20), nullable=False),
        sa.Column("default_assignee_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("checklist_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archive_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("plan_code = upper(btrim(plan_code))", name="ck_pm_plans_code"),
        sa.CheckConstraint("schedule_type = 'interval'", name="ck_pm_plans_schedule_type"),
        sa.CheckConstraint("recurrence_rule IS NULL", name="ck_pm_plans_no_freeform_rrule"),
        sa.CheckConstraint("interval_value > 0", name="ck_pm_plans_interval_value"),
        sa.CheckConstraint(
            "interval_unit IN ('day', 'week', 'month', 'year')",
            name="ck_pm_plans_interval_unit",
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="ck_pm_plans_date_range"
        ),
        sa.CheckConstraint(
            "lead_time_days BETWEEN 0 AND 365 AND grace_period_days BETWEEN 0 AND 365",
            name="ck_pm_plans_lead_grace",
        ),
        sa.CheckConstraint(
            "estimated_duration_minutes > 0", name="ck_pm_plans_duration"
        ),
        sa.CheckConstraint(
            "default_priority IN ('low', 'medium', 'high', 'critical')",
            name="ck_pm_plans_priority",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'archived')", name="ck_pm_plans_status"
        ),
        sa.CheckConstraint(
            "((status = 'active' AND is_active = true AND paused_at IS NULL "
            "AND archived_at IS NULL AND archive_reason IS NULL) OR "
            "(status = 'paused' AND is_active = false AND paused_at IS NOT NULL "
            "AND archived_at IS NULL AND archive_reason IS NULL) OR "
            "(status = 'archived' AND is_active = false AND archived_at IS NOT NULL "
            "AND archive_reason IS NOT NULL))",
            name="ck_pm_plans_lifecycle_state",
        ),
        sa.CheckConstraint(
            "next_due_date IS NULL OR next_due_date >= start_date",
            name="ck_pm_plans_next_due",
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.asset_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["default_assignee_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["checklist_template_id"], ["checklist_templates.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_code", name="uq_pm_plans_code"),
        sa.UniqueConstraint("id", "asset_id", name="uq_pm_plans_id_asset"),
    )
    op.create_index("ix_pm_plans_asset", "preventive_maintenance_plans", ["asset_id"])
    op.create_index("ix_pm_plans_status", "preventive_maintenance_plans", ["status"])
    op.create_index(
        "ix_pm_plans_next_due", "preventive_maintenance_plans", ["next_due_date"]
    )

    op.execute("CREATE SEQUENCE work_order_number_seq START WITH 1 INCREMENT BY 1")
    op.create_table(
        "work_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_order_number", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("work_order_type", sa.String(length=20), nullable=False),
        sa.Column("asset_id", sa.String(length=50), nullable=False),
        sa.Column("preventive_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_ticket_id", sa.String(length=50), nullable=True),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column(
            "local_timezone",
            sa.String(length=64),
            server_default="Asia/Ho_Chi_Minh",
            nullable=False,
        ),
        sa.Column("grace_period_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("completion_summary", sa.Text(), nullable=True),
        sa.Column("safety_notes", sa.Text(), nullable=True),
        sa.Column("labor_minutes", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="planned", nullable=False),
        sa.Column("hold_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "work_order_type IN ('preventive', 'corrective', 'inspection', 'emergency')",
            name="ck_work_orders_type",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name="ck_work_orders_priority",
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'assigned', 'in_progress', 'on_hold', "
            "'completed', 'verified', 'cancelled')",
            name="ck_work_orders_status",
        ),
        sa.CheckConstraint(
            "work_order_type <> 'preventive' OR preventive_plan_id IS NOT NULL",
            name="ck_work_orders_preventive_source",
        ),
        sa.CheckConstraint(
            "preventive_plan_id IS NULL OR work_order_type = 'preventive'",
            name="ck_work_orders_plan_type",
        ),
        sa.CheckConstraint(
            "estimated_duration_minutes > 0 AND "
            "(labor_minutes IS NULL OR labor_minutes >= 0) AND grace_period_days >= 0",
            name="ck_work_orders_duration",
        ),
        sa.CheckConstraint(
            "scheduled_end_at IS NULL OR scheduled_start_at IS NULL OR "
            "scheduled_end_at >= scheduled_start_at",
            name="ck_work_orders_schedule_chronology",
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'cancelled') OR assigned_to_user_id IS NOT NULL",
            name="ck_work_orders_assignment_state",
        ),
        sa.CheckConstraint(
            "((status IN ('in_progress', 'completed', 'verified') "
            "AND started_at IS NOT NULL) OR "
            "status IN ('assigned', 'on_hold', 'cancelled') OR "
            "(status = 'planned' AND started_at IS NULL))",
            name="ck_work_orders_started_state",
        ),
        sa.CheckConstraint(
            "((status IN ('completed', 'verified') AND completed_at IS NOT NULL) OR "
            "(status NOT IN ('completed', 'verified') AND completed_at IS NULL))",
            name="ck_work_orders_completed_state",
        ),
        sa.CheckConstraint(
            "((status = 'verified' AND verified_at IS NOT NULL "
            "AND verified_by_user_id IS NOT NULL) OR "
            "(status <> 'verified' AND verified_at IS NULL "
            "AND verified_by_user_id IS NULL))",
            name="ck_work_orders_verified_state",
        ),
        sa.CheckConstraint(
            "((status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND cancellation_reason IS NOT NULL) OR "
            "(status <> 'cancelled' AND cancelled_at IS NULL "
            "AND cancellation_reason IS NULL))",
            name="ck_work_orders_cancelled_state",
        ),
        sa.CheckConstraint(
            "((status = 'on_hold' AND hold_reason IS NOT NULL) OR "
            "(status <> 'on_hold' AND hold_reason IS NULL))",
            name="ck_work_orders_hold_state",
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.asset_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["preventive_plan_id", "asset_id"],
            ["preventive_maintenance_plans.id", "preventive_maintenance_plans.asset_id"],
            name="fk_work_orders_plan_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_ticket_id", "asset_id"],
            ["maintenance_tickets.ticket_id", "maintenance_tickets.asset_id"],
            name="fk_work_orders_ticket_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["verified_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("work_order_number", name="uq_work_orders_number"),
        sa.UniqueConstraint("id", "asset_id", name="uq_work_orders_id_asset"),
        sa.UniqueConstraint(
            "preventive_plan_id", "due_date", name="uq_work_orders_plan_occurrence"
        ),
    )
    op.create_index("ix_work_orders_asset", "work_orders", ["asset_id"])
    op.create_index("ix_work_orders_plan", "work_orders", ["preventive_plan_id"])
    op.create_index("ix_work_orders_ticket", "work_orders", ["source_ticket_id"])
    op.create_index("ix_work_orders_assignee", "work_orders", ["assigned_to_user_id"])
    op.create_index("ix_work_orders_status", "work_orders", ["status"])
    op.create_index("ix_work_orders_due_date", "work_orders", ["due_date"])
    op.create_index(
        "uq_work_orders_active_corrective_ticket",
        "work_orders",
        ["source_ticket_id"],
        unique=True,
        postgresql_where=sa.text(
            "source_ticket_id IS NOT NULL AND work_order_type = 'corrective' "
            "AND status NOT IN ('verified', 'cancelled')"
        ),
    )

    op.create_table(
        "work_order_checklist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_template_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("response_type", sa.String(length=20), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("safety_critical", sa.Boolean(), nullable=False),
        sa.Column("allow_not_applicable", sa.Boolean(), nullable=False),
        sa.Column("expected_unit", sa.String(length=40), nullable=True),
        sa.Column("minimum_value", sa.Float(), nullable=True),
        sa.Column("maximum_value", sa.Float(), nullable=True),
        sa.Column("guidance", sa.Text(), nullable=True),
        sa.Column("result_status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("boolean_value", sa.Boolean(), nullable=True),
        sa.Column("numeric_value", sa.Float(), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("sequence > 0", name="ck_wo_checklist_sequence"),
        sa.CheckConstraint(
            "response_type IN ('checkbox', 'pass_fail', 'numeric', 'text')",
            name="ck_wo_checklist_response_type",
        ),
        sa.CheckConstraint(
            "result_status IN ('pending', 'completed', 'pass', 'fail', 'not_applicable')",
            name="ck_wo_checklist_result_status",
        ),
        sa.CheckConstraint(
            "minimum_value IS NULL OR maximum_value IS NULL OR "
            "minimum_value <= maximum_value",
            name="ck_wo_checklist_numeric_range",
        ),
        sa.CheckConstraint(
            "result_status <> 'not_applicable' OR allow_not_applicable = true",
            name="ck_wo_checklist_not_applicable",
        ),
        sa.CheckConstraint(
            "((result_status = 'pending' AND completed_at IS NULL "
            "AND completed_by_user_id IS NULL) OR "
            "(result_status <> 'pending' AND completed_at IS NOT NULL "
            "AND completed_by_user_id IS NOT NULL))",
            name="ck_wo_checklist_completion_state",
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"], ["work_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_template_item_id"],
            ["checklist_template_items.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("work_order_id", "sequence", name="uq_wo_checklist_sequence"),
    )
    op.create_index(
        "ix_wo_checklist_work_order",
        "work_order_checklist_items",
        ["work_order_id"],
    )

    op.create_table(
        "work_order_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "category IN ('before_photo', 'after_photo', 'inspection_document', "
            "'completion_document', 'safety_document', 'other')",
            name="ck_wo_attachments_category",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_wo_attachments_size"),
        sa.CheckConstraint("length(checksum) = 64", name="ck_wo_attachments_checksum"),
        sa.ForeignKeyConstraint(
            ["work_order_id", "asset_id"],
            ["work_orders.id", "work_orders.asset_id"],
            name="fk_wo_attachments_work_order_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_wo_attachments_storage_key"),
    )
    op.create_index(
        "ix_wo_attachments_work_order", "work_order_attachments", ["work_order_id"]
    )
    op.create_index(
        "ix_wo_attachments_active",
        "work_order_attachments",
        ["work_order_id", "deleted_at"],
    )

    op.add_column(
        "maintenance_logs",
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_logs_work_order_asset",
        "maintenance_logs",
        "work_orders",
        ["work_order_id", "asset_id"],
        ["id", "asset_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_logs_work_order_id", "maintenance_logs", ["work_order_id"]
    )
    op.create_index(
        "ix_logs_work_order_id", "maintenance_logs", ["work_order_id"]
    )


def downgrade() -> None:
    """Remove Product Milestone 4 entities while preserving legacy transactions."""

    op.drop_index("ix_logs_work_order_id", table_name="maintenance_logs")
    op.drop_constraint("uq_logs_work_order_id", "maintenance_logs", type_="unique")
    op.drop_constraint("fk_logs_work_order_asset", "maintenance_logs", type_="foreignkey")
    op.drop_column("maintenance_logs", "work_order_id")

    op.drop_index("ix_wo_attachments_active", table_name="work_order_attachments")
    op.drop_index("ix_wo_attachments_work_order", table_name="work_order_attachments")
    op.drop_table("work_order_attachments")
    op.drop_index("ix_wo_checklist_work_order", table_name="work_order_checklist_items")
    op.drop_table("work_order_checklist_items")
    op.drop_index("uq_work_orders_active_corrective_ticket", table_name="work_orders")
    op.drop_index("ix_work_orders_due_date", table_name="work_orders")
    op.drop_index("ix_work_orders_status", table_name="work_orders")
    op.drop_index("ix_work_orders_assignee", table_name="work_orders")
    op.drop_index("ix_work_orders_ticket", table_name="work_orders")
    op.drop_index("ix_work_orders_plan", table_name="work_orders")
    op.drop_index("ix_work_orders_asset", table_name="work_orders")
    op.drop_table("work_orders")
    op.execute("DROP SEQUENCE work_order_number_seq")
    op.drop_index("ix_pm_plans_next_due", table_name="preventive_maintenance_plans")
    op.drop_index("ix_pm_plans_status", table_name="preventive_maintenance_plans")
    op.drop_index("ix_pm_plans_asset", table_name="preventive_maintenance_plans")
    op.drop_table("preventive_maintenance_plans")
    op.drop_index("ix_checklist_items_template", table_name="checklist_template_items")
    op.drop_table("checklist_template_items")
    op.drop_index("ix_checklist_templates_asset_type", table_name="checklist_templates")
    op.drop_index("ix_checklist_templates_status", table_name="checklist_templates")
    op.drop_index("ix_checklist_templates_code", table_name="checklist_templates")
    op.drop_table("checklist_templates")
