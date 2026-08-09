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

class MaintenanceLog(Base):
    """Append-only field maintenance result linked to an asset and optional ticket."""

    __tablename__ = "maintenance_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ticket_id", "asset_id"],
            ["maintenance_tickets.ticket_id", "maintenance_tickets.asset_id"],
            name="fk_logs_ticket_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["work_order_id", "asset_id"],
            ["work_orders.id", "work_orders.asset_id"],
            name="fk_logs_work_order_asset",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "maintenance_type IN ('preventive', 'corrective', 'inspection', 'emergency')",
            name="ck_logs_maintenance_type",
        ),
        CheckConstraint(
            "maintenance_result IN ('resolved', 'partially_resolved', "
            "'monitoring_required', 'vendor_required')",
            name="ck_logs_maintenance_result",
        ),
        CheckConstraint(
            "((maintenance_result = 'resolved' AND follow_up_required = false) OR "
            "(maintenance_result <> 'resolved' AND follow_up_required = true))",
            name="ck_logs_follow_up_result",
        ),
        CheckConstraint(
            "next_maintenance_date > maintenance_date",
            name="ck_logs_maintenance_chronology",
        ),
        UniqueConstraint("work_order_id", name="uq_logs_work_order_id"),
        Index("ix_logs_asset_id", "asset_id"),
        Index("ix_logs_ticket_id", "ticket_id"),
        Index("ix_logs_work_order_id", "work_order_id"),
        Index("ix_logs_maintenance_date", "maintenance_date"),
    )

    log_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    ticket_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    work_order_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="RESTRICT"),
        nullable=False,
    )
    maintenance_date: Mapped[date] = mapped_column(Date, nullable=False)
    maintenance_type: Mapped[str] = mapped_column(String(30), nullable=False)
    technician_id: Mapped[str] = mapped_column(String(50), nullable=False)
    inspection_result: Mapped[str] = mapped_column(Text, nullable=False)
    actions_taken: Mapped[str] = mapped_column(Text, nullable=False)
    parts_replaced: Mapped[str | None] = mapped_column(Text, nullable=True)
    technician_note: Mapped[str] = mapped_column(Text, nullable=False)
    maintenance_result: Mapped[str] = mapped_column(String(30), nullable=False)
    follow_up_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    next_maintenance_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
    )

class ChecklistTemplate(Base):
    """Immutable-version checklist definition used by preventive plans."""

    __tablename__ = "checklist_templates"
    __table_args__ = (
        CheckConstraint("code = upper(btrim(code))", name="ck_checklist_templates_code"),
        CheckConstraint("version_number > 0", name="ck_checklist_templates_version"),
        CheckConstraint(
            "asset_type IS NULL OR asset_type IN ('hvac', 'pump', 'generator')",
            name="ck_checklist_templates_asset_type",
        ),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_checklist_templates_status",
        ),
        CheckConstraint(
            "((status = 'archived' AND archived_at IS NOT NULL) OR "
            "(status = 'active' AND archived_at IS NULL))",
            name="ck_checklist_templates_archive_state",
        ),
        UniqueConstraint("code", "version_number", name="uq_checklist_template_version"),
        Index("ix_checklist_templates_code", "code"),
        Index("ix_checklist_templates_status", "status"),
        Index("ix_checklist_templates_asset_type", "asset_type"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default=text("'active'")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
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
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}

