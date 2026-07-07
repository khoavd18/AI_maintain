"""SQLAlchemy models for facility maintenance intelligence data."""

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.value_mappings import ANOMALY_TYPE_CODE_TO_VI, STATUS_CODE_TO_VI
from src.database.session import Base


class Asset(Base):
    """Physical facility asset monitored by the maintenance copilot."""

    __tablename__ = "assets"

    asset_id: Mapped[str] = mapped_column(String(40), primary_key=True, index=True)
    asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    criticality: Mapped[str] = mapped_column(String(40), nullable=False)
    installation_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_maintenance_date: Mapped[date] = mapped_column(Date, nullable=False)
    maintenance_frequency_days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default=STATUS_CODE_TO_VI["normal"])

    sensor_readings: Mapped[list["SensorReading"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    maintenance_tickets: Mapped[list["MaintenanceTicket"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    maintenance_logs: Mapped[list["MaintenanceLog"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    risk_scores: Mapped[list["RiskScore"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )


class SensorReading(Base):
    """Hourly or daily sensor and energy reading for a facility asset."""

    __tablename__ = "sensor_readings"

    reading_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id"), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    energy_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    vibration: Mapped[float] = mapped_column(Float, nullable=False)
    runtime_hours: Mapped[float] = mapped_column(Float, nullable=False)
    pressure: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default=STATUS_CODE_TO_VI["normal"])
    anomaly_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default=ANOMALY_TYPE_CODE_TO_VI["none"]
    )

    asset: Mapped[Asset] = relationship(back_populates="sensor_readings")


class MaintenanceTicket(Base):
    """Maintenance ticket imported from a CMMS or service desk."""

    __tablename__ = "maintenance_tickets"

    ticket_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id"), index=True, nullable=False)
    issue_description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    technician_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_type: Mapped[str] = mapped_column(String(100), nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="maintenance_tickets")


class MaintenanceLog(Base):
    """Historical maintenance action performed on an asset."""

    __tablename__ = "maintenance_logs"

    log_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id"), index=True, nullable=False)
    maintenance_date: Mapped[date] = mapped_column(Date, nullable=False)
    maintenance_type: Mapped[str] = mapped_column(String(80), nullable=False)
    technician_name: Mapped[str] = mapped_column(String(120), nullable=False)
    actions_taken: Mapped[str] = mapped_column(Text, nullable=False)
    parts_replaced: Mapped[str] = mapped_column(Text, nullable=False, default="")
    next_maintenance_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    asset: Mapped[Asset] = relationship(back_populates="maintenance_logs")


class RiskScore(Base):
    """Explainable risk score snapshot for an asset."""

    __tablename__ = "risk_scores"

    risk_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id"), index=True, nullable=False)
    score_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    failure_probability: Mapped[float] = mapped_column(Float, nullable=False)
    maintenance_overdue_score: Mapped[float] = mapped_column(Float, nullable=False)
    ticket_score: Mapped[float] = mapped_column(Float, nullable=False)
    criticality_score: Mapped[float] = mapped_column(Float, nullable=False)
    runtime_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False)
    main_reasons: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="risk_scores")


class Document(Base):
    """SOP, checklist, or maintenance reference document for RAG ingestion."""

    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(80), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(250), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    clean_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
