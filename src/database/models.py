"""Canonical SQLAlchemy models for transactional maintenance data."""

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

from src.database.session import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _asset_qr_token(context) -> UUID:
    from uuid import NAMESPACE_URL, uuid5

    asset_id = str(context.get_current_parameters().get("asset_id", ""))
    return uuid5(NAMESPACE_URL, f"ai-maintenance-copilot:asset:{asset_id}")


class Location(Base):
    """Hierarchical facility location with archive-in-place semantics."""

    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint(
            "location_type IN ('building', 'floor', 'room', 'area', 'plant')",
            name="ck_locations_type",
        ),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name="ck_locations_not_self_parent"
        ),
        CheckConstraint("code = upper(btrim(code))", name="ck_locations_code_normalized"),
        UniqueConstraint("code", name="uq_locations_code"),
        Index("ix_locations_parent_id", "parent_id"),
        Index("ix_locations_is_active", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location_type: Mapped[str] = mapped_column(String(30), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
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
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class Asset(Base):
    """Facility asset stored with stable internal enum codes."""

    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('hvac', 'pump', 'generator')",
            name="ck_assets_asset_type",
        ),
        CheckConstraint(
            "criticality IN ('low', 'medium', 'high', 'critical')",
            name="ck_assets_criticality",
        ),
        CheckConstraint(
            "operational_status IN ('running', 'warning', 'fault', "
            "'under_maintenance', 'out_of_service')",
            name="ck_assets_operational_status",
        ),
        CheckConstraint(
            "lifecycle_status IN ('planned', 'active', 'inactive', 'retired', 'archived')",
            name="ck_assets_lifecycle_status",
        ),
        CheckConstraint(
            "lifecycle_status_before_archive IS NULL OR "
            "lifecycle_status_before_archive IN ('planned', 'active', 'inactive', 'retired')",
            name="ck_assets_pre_archive_lifecycle_status",
        ),
        CheckConstraint(
            "operational_status_before_archive IS NULL OR "
            "operational_status_before_archive IN ('running', 'warning', 'fault', "
            "'under_maintenance', 'out_of_service')",
            name="ck_assets_pre_archive_operational_status",
        ),
        CheckConstraint(
            "asset_category IN ('climate_control', 'water_system', 'power_system', 'other')",
            name="ck_assets_category",
        ),
        CheckConstraint(
            "ownership_type IN ('owned', 'leased', 'managed')",
            name="ck_assets_ownership_type",
        ),
        CheckConstraint(
            "serial_number IS NULL OR serial_number = upper(btrim(serial_number))",
            name="ck_assets_serial_number_normalized",
        ),
        CheckConstraint(
            "production_year IS NULL OR production_year BETWEEN 1900 AND 2200",
            name="ck_assets_production_year",
        ),
        CheckConstraint(
            "commissioned_at IS NULL OR commissioned_at >= installed_at",
            name="ck_assets_commissioning_chronology",
        ),
        CheckConstraint(
            "retired_at IS NULL OR retired_at >= installed_at",
            name="ck_assets_retirement_chronology",
        ),
        CheckConstraint(
            "warranty_end_date IS NULL OR warranty_start_date IS NULL OR "
            "warranty_end_date >= warranty_start_date",
            name="ck_assets_warranty_chronology",
        ),
        CheckConstraint(
            "((lifecycle_status = 'archived' AND archived_at IS NOT NULL "
            "AND archive_reason IS NOT NULL) OR "
            "(lifecycle_status <> 'archived' AND archived_at IS NULL "
            "AND archive_reason IS NULL))",
            name="ck_assets_archive_state",
        ),
        CheckConstraint(
            "maintenance_interval_days > 0",
            name="ck_assets_maintenance_interval_positive",
        ),
        CheckConstraint(
            "next_maintenance_date >= last_maintenance_date",
            name="ck_assets_maintenance_chronology",
        ),
        Index("ix_assets_asset_type", "asset_type"),
        Index("ix_assets_location", "location"),
        Index("ix_assets_location_id", "location_id"),
        Index("ix_assets_lifecycle_status", "lifecycle_status"),
        Index("ix_assets_operational_status", "operational_status"),
        Index("ix_assets_manufacturer_model", "manufacturer", "model"),
        Index(
            "uq_assets_serial_number",
            "serial_number",
            unique=True,
            postgresql_where=text("serial_number IS NOT NULL"),
        ),
        UniqueConstraint("qr_token", name="uq_assets_qr_token"),
        Index("ix_assets_next_maintenance_date", "next_maintenance_date"),
    )

    asset_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(40), nullable=False)
    asset_category: Mapped[str] = mapped_column(
        String(40), nullable=False, default="other", server_default=text("'other'")
    )
    manufacturer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(150), nullable=True)
    production_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    criticality: Mapped[str] = mapped_column(String(20), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default=text("'active'")
    )
    lifecycle_status_before_archive: Mapped[str | None] = mapped_column(String(20), nullable=True)
    operational_status_before_archive: Mapped[str | None] = mapped_column(String(30), nullable=True)
    operational_status: Mapped[str] = mapped_column(String(30), nullable=False)

    def _get_compatibility_status(self) -> str:
        return self.operational_status

    def _set_compatibility_status(self, value: str) -> None:
        self.operational_status = {
            "normal": "running",
            "warning": "warning",
            "fault": "fault",
        }.get(value, value)

    status = synonym(
        "operational_status",
        descriptor=property(_get_compatibility_status, _set_compatibility_status),
    )
    installation_date: Mapped[date] = mapped_column(Date, nullable=False)
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )
    commissioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ownership_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="owned", server_default=text("'owned'")
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    warranty_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    warranty_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    warranty_provider: Mapped[str | None] = mapped_column(String(200), nullable=True)
    warranty_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_maintenance_date: Mapped[date] = mapped_column(Date, nullable=False)
    maintenance_interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    next_maintenance_date: Mapped[date] = mapped_column(Date, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
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
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    qr_token: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=_asset_qr_token
    )

    __mapper_args__ = {"version_id_col": version}


