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

class TicketCategory(Base):
    """Stable service category used for intake and SLA selection."""

    __tablename__ = "ticket_categories"
    __table_args__ = (
        CheckConstraint("code = lower(btrim(code))", name="ck_ticket_categories_code"),
        UniqueConstraint("code", name="uq_ticket_categories_code"),
        Index("ix_ticket_categories_active", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
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

class TicketSubcategory(Base):
    """Category-owned intake subcategory."""

    __tablename__ = "ticket_subcategories"
    __table_args__ = (
        CheckConstraint("code = lower(btrim(code))", name="ck_ticket_subcategories_code"),
        UniqueConstraint("category_id", "code", name="uq_ticket_subcategories_code"),
        UniqueConstraint("id", "category_id", name="uq_ticket_subcategories_id_category"),
        Index("ix_ticket_subcategories_category", "category_id"),
        Index("ix_ticket_subcategories_active", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    category_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ticket_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
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

class TicketIntakeSource(Base):
    """Controlled intake channel such as web, phone, or email."""

    __tablename__ = "ticket_intake_sources"
    __table_args__ = (
        CheckConstraint("code = lower(btrim(code))", name="ck_ticket_sources_code"),
        UniqueConstraint("code", name="uq_ticket_sources_code"),
        Index("ix_ticket_sources_active", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
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

class SupportGroup(Base):
    """Assignment queue for one operational support team."""

    __tablename__ = "support_groups"
    __table_args__ = (
        CheckConstraint("code = upper(btrim(code))", name="ck_support_groups_code"),
        UniqueConstraint("code", name="uq_support_groups_code"),
        Index("ix_support_groups_active", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
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

class BusinessCalendar(Base):
    """Versioned business-hours aggregate used to snapshot SLA targets."""

    __tablename__ = "business_calendars"
    __table_args__ = (
        CheckConstraint("code = upper(btrim(code))", name="ck_business_calendars_code"),
        UniqueConstraint("code", name="uq_business_calendars_code"),
        Index("ix_business_calendars_active", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
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

class BusinessWorkingPeriod(Base):
    """One non-overlapping same-day period in a business calendar."""

    __tablename__ = "business_working_periods"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_working_periods_weekday"),
        CheckConstraint("start_time < end_time", name="ck_working_periods_chronology"),
        UniqueConstraint("calendar_id", "weekday", "start_time", name="uq_working_period_start"),
        Index("ix_working_periods_calendar", "calendar_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    calendar_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_calendars.id", ondelete="CASCADE"),
        nullable=False,
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

class BusinessCalendarHoliday(Base):
    """Closed local business date captured by one calendar."""

    __tablename__ = "business_calendar_holidays"
    __table_args__ = (
        UniqueConstraint("calendar_id", "holiday_date", name="uq_calendar_holiday"),
        Index("ix_calendar_holidays_calendar", "calendar_id"),
        Index("ix_calendar_holidays_date", "holiday_date"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    calendar_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_calendars.id", ondelete="CASCADE"),
        nullable=False,
    )
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)

class SlaPolicy(Base):
    """Effective-dated SLA policy; ticket clocks keep immutable snapshots."""

    __tablename__ = "sla_policies"
    __table_args__ = (
        CheckConstraint("code = upper(btrim(code))", name="ck_sla_policies_code"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_sla_policies_effective_range",
        ),
        CheckConstraint("due_soon_percent BETWEEN 1 AND 100", name="ck_sla_due_soon_percent"),
        UniqueConstraint("code", name="uq_sla_policies_code"),
        Index("ix_sla_policies_active", "is_active"),
        Index("ix_sla_policies_effective", "effective_from", "effective_to"),
        Index("ix_sla_policies_category", "category_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    calendar_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_calendars.id", ondelete="RESTRICT"),
        nullable=False,
    )
    category_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ticket_categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    pause_on_waiting: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    due_soon_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20, server_default=text("20")
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
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

class SlaPolicyTarget(Base):
    """Priority-specific first-response and resolution targets."""

    __tablename__ = "sla_policy_targets"
    __table_args__ = (
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name="ck_sla_targets_priority",
        ),
        CheckConstraint(
            "first_response_minutes > 0 AND resolution_minutes > 0",
            name="ck_sla_targets_minutes",
        ),
        UniqueConstraint("policy_id", "priority", name="uq_sla_policy_priority"),
        Index("ix_sla_targets_policy", "policy_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    policy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sla_policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    first_response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

class Ticket(Base):
    """Service request with an explicit lifecycle, assignment, and SLA context."""

    __tablename__ = "maintenance_tickets"
    __table_args__ = (
        UniqueConstraint("ticket_id", "asset_id", name="uq_tickets_ticket_asset"),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name="ck_tickets_priority",
        ),
        CheckConstraint(
            "status IN ('open', 'assigned', 'in_progress', 'waiting', 'resolved', "
            "'closed', 'cancelled', 'reopened')",
            name="ck_tickets_status",
        ),
        CheckConstraint(
            "impact IN ('low', 'medium', 'high', 'critical')",
            name="ck_tickets_impact",
        ),
        CheckConstraint(
            "urgency IN ('low', 'medium', 'high', 'immediate')",
            name="ck_tickets_urgency",
        ),
        CheckConstraint(
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
            name="ck_tickets_priority_matrix",
        ),
        CheckConstraint(
            "failure_category IN ('cooling_issue', 'vibration_issue', "
            "'electrical_issue', 'pressure_issue', 'runtime_issue', "
            "'sensor_issue', 'false_alarm', 'no_failure')",
            name="ck_tickets_failure_category",
        ),
        CheckConstraint(
            "((status IN ('resolved', 'closed') AND resolved_at IS NOT NULL) OR "
            "(status NOT IN ('resolved', 'closed') AND resolved_at IS NULL))",
            name="ck_tickets_resolution_state",
        ),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= created_at",
            name="ck_tickets_resolution_chronology",
        ),
        CheckConstraint(
            "((status = 'closed' AND closed_at IS NOT NULL) OR "
            "(status <> 'closed' AND closed_at IS NULL))",
            name="ck_tickets_closed_state",
        ),
        CheckConstraint(
            "closed_at IS NULL OR (resolved_at IS NOT NULL AND closed_at >= resolved_at)",
            name="ck_tickets_closed_chronology",
        ),
        CheckConstraint(
            "((status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND cancellation_reason IS NOT NULL) OR "
            "(status <> 'cancelled' AND cancelled_at IS NULL "
            "AND cancellation_reason IS NULL))",
            name="ck_tickets_cancelled_state",
        ),
        CheckConstraint(
            "((status = 'waiting' AND waiting_reason IS NOT NULL "
            "AND waiting_previous_status IN ('assigned', 'in_progress')) OR "
            "(status <> 'waiting' AND waiting_reason IS NULL "
            "AND waiting_previous_status IS NULL))",
            name="ck_tickets_waiting_state",
        ),
        CheckConstraint("reopen_count >= 0", name="ck_tickets_reopen_count"),
        CheckConstraint(
            "first_response_at IS NULL OR first_response_at >= created_at",
            name="ck_tickets_first_response_chronology",
        ),
        CheckConstraint(
            "subcategory_id IS NULL OR category_id IS NOT NULL",
            name="ck_tickets_subcategory_requires_category",
        ),
        ForeignKeyConstraint(
            ["subcategory_id", "category_id"],
            ["ticket_subcategories.id", "ticket_subcategories.category_id"],
            name="fk_tickets_subcategory_category",
            ondelete="RESTRICT",
        ),
        Index("ix_tickets_asset_id", "asset_id"),
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_created_at", "created_at"),
        Index("ix_tickets_priority", "priority"),
        Index("ix_tickets_support_group", "support_group_id"),
        Index("ix_tickets_assigned_user", "assigned_user_id"),
        Index("ix_tickets_category", "category_id"),
    )

    ticket_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="RESTRICT"),
        nullable=False,
    )
    issue_description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    failure_category: Mapped[str] = mapped_column(String(40), nullable=False)
    reporter_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reporter_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    reporter_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    category_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ticket_categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    subcategory_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    impact: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium", server_default=text("'medium'")
    )
    urgency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium", server_default=text("'medium'")
    )
    intake_source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ticket_intake_sources.id", ondelete="RESTRICT"),
        nullable=True,
    )
    support_group_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("support_groups.id", ondelete="RESTRICT"),
        nullable=True,
    )
    assigned_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    first_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    waiting_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    waiting_previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reopen_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    technician_id: Mapped[str] = mapped_column(String(50), nullable=False)
    manager_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
    )

    __mapper_args__ = {"version_id_col": version}

class TicketSlaState(Base):
    """Policy and calendar snapshot for the current ticket SLA occurrence."""

    __tablename__ = "ticket_sla_states"
    __table_args__ = (
        CheckConstraint(
            "first_response_target_minutes > 0 AND resolution_target_minutes > 0",
            name="ck_ticket_sla_target_minutes",
        ),
        CheckConstraint(
            "due_soon_percent BETWEEN 1 AND 100",
            name="ck_ticket_sla_due_soon_percent",
        ),
        CheckConstraint("occurrence_number > 0", name="ck_ticket_sla_occurrence"),
        CheckConstraint(
            "first_response_due_at >= started_at AND resolution_due_at >= started_at",
            name="ck_ticket_sla_due_chronology",
        ),
        CheckConstraint(
            "first_response_remaining_minutes IS NULL OR first_response_remaining_minutes >= 0",
            name="ck_ticket_sla_response_remaining",
        ),
        CheckConstraint(
            "resolution_remaining_minutes IS NULL OR resolution_remaining_minutes >= 0",
            name="ck_ticket_sla_resolution_remaining",
        ),
        UniqueConstraint("ticket_id", name="uq_ticket_sla_ticket"),
        Index("ix_ticket_sla_policy", "policy_id"),
        Index("ix_ticket_sla_response_due", "first_response_due_at"),
        Index("ix_ticket_sla_resolution_due", "resolution_due_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("maintenance_tickets.ticket_id", ondelete="CASCADE"),
        nullable=False,
    )
    policy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sla_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_code: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_name: Mapped[str] = mapped_column(String(200), nullable=False)
    calendar_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_calendars.id", ondelete="RESTRICT"),
        nullable=False,
    )
    calendar_code: Mapped[str] = mapped_column(String(50), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    calendar_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    pause_on_waiting: Mapped[bool] = mapped_column(Boolean, nullable=False)
    due_soon_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    first_response_target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_response_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolution_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_response_remaining_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_remaining_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    occurrence_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
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

class TicketSlaEvent(Base):
    """Immutable source event for SLA clock reconstruction and audit."""

    __tablename__ = "ticket_sla_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('policy_applied', 'clock_started', 'paused', 'resumed', "
            "'first_response_recorded', 'target_met', 'breach_detected', "
            "'resolved', 'reopened', 'stopped')",
            name="ck_ticket_sla_events_type",
        ),
        CheckConstraint(
            "clock_type IS NULL OR clock_type IN ('first_response', 'resolution')",
            name="ck_ticket_sla_events_clock",
        ),
        CheckConstraint("occurrence_number > 0", name="ck_ticket_sla_events_occurrence"),
        Index("ix_ticket_sla_events_ticket", "ticket_id", "occurred_at"),
        Index("ix_ticket_sla_events_state", "ticket_sla_id"),
        Index("ix_ticket_sla_events_type", "event_type"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket_sla_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ticket_sla_states.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticket_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("maintenance_tickets.ticket_id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    clock_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    occurrence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )

class TicketComment(Base):
    """Append-only internal or requester-visible communication entry."""

    __tablename__ = "ticket_comments"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('internal', 'requester')",
            name="ck_ticket_comments_visibility",
        ),
        Index("ix_ticket_comments_ticket", "ticket_id", "created_at"),
        Index("ix_ticket_comments_author", "author_user_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("maintenance_tickets.ticket_id", ondelete="CASCADE"),
        nullable=False,
    )
    author_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    visibility: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )

class TicketCommentAttachment(Base):
    """Reference to an existing authorized asset or work-order attachment."""

    __tablename__ = "ticket_comment_attachments"
    __table_args__ = (
        CheckConstraint(
            "((asset_attachment_id IS NOT NULL AND work_order_attachment_id IS NULL) OR "
            "(asset_attachment_id IS NULL AND work_order_attachment_id IS NOT NULL))",
            name="ck_ticket_comment_attachment_source",
        ),
        UniqueConstraint(
            "comment_id", "asset_attachment_id", name="uq_ticket_comment_asset_attachment"
        ),
        UniqueConstraint(
            "comment_id",
            "work_order_attachment_id",
            name="uq_ticket_comment_work_order_attachment",
        ),
        Index("ix_ticket_comment_attachments_comment", "comment_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    comment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ticket_comments.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_attachment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("asset_attachments.id", ondelete="RESTRICT"),
        nullable=True,
    )
    work_order_attachment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("work_order_attachments.id", ondelete="RESTRICT"),
        nullable=True,
    )

class TicketEscalationEvent(Base):
    """Idempotent immutable escalation evaluation result."""

    __tablename__ = "ticket_escalation_events"
    __table_args__ = (
        CheckConstraint(
            "rule_code IN ('first_response_due_soon', 'first_response_breached', "
            "'resolution_due_soon', 'resolution_breached', 'repeated_reopen', "
            "'critical_priority')",
            name="ck_ticket_escalations_rule",
        ),
        CheckConstraint(
            "clock_type IS NULL OR clock_type IN ('first_response', 'resolution')",
            name="ck_ticket_escalations_clock",
        ),
        CheckConstraint("occurrence_number > 0", name="ck_ticket_escalations_occurrence"),
        UniqueConstraint(
            "ticket_id",
            "rule_code",
            "occurrence_number",
            name="uq_ticket_escalation_rule_occurrence",
        ),
        Index("ix_ticket_escalations_ticket", "ticket_id", "detected_at"),
        Index("ix_ticket_escalations_rule", "rule_code"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("maintenance_tickets.ticket_id", ondelete="CASCADE"),
        nullable=False,
    )
    ticket_sla_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ticket_sla_states.id", ondelete="CASCADE"),
        nullable=True,
    )
    rule_code: Mapped[str] = mapped_column(String(50), nullable=False)
    clock_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    occurrence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )

