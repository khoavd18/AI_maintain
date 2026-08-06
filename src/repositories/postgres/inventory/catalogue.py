"""Inventory catalogue and stock-location PostgreSQL operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.database.models import (
    InventoryPosition,
    PartCategory,
    PartReorderConfiguration,
    SparePart,
    StockLocation,
    UnitOfMeasure,
)
from src.inventory_management.domain import StockLocationStatus
from src.repositories.contracts import (
    IntegrityViolationError,
    RecordNotFoundError,
    StaleRecordError,
    StorageUnavailableError,
    StoredRecord,
)
from src.security.audit import AuditContext


class InventoryCatalogueRepository:
    """Own transactional master-data and reorder-configuration operations."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        category_record: Callable[..., StoredRecord],
        unit_record: Callable[..., StoredRecord],
        part_record: Callable[..., StoredRecord],
        stock_location_record: Callable[..., StoredRecord],
        reorder_record: Callable[..., StoredRecord],
        require_active_reference: Callable[..., Any],
        require_part: Callable[..., SparePart],
        require_stock_location: Callable[..., StockLocation],
        ensure_position: Callable[..., InventoryPosition],
        audit: Callable[..., None],
        require_version: Callable[..., None],
        raise_integrity: Callable[..., None],
        decimal_value: Callable[..., Any],
        part_audit_fields: set[str],
        location_audit_fields: set[str],
    ) -> None:
        self.session_factory = session_factory
        self._category_record = category_record
        self._unit_record = unit_record
        self._part_record = part_record
        self._stock_location_record = stock_location_record
        self._reorder_record = reorder_record
        self._require_active_reference = require_active_reference
        self._require_part = require_part
        self._require_stock_location = require_stock_location
        self._ensure_position = ensure_position
        self._audit = audit
        self._require_version = require_version
        self._raise_integrity = raise_integrity
        self._decimal = decimal_value
        self._part_audit_fields = part_audit_fields
        self._location_audit_fields = location_audit_fields

    def create_category(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = PartCategory(id=uuid4(), **values)
                session.add(entity)
                session.flush()
                result = self._category_record(entity)
                self._audit(
                    session,
                    audit_context,
                    action="inventory.part_category_created",
                    resource_type="part_category",
                    resource_id=str(entity.id),
                    after=result.values,
                    fields={"id", "code", "is_active", "version"},
                )
            return result
        except IntegrityError as exc:
            self._raise_integrity(exc, duplicate_message="Mã danh mục vật tư đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo danh mục vật tư.") from exc

    def create_unit(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = UnitOfMeasure(id=uuid4(), **values)
                session.add(entity)
                session.flush()
                result = self._unit_record(entity)
                self._audit(
                    session,
                    audit_context,
                    action="inventory.unit_created",
                    resource_type="unit_of_measure",
                    resource_id=str(entity.id),
                    after=result.values,
                    fields={"id", "code", "symbol", "quantity_precision", "version"},
                )
            return result
        except IntegrityError as exc:
            self._raise_integrity(exc, duplicate_message="Mã đơn vị tính đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo đơn vị tính.") from exc

    def create_part(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                self._require_active_reference(
                    session, PartCategory, values["category_id"], "danh mục vật tư"
                )
                self._require_active_reference(
                    session, UnitOfMeasure, values["unit_of_measure_id"], "đơn vị tính"
                )
                entity = SparePart(id=uuid4(), **values)
                session.add(entity)
                session.flush()
                result = self._part_record(session, entity)
                self._audit(
                    session,
                    audit_context,
                    action="inventory.part_created",
                    resource_type="spare_part",
                    resource_id=str(entity.id),
                    after=result.values,
                    fields=self._part_audit_fields,
                )
            return result
        except IntegrityError as exc:
            self._raise_integrity(exc, duplicate_message="Part number đã tồn tại.")
        except (RecordNotFoundError, IntegrityViolationError):
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo spare part.") from exc

    def update_part(
        self,
        part_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = session.scalar(
                    select(SparePart).where(SparePart.id == part_id).with_for_update()
                )
                if entity is None:
                    raise RecordNotFoundError(f"Không tìm thấy spare part: {part_id}")
                self._require_version(entity.version, expected_version, entity.part_number)
                if updates.get("category_id"):
                    self._require_active_reference(
                        session, PartCategory, updates["category_id"], "danh mục vật tư"
                    )
                before = self._part_record(session, entity)
                for key, value in updates.items():
                    setattr(entity, key, value)
                entity.updated_by_user_id = audit_context.actor_user_id
                session.flush()
                result = self._part_record(session, entity)
                self._audit(
                    session,
                    audit_context,
                    action=audit_action,
                    resource_type="spare_part",
                    resource_id=str(entity.id),
                    before=before.values,
                    after=result.values,
                    fields=self._part_audit_fields,
                )
            return result
        except (RecordNotFoundError, StaleRecordError):
            raise
        except StaleDataError as exc:
            raise StaleRecordError(
                "Spare part đã được cập nhật bởi người dùng khác."
            ) from exc
        except IntegrityError as exc:
            self._raise_integrity(exc, duplicate_message="Dữ liệu spare part đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể cập nhật spare part.") from exc

    def create_stock_location(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = StockLocation(id=uuid4(), **values)
                session.add(entity)
                session.flush()
                result = self._stock_location_record(entity)
                self._audit(
                    session,
                    audit_context,
                    action="inventory.stock_location_created",
                    resource_type="stock_location",
                    resource_id=str(entity.id),
                    after=result.values,
                    fields=self._location_audit_fields,
                )
            return result
        except IntegrityError as exc:
            self._raise_integrity(exc, duplicate_message="Mã stock location đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo stock location.") from exc

    def update_stock_location(
        self,
        location_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = session.scalar(
                    select(StockLocation)
                    .where(StockLocation.id == location_id)
                    .with_for_update()
                )
                if entity is None:
                    raise RecordNotFoundError(
                        f"Không tìm thấy stock location: {location_id}"
                    )
                self._require_version(entity.version, expected_version, entity.code)
                target_status = updates.get("lifecycle_status")
                if target_status in {
                    StockLocationStatus.INACTIVE,
                    StockLocationStatus.ARCHIVED,
                }:
                    quantities = session.execute(
                        select(
                            func.coalesce(func.sum(InventoryPosition.on_hand_quantity), 0),
                            func.coalesce(func.sum(InventoryPosition.reserved_quantity), 0),
                        ).where(InventoryPosition.stock_location_id == location_id)
                    ).one()
                    if self._decimal(quantities[0]) > 0 or self._decimal(quantities[1]) > 0:
                        raise IntegrityViolationError(
                            "Chỉ có thể ngừng hoặc archive stock location khi tồn kho bằng 0."
                        )
                before = self._stock_location_record(entity)
                for key, value in updates.items():
                    setattr(entity, key, value)
                entity.updated_by_user_id = audit_context.actor_user_id
                session.flush()
                result = self._stock_location_record(entity)
                self._audit(
                    session,
                    audit_context,
                    action=audit_action,
                    resource_type="stock_location",
                    resource_id=str(entity.id),
                    before=before.values,
                    after=result.values,
                    fields=self._location_audit_fields,
                )
            return result
        except (RecordNotFoundError, StaleRecordError, IntegrityViolationError):
            raise
        except StaleDataError as exc:
            raise StaleRecordError(
                "Stock location đã được cập nhật bởi người dùng khác."
            ) from exc
        except IntegrityError as exc:
            self._raise_integrity(
                exc, duplicate_message="Dữ liệu stock location đã tồn tại."
            )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể cập nhật stock location.") from exc

    def upsert_reorder_configuration(
        self,
        values: dict[str, Any],
        *,
        expected_version: int | None,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                part = self._require_part(session, values["part_id"])
                location = self._require_stock_location(session, values["stock_location_id"])
                entity = session.scalar(
                    select(PartReorderConfiguration)
                    .where(
                        PartReorderConfiguration.part_id == part.id,
                        PartReorderConfiguration.stock_location_id == location.id,
                    )
                    .with_for_update()
                )
                before: StoredRecord | None = None
                if entity is None:
                    if expected_version is not None:
                        raise StaleRecordError(
                            "Reorder configuration chưa tồn tại; hãy tải lại dữ liệu."
                        )
                    entity = PartReorderConfiguration(
                        id=uuid4(),
                        created_by_user_id=audit_context.actor_user_id,
                        updated_by_user_id=audit_context.actor_user_id,
                        **values,
                    )
                    session.add(entity)
                    action = "inventory.reorder_configuration_created"
                else:
                    if expected_version is None:
                        raise StaleRecordError(
                            "expected_version là bắt buộc khi cập nhật reorder configuration."
                        )
                    self._require_version(
                        entity.version,
                        expected_version,
                        f"{part.part_number}/{location.code}",
                    )
                    before = self._reorder_record(session, entity)
                    for key in ("minimum_stock", "reorder_point", "maximum_stock"):
                        setattr(entity, key, values[key])
                    entity.updated_by_user_id = audit_context.actor_user_id
                    action = "inventory.reorder_configuration_updated"
                self._ensure_position(session, part.id, location.id)
                session.flush()
                result = self._reorder_record(session, entity)
                self._audit(
                    session,
                    audit_context,
                    action=action,
                    resource_type="reorder_configuration",
                    resource_id=str(entity.id),
                    before=before.values if before else None,
                    after=result.values,
                    fields={
                        "id",
                        "part_id",
                        "stock_location_id",
                        "minimum_stock",
                        "reorder_point",
                        "maximum_stock",
                        "version",
                    },
                )
            return result
        except (RecordNotFoundError, StaleRecordError, IntegrityViolationError):
            raise
        except StaleDataError as exc:
            raise StaleRecordError(
                "Reorder configuration đã được cập nhật bởi người dùng khác."
            ) from exc
        except IntegrityError as exc:
            self._raise_integrity(
                exc,
                duplicate_message="Reorder configuration cho part/location đã tồn tại.",
            )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể cập nhật reorder configuration."
            ) from exc