class AssetAttachment(Base):
    """Metadata for a safely stored asset attachment."""

    __tablename__ = "asset_attachments"
    __table_args__ = (
        CheckConstraint(
            "category IN ('asset_photo', 'technical_manual', 'warranty_document', "
            "'commissioning_record', 'inspection_document', 'other')",
            name="ck_asset_attachments_category",
        ),
        CheckConstraint("size_bytes > 0", name="ck_asset_attachments_size_positive"),
        CheckConstraint("length(checksum) = 64", name="ck_asset_attachments_checksum_length"),
        UniqueConstraint("storage_key", name="uq_asset_attachments_storage_key"),
        Index("ix_asset_attachments_asset_id", "asset_id"),
        Index("ix_asset_attachments_active", "asset_id", "deleted_at"),
        Index("ix_asset_attachments_checksum", "checksum"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="RESTRICT"), nullable=False
    )
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


class PartCategory(Base):
    """Versioned spare-part classification with stable business codes."""

    __tablename__ = "part_categories"
    __table_args__ = (
        CheckConstraint("code = upper(btrim(code))", name="ck_part_categories_code"),
        UniqueConstraint("code", name="uq_part_categories_code"),
        Index("ix_part_categories_active", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name_vi: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class UnitOfMeasure(Base):
    """Controlled unit used by a part, balance, and immutable movement."""

    __tablename__ = "units_of_measure"
    __table_args__ = (
        CheckConstraint("code = upper(btrim(code))", name="ck_units_of_measure_code"),
        CheckConstraint(
            "quantity_precision BETWEEN 0 AND 3",
            name="ck_units_of_measure_precision",
        ),
        UniqueConstraint("code", name="uq_units_of_measure_code"),
        Index("ix_units_of_measure_active", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name_vi: Mapped[str] = mapped_column(String(120), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(120), nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity_precision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
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


class SparePart(Base):
    """Spare-part master data; stock remains in inventory positions."""

    __tablename__ = "spare_parts"
    __table_args__ = (
        CheckConstraint(
            "part_number = upper(btrim(part_number))",
            name="ck_spare_parts_number",
        ),
        CheckConstraint(
            "lifecycle_status IN ('active', 'inactive', 'archived')",
            name="ck_spare_parts_lifecycle",
        ),
        CheckConstraint(
            "lifecycle_status_before_archive IS NULL OR "
            "lifecycle_status_before_archive IN ('active', 'inactive')",
            name="ck_spare_parts_pre_archive",
        ),
        CheckConstraint(
            "jsonb_typeof(compatible_asset_types) = 'array'",
            name="ck_spare_parts_asset_types",
        ),
        CheckConstraint(
            "minimum_stock >= 0 AND reorder_point >= minimum_stock AND "
            "(maximum_stock IS NULL OR maximum_stock >= reorder_point)",
            name="ck_spare_parts_thresholds",
        ),
        CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0",
            name="ck_spare_parts_unit_cost",
        ),
        CheckConstraint(
            "((lifecycle_status = 'archived' AND archived_at IS NOT NULL "
            "AND archive_reason IS NOT NULL) OR "
            "(lifecycle_status <> 'archived' AND archived_at IS NULL "
            "AND archive_reason IS NULL))",
            name="ck_spare_parts_archive_state",
        ),
        UniqueConstraint("part_number", name="uq_spare_parts_number"),
        Index("ix_spare_parts_category", "category_id"),
        Index("ix_spare_parts_uom", "unit_of_measure_id"),
        Index("ix_spare_parts_lifecycle", "lifecycle_status"),
        Index("ix_spare_parts_name_vi", "name_vi"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    part_number: Mapped[str] = mapped_column(String(80), nullable=False)
    name_vi: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("part_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    unit_of_measure_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    manufacturer_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    compatible_asset_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default=text("'active'")
    )
    lifecycle_status_before_archive: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    minimum_stock: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=0, server_default=text("0")
    )
    reorder_point: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=0, server_default=text("0")
    )
    maximum_stock: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
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


class StockLocation(Base):
    """Warehouse or mobile stock point, separate from asset locations."""

    __tablename__ = "stock_locations"
    __table_args__ = (
        CheckConstraint("code = upper(btrim(code))", name="ck_stock_locations_code"),
        CheckConstraint(
            "location_type IN ('main_store', 'engineering_store', 'technician_van', "
            "'maintenance_room', 'quarantine', 'other')",
            name="ck_stock_locations_type",
        ),
        CheckConstraint(
            "lifecycle_status IN ('active', 'inactive', 'archived')",
            name="ck_stock_locations_lifecycle",
        ),
        CheckConstraint(
            "lifecycle_status_before_archive IS NULL OR "
            "lifecycle_status_before_archive IN ('active', 'inactive')",
            name="ck_stock_locations_pre_archive",
        ),
        CheckConstraint(
            "((lifecycle_status = 'archived' AND archived_at IS NOT NULL "
            "AND archive_reason IS NOT NULL) OR "
            "(lifecycle_status <> 'archived' AND archived_at IS NULL "
            "AND archive_reason IS NULL))",
            name="ck_stock_locations_archive_state",
        ),
        UniqueConstraint("code", name="uq_stock_locations_code"),
        Index("ix_stock_locations_lifecycle", "lifecycle_status"),
        Index("ix_stock_locations_type", "location_type"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location_type: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default=text("'active'")
    )
    lifecycle_status_before_archive: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
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


class InventoryPosition(Base):
    """Transactionally maintained on-hand and reserved quantities."""

    __tablename__ = "inventory_positions"
    __table_args__ = (
        CheckConstraint(
            "on_hand_quantity >= 0 AND reserved_quantity >= 0 "
            "AND reserved_quantity <= on_hand_quantity",
            name="ck_inventory_positions_quantities",
        ),
        UniqueConstraint(
            "part_id", "stock_location_id", name="uq_inventory_position_part_location"
        ),
        Index("ix_inventory_positions_part", "part_id"),
        Index("ix_inventory_positions_location", "stock_location_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    part_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False
    )
    stock_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stock_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    on_hand_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=0, server_default=text("0")
    )
    reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=0, server_default=text("0")
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


class PartReorderConfiguration(Base):
    """Location-specific thresholds overriding the spare-part defaults."""

    __tablename__ = "part_reorder_configurations"
    __table_args__ = (
        CheckConstraint(
            "minimum_stock >= 0 AND reorder_point >= minimum_stock AND "
            "(maximum_stock IS NULL OR maximum_stock >= reorder_point)",
            name="ck_part_reorder_thresholds",
        ),
        UniqueConstraint(
            "part_id", "stock_location_id", name="uq_part_reorder_part_location"
        ),
        Index("ix_part_reorder_part", "part_id"),
        Index("ix_part_reorder_location", "stock_location_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    part_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False
    )
    stock_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stock_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    minimum_stock: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    reorder_point: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    maximum_stock: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
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


class InventoryOperation(Base):
    """Globally idempotent named inventory operation."""

    __tablename__ = "inventory_operations"
    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('opening_balance', 'receipt', 'reserve', "
            "'release_reservation', 'expire_reservation', 'replace_reservation', "
            "'issue', 'consume', 'return', 'transfer', 'adjustment_increase', "
            "'adjustment_decrease', 'damaged_scrapped')",
            name="ck_inventory_operations_type",
        ),
        UniqueConstraint("idempotency_key", name="uq_inventory_operations_key"),
        CheckConstraint(
            "length(request_hash) = 64", name="ck_inventory_operations_request_hash"
        ),
        Index("ix_inventory_operations_created_at", "created_at"),
        Index("ix_inventory_operations_actor", "actor_user_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    result_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )


class InventoryMovement(Base):
    """Immutable source event for physical stock quantity changes."""

    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_inventory_movements_quantity"),
        CheckConstraint(
            "movement_type IN ('opening_balance', 'receipt', 'issue', 'return', "
            "'transfer_out', 'transfer_in', 'adjustment_increase', "
            "'adjustment_decrease', 'damaged_scrapped')",
            name="ck_inventory_movements_type",
        ),
        CheckConstraint(
            "resulting_on_hand_quantity >= 0 AND resulting_reserved_quantity >= 0 "
            "AND resulting_reserved_quantity <= resulting_on_hand_quantity",
            name="ck_inventory_movements_result",
        ),
        CheckConstraint(
            "unit_cost_snapshot IS NULL OR unit_cost_snapshot >= 0",
            name="ck_inventory_movements_cost",
        ),
        CheckConstraint(
            "((movement_type IN ('transfer_out', 'transfer_in') "
            "AND transfer_group_id IS NOT NULL "
            "AND source_location_id IS NOT NULL AND destination_location_id IS NOT NULL "
            "AND source_location_id <> destination_location_id) OR "
            "(movement_type NOT IN ('transfer_out', 'transfer_in') "
            "AND transfer_group_id IS NULL))",
            name="ck_inventory_movements_transfer",
        ),
        UniqueConstraint("movement_number", name="uq_inventory_movements_number"),
        UniqueConstraint("operation_id", "movement_type", name="uq_inventory_movement_operation"),
        Index("ix_inventory_movements_part", "part_id", "occurred_at"),
        Index("ix_inventory_movements_location", "stock_location_id", "occurred_at"),
        Index("ix_inventory_movements_work_order", "work_order_id"),
        Index("ix_inventory_movements_transfer", "transfer_group_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    movement_number: Mapped[str] = mapped_column(String(50), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_operations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    part_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False
    )
    stock_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stock_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_of_measure_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    movement_type: Mapped[str] = mapped_column(String(40), nullable=False)
    business_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    work_order_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="RESTRICT"), nullable=True
    )
    source_location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stock_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    destination_location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stock_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    transfer_group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    unit_cost_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    resulting_on_hand_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False
    )
    resulting_reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )


class WorkOrderPartRequirement(Base):
    """Planned part demand, separate from reservation and physical issue."""

    __tablename__ = "work_order_part_requirements"
    __table_args__ = (
        CheckConstraint("planned_quantity > 0", name="ck_wo_part_requirements_quantity"),
        CheckConstraint(
            "status IN ('planned', 'partially_reserved', 'reserved', "
            "'partially_issued', 'issued', 'partially_consumed', 'fulfilled', "
            "'cancelled')",
            name="ck_wo_part_requirements_status",
        ),
        UniqueConstraint(
            "work_order_id",
            "part_id",
            "source_stock_location_id",
            name="uq_wo_part_requirement_line",
        ),
        Index("ix_wo_part_requirements_work_order", "work_order_id"),
        Index("ix_wo_part_requirements_part", "part_id"),
        Index("ix_wo_part_requirements_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    work_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="RESTRICT"), nullable=False
    )
    part_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False
    )
    planned_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    required_by_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_stock_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stock_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="planned", server_default=text("'planned'")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class StockReservation(Base):
    """Concurrency-safe stock allocation for one work-order requirement."""

    __tablename__ = "stock_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_reservations_quantity"),
        CheckConstraint(
            "status IN ('active', 'partially_issued', 'fulfilled', 'released', "
            "'expired', 'replaced')",
            name="ck_stock_reservations_status",
        ),
        CheckConstraint("occurrence_number > 0", name="ck_stock_reservations_occurrence"),
        UniqueConstraint("reservation_number", name="uq_stock_reservations_number"),
        UniqueConstraint(
            "requirement_id",
            "occurrence_number",
            name="uq_stock_reservation_requirement_occurrence",
        ),
        UniqueConstraint("operation_id", name="uq_stock_reservations_operation"),
        Index("ix_stock_reservations_requirement", "requirement_id"),
        Index("ix_stock_reservations_work_order", "work_order_id"),
        Index("ix_stock_reservations_position", "part_id", "stock_location_id"),
        Index(
            "uq_stock_reservation_active_requirement",
            "requirement_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'partially_issued')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    reservation_number: Mapped[str] = mapped_column(String(50), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_operations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requirement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("work_order_part_requirements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    work_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="RESTRICT"), nullable=False
    )
    part_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False
    )
    stock_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stock_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    occurrence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="active", server_default=text("'active'")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_reservation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stock_reservations.id", ondelete="RESTRICT"),
        nullable=True,
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
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class StockReservationEvent(Base):
    """Append-only reservation history; it never changes on-hand stock."""

    __tablename__ = "stock_reservation_events"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_reservation_events_quantity"),
        CheckConstraint(
            "event_type IN ('reserved', 'released', 'expired', 'replaced', "
            "'issued', 'fulfilled')",
            name="ck_stock_reservation_events_type",
        ),
        UniqueConstraint("operation_id", "event_type", name="uq_reservation_event_operation"),
        Index("ix_stock_reservation_events_reservation", "reservation_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    reservation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stock_reservations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_operations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkOrderPartIssue(Base):
    """Immutable issue record; physical stock leaves a location here."""

    __tablename__ = "work_order_part_issues"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0 AND reserved_quantity_used >= 0 "
            "AND reserved_quantity_used <= quantity",
            name="ck_wo_part_issues_quantity",
        ),
        UniqueConstraint("issue_number", name="uq_wo_part_issues_number"),
        UniqueConstraint("operation_id", name="uq_wo_part_issues_operation"),
        UniqueConstraint("movement_id", name="uq_wo_part_issues_movement"),
        Index("ix_wo_part_issues_work_order", "work_order_id", "issued_at"),
        Index("ix_wo_part_issues_requirement", "requirement_id"),
        Index("ix_wo_part_issues_reservation", "reservation_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    issue_number: Mapped[str] = mapped_column(String(50), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_operations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    work_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="RESTRICT"), nullable=False
    )
    requirement_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("work_order_part_requirements.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reservation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stock_reservations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    part_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False
    )
    stock_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stock_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    reserved_quantity_used: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=0, server_default=text("0")
    )
    issued_to_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    issued_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    movement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_movements.id", ondelete="RESTRICT"),
        nullable=False,
    )


class WorkOrderPartConsumption(Base):
    """Explicit immutable usage event, separate from issue and completion."""

    __tablename__ = "work_order_part_consumptions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_wo_part_consumptions_quantity"),
        UniqueConstraint("operation_id", name="uq_wo_part_consumptions_operation"),
        Index("ix_wo_part_consumptions_issue", "issue_id", "consumed_at"),
        Index("ix_wo_part_consumptions_work_order", "work_order_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_operations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issue_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("work_order_part_issues.id", ondelete="RESTRICT"),
        nullable=False,
    )
    work_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="RESTRICT"), nullable=False
    )
    part_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    consumed_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkOrderPartReturn(Base):
    """Immutable return of unused issued stock to a valid location."""

    __tablename__ = "work_order_part_returns"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_wo_part_returns_quantity"),
        UniqueConstraint("return_number", name="uq_wo_part_returns_number"),
        UniqueConstraint("operation_id", name="uq_wo_part_returns_operation"),
        UniqueConstraint("movement_id", name="uq_wo_part_returns_movement"),
        Index("ix_wo_part_returns_issue", "issue_id", "returned_at"),
        Index("ix_wo_part_returns_work_order", "work_order_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    return_number: Mapped[str] = mapped_column(String(50), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_operations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issue_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("work_order_part_issues.id", ondelete="RESTRICT"),
        nullable=False,
    )
    work_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="RESTRICT"), nullable=False
    )
    part_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False
    )
    stock_location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stock_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    returned_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    returned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    movement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_movements.id", ondelete="RESTRICT"),
        nullable=False,
    )


