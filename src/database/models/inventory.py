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

