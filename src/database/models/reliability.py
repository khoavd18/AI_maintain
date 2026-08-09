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