class InventoryAttachment(Base):
    """Protected evidence metadata attached to an immutable movement."""

    __tablename__ = "inventory_attachments"
    __table_args__ = (
        CheckConstraint(
            "category IN ('adjustment_evidence', 'damage_evidence', "
            "'receipt_evidence', 'transfer_evidence', 'other')",
            name="ck_inventory_attachments_category",
        ),
        CheckConstraint("size_bytes > 0", name="ck_inventory_attachments_size"),
        CheckConstraint("length(checksum) = 64", name="ck_inventory_attachments_checksum"),
        UniqueConstraint("storage_key", name="uq_inventory_attachments_storage_key"),
        Index("ix_inventory_attachments_movement", "movement_id"),
        Index("ix_inventory_attachments_active", "movement_id", "deleted_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    movement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_movements.id", ondelete="RESTRICT"),
        nullable=False,
    )
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


class User(Base):
    """Local internal-pilot identity with a normalized login identifier."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("username = lower(btrim(username))", name="ck_users_username_normalized"),
        CheckConstraint(
            "email IS NULL OR email = lower(btrim(email))",
            name="ck_users_email_normalized",
        ),
        CheckConstraint(
            "role IN ('administrator', 'property_manager', 'chief_engineer', "
            "'technician', 'helpdesk', 'storekeeper')",
            name="ck_users_role",
        ),
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("technician_id", name="uq_users_technician_id"),
        Index("ix_users_role", "role"),
        Index("ix_users_is_active", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    technician_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class RefreshSession(Base):
    """Revocable refresh session; only hashes are persisted."""

    __tablename__ = "refresh_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_sessions_token_hash"),
        Index("ix_refresh_sessions_user_id", "user_id"),
        Index("ix_refresh_sessions_expires_at", "expires_at"),
        Index("ix_refresh_sessions_active", "user_id", "revoked_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)


class AuditLog(Base):
    """Append-only security and maintenance workflow event."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_occurred_at", "occurred_at"),
        Index("ix_audit_logs_actor_user_id", "actor_user_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_request_id", "request_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    actor_display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    before_state: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    event_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)


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


class ReliabilityValidationRecord(Base):
    """Append-only evidence marker produced by a completed PM8 validation drill."""

    __tablename__ = "reliability_validation_records"
    __table_args__ = (
        CheckConstraint(
            "validation_type IN ('backup_restore')",
            name="ck_reliability_validation_records_type",
        ),
        CheckConstraint(
            "status IN ('passed', 'failed')",
            name="ck_reliability_validation_records_status",
        ),
        CheckConstraint(
            "jsonb_typeof(summary) = 'object' AND octet_length(summary::text) <= 4096",
            name="ck_reliability_validation_records_summary",
        ),
        CheckConstraint(
            "backup_checksum IS NULL OR "
            "backup_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_reliability_validation_records_checksum",
        ),
        Index(
            "ix_reliability_validation_records_latest",
            "validation_type",
            "status",
            "performed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    validation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, server_default=func.now()
    )
    source_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    backup_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    recorded_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


# Compatibility import for the former experimental class name.
MaintenanceTicket = Ticket
