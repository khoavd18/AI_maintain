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