class ChecklistTemplateItem(Base):
    """One ordered, plain-text instruction in an immutable template version."""

    __tablename__ = "checklist_template_items"
    __table_args__ = (
        CheckConstraint("sequence > 0", name="ck_checklist_items_sequence"),
        CheckConstraint(
            "response_type IN ('checkbox', 'pass_fail', 'numeric', 'text')",
            name="ck_checklist_items_response_type",
        ),
        CheckConstraint(
            "minimum_value IS NULL OR maximum_value IS NULL OR minimum_value <= maximum_value",
            name="ck_checklist_items_numeric_range",
        ),
        CheckConstraint(
            "response_type = 'numeric' OR "
            "(minimum_value IS NULL AND maximum_value IS NULL AND expected_unit IS NULL)",
            name="ck_checklist_items_numeric_fields",
        ),
        UniqueConstraint("template_id", "sequence", name="uq_checklist_item_sequence"),
        Index("ix_checklist_items_template", "template_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    template_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("checklist_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    response_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    safety_critical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    allow_not_applicable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    expected_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    minimum_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    maximum_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    guidance: Mapped[str | None] = mapped_column(Text, nullable=True)

class PreventiveMaintenancePlan(Base):
    """Recurring maintenance intent; never an executable work order itself."""

    __tablename__ = "preventive_maintenance_plans"
    __table_args__ = (
        CheckConstraint("plan_code = upper(btrim(plan_code))", name="ck_pm_plans_code"),
        CheckConstraint("schedule_type = 'interval'", name="ck_pm_plans_schedule_type"),
        CheckConstraint("recurrence_rule IS NULL", name="ck_pm_plans_no_freeform_rrule"),
        CheckConstraint("interval_value > 0", name="ck_pm_plans_interval_value"),
        CheckConstraint(
            "interval_unit IN ('day', 'week', 'month', 'year')",
            name="ck_pm_plans_interval_unit",
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_pm_plans_date_range",
        ),
        CheckConstraint(
            "lead_time_days BETWEEN 0 AND 365 AND grace_period_days BETWEEN 0 AND 365",
            name="ck_pm_plans_lead_grace",
        ),
        CheckConstraint(
            "estimated_duration_minutes > 0",
            name="ck_pm_plans_duration",
        ),
        CheckConstraint(
            "default_priority IN ('low', 'medium', 'high', 'critical')",
            name="ck_pm_plans_priority",
        ),
        CheckConstraint(
            "status IN ('active', 'paused', 'archived')",
            name="ck_pm_plans_status",
        ),
        CheckConstraint(
            "((status = 'active' AND is_active = true AND paused_at IS NULL "
            "AND archived_at IS NULL AND archive_reason IS NULL) OR "
            "(status = 'paused' AND is_active = false AND paused_at IS NOT NULL "
            "AND archived_at IS NULL AND archive_reason IS NULL) OR "
            "(status = 'archived' AND is_active = false AND archived_at IS NOT NULL "
            "AND archive_reason IS NOT NULL))",
            name="ck_pm_plans_lifecycle_state",
        ),
        CheckConstraint(
            "next_due_date IS NULL OR next_due_date >= start_date",
            name="ck_pm_plans_next_due",
        ),
        UniqueConstraint("plan_code", name="uq_pm_plans_code"),
        UniqueConstraint("id", "asset_id", name="uq_pm_plans_id_asset"),
        Index("ix_pm_plans_asset", "asset_id"),
        Index("ix_pm_plans_status", "status"),
        Index("ix_pm_plans_next_due", "next_due_date"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    plan_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="RESTRICT"), nullable=False
    )
    schedule_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="interval", server_default=text("'interval'")
    )
    interval_value: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_unit: Mapped[str] = mapped_column(String(10), nullable=False)
    recurrence_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    local_timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Ho_Chi_Minh",
        server_default=text("'Asia/Ho_Chi_Minh'"),
    )
    lead_time_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7, server_default=text("7")
    )
    grace_period_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_generated_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    default_priority: Mapped[str] = mapped_column(String(20), nullable=False)
    default_assignee_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    checklist_template_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("checklist_templates.id", ondelete="RESTRICT"),
        nullable=True,
    )
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default=text("'active'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
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

class WorkOrder(Base):
    """One executable maintenance job, independent from its source intent."""

    __tablename__ = "work_orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["preventive_plan_id", "asset_id"],
            ["preventive_maintenance_plans.id", "preventive_maintenance_plans.asset_id"],
            name="fk_work_orders_plan_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_ticket_id", "asset_id"],
            ["maintenance_tickets.ticket_id", "maintenance_tickets.asset_id"],
            name="fk_work_orders_ticket_asset",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "work_order_type IN ('preventive', 'corrective', 'inspection', 'emergency')",
            name="ck_work_orders_type",
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name="ck_work_orders_priority",
        ),
        CheckConstraint(
            "status IN ('planned', 'assigned', 'in_progress', 'on_hold', "
            "'completed', 'verified', 'cancelled')",
            name="ck_work_orders_status",
        ),
        CheckConstraint(
            "work_order_type <> 'preventive' OR preventive_plan_id IS NOT NULL",
            name="ck_work_orders_preventive_source",
        ),
        CheckConstraint(
            "preventive_plan_id IS NULL OR work_order_type = 'preventive'",
            name="ck_work_orders_plan_type",
        ),
        CheckConstraint(
            "estimated_duration_minutes > 0 AND "
            "(labor_minutes IS NULL OR labor_minutes >= 0) AND grace_period_days >= 0",
            name="ck_work_orders_duration",
        ),
        CheckConstraint(
            "scheduled_end_at IS NULL OR scheduled_start_at IS NULL OR "
            "scheduled_end_at >= scheduled_start_at",
            name="ck_work_orders_schedule_chronology",
        ),
        CheckConstraint(
            "status IN ('planned', 'cancelled') OR assigned_to_user_id IS NOT NULL",
            name="ck_work_orders_assignment_state",
        ),
        CheckConstraint(
            "((status IN ('in_progress', 'completed', 'verified') "
            "AND started_at IS NOT NULL) OR "
            "status IN ('assigned', 'on_hold', 'cancelled') OR "
            "(status = 'planned' AND started_at IS NULL))",
            name="ck_work_orders_started_state",
        ),
        CheckConstraint(
            "((status IN ('completed', 'verified') AND completed_at IS NOT NULL) OR "
            "(status NOT IN ('completed', 'verified') AND completed_at IS NULL))",
            name="ck_work_orders_completed_state",
        ),
        CheckConstraint(
            "((status = 'verified' AND verified_at IS NOT NULL "
            "AND verified_by_user_id IS NOT NULL) OR "
            "(status <> 'verified' AND verified_at IS NULL AND verified_by_user_id IS NULL))",
            name="ck_work_orders_verified_state",
        ),
        CheckConstraint(
            "((status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND cancellation_reason IS NOT NULL) OR "
            "(status <> 'cancelled' AND cancelled_at IS NULL "
            "AND cancellation_reason IS NULL))",
            name="ck_work_orders_cancelled_state",
        ),
        CheckConstraint(
            "((status = 'on_hold' AND hold_reason IS NOT NULL) OR "
            "(status <> 'on_hold' AND hold_reason IS NULL))",
            name="ck_work_orders_hold_state",
        ),
        UniqueConstraint("work_order_number", name="uq_work_orders_number"),
        UniqueConstraint("id", "asset_id", name="uq_work_orders_id_asset"),
        UniqueConstraint("preventive_plan_id", "due_date", name="uq_work_orders_plan_occurrence"),
        Index("ix_work_orders_asset", "asset_id"),
        Index("ix_work_orders_plan", "preventive_plan_id"),
        Index("ix_work_orders_ticket", "source_ticket_id"),
        Index("ix_work_orders_assignee", "assigned_to_user_id"),
        Index("ix_work_orders_status", "status"),
        Index("ix_work_orders_due_date", "due_date"),
        Index(
            "uq_work_orders_active_corrective_ticket",
            "source_ticket_id",
            unique=True,
            postgresql_where=text(
                "source_ticket_id IS NOT NULL AND work_order_type = 'corrective' "
                "AND status NOT IN ('verified', 'cancelled')"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    work_order_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="RESTRICT"), nullable=False
    )
    preventive_plan_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source_ticket_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assigned_to_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    verified_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    scheduled_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    local_timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Ho_Chi_Minh",
        server_default=text("'Asia/Ho_Chi_Minh'"),
    )
    grace_period_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    estimated_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    labor_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="planned", server_default=text("'planned'")
    )
    hold_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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

class WorkOrderChecklistItem(Base):
    """Checklist template snapshot and technician response for one work order."""

    __tablename__ = "work_order_checklist_items"
    __table_args__ = (
        CheckConstraint("sequence > 0", name="ck_wo_checklist_sequence"),
        CheckConstraint(
            "response_type IN ('checkbox', 'pass_fail', 'numeric', 'text')",
            name="ck_wo_checklist_response_type",
        ),
        CheckConstraint(
            "result_status IN ('pending', 'completed', 'pass', 'fail', 'not_applicable')",
            name="ck_wo_checklist_result_status",
        ),
        CheckConstraint(
            "minimum_value IS NULL OR maximum_value IS NULL OR minimum_value <= maximum_value",
            name="ck_wo_checklist_numeric_range",
        ),
        CheckConstraint(
            "result_status <> 'not_applicable' OR allow_not_applicable = true",
            name="ck_wo_checklist_not_applicable",
        ),
        CheckConstraint(
            "((result_status = 'pending' AND completed_at IS NULL "
            "AND completed_by_user_id IS NULL) OR "
            "(result_status <> 'pending' AND completed_at IS NOT NULL "
            "AND completed_by_user_id IS NOT NULL))",
            name="ck_wo_checklist_completion_state",
        ),
        UniqueConstraint("work_order_id", "sequence", name="uq_wo_checklist_sequence"),
        Index("ix_wo_checklist_work_order", "work_order_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    work_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="RESTRICT"), nullable=False
    )
    source_template_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("checklist_template_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    response_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    safety_critical: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allow_not_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    minimum_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    maximum_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default=text("'pending'")
    )
    boolean_value: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class WorkOrderAttachment(Base):
    """Safe execution evidence metadata linked to one work order and asset."""

    __tablename__ = "work_order_attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["work_order_id", "asset_id"],
            ["work_orders.id", "work_orders.asset_id"],
            name="fk_wo_attachments_work_order_asset",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "category IN ('before_photo', 'after_photo', 'inspection_document', "
            "'completion_document', 'safety_document', 'other')",
            name="ck_wo_attachments_category",
        ),
        CheckConstraint("size_bytes > 0", name="ck_wo_attachments_size"),
        CheckConstraint("length(checksum) = 64", name="ck_wo_attachments_checksum"),
        UniqueConstraint("storage_key", name="uq_wo_attachments_storage_key"),
        Index("ix_wo_attachments_work_order", "work_order_id"),
        Index("ix_wo_attachments_active", "work_order_id", "deleted_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    work_order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

