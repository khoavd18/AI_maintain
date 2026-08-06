"""Read-only PostgreSQL inventory queries."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import (
    InventoryAttachment,
    InventoryMovement,
    InventoryPosition,
    PartCategory,
    SparePart,
    StockLocation,
    StockReservation,
    UnitOfMeasure,
    WorkOrder,
    WorkOrderPartIssue,
    WorkOrderPartRequirement,
)
from src.inventory_management.domain import (
    PartLifecycleStatus,
    RequirementStatus,
    ReservationStatus,
    StockLocationStatus,
)
from src.maintenance_management.domain import WORK_ORDER_STATUS_LABELS, WorkOrderStatus
from src.repositories.contracts import RecordNotFoundError, StorageUnavailableError, StoredPage, StoredRecord

ZERO = Decimal("0")


class InventoryQueryRepository:
    """Own inventory catalogue, balance, movement, and work-order reads."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        category_record: Callable[..., StoredRecord],
        unit_record: Callable[..., StoredRecord],
        part_record: Callable[..., StoredRecord],
        stock_location_record: Callable[..., StoredRecord],
        balance_record: Callable[..., StoredRecord],
        movement_record: Callable[..., StoredRecord],
        requirement_record: Callable[..., StoredRecord],
        reservation_record: Callable[..., StoredRecord],
        issue_record: Callable[..., StoredRecord],
        work_order_state_record: Callable[..., StoredRecord],
        inventory_attachment_record: Callable[..., StoredRecord],
        part_sort_key: Callable[..., Any],
        balance_sort_key: Callable[..., Any],
        require_work_order: Callable[..., WorkOrder],
        decimal_value: Callable[[Any], Decimal],
        uuid_text: Callable[[UUID | None], str | None],
    ) -> None:
        self.session_factory = session_factory
        self._category_record = category_record
        self._unit_record = unit_record
        self._part_record = part_record
        self._stock_location_record = stock_location_record
        self._balance_record = balance_record
        self._movement_record = movement_record
        self._requirement_record = requirement_record
        self._reservation_record = reservation_record
        self._issue_record = issue_record
        self._work_order_state_record = work_order_state_record
        self._inventory_attachment_record = inventory_attachment_record
        self._part_sort_key = part_sort_key
        self._balance_sort_key = balance_sort_key
        self._require_work_order = require_work_order
        self._decimal = decimal_value
        self._uuid_text = uuid_text

    def list_categories(self, *, include_inactive: bool) -> list[StoredRecord]:
        try:
            with self.session_factory() as session:
                statement = select(PartCategory)
                if not include_inactive:
                    statement = statement.where(PartCategory.is_active.is_(True))
                entities = session.scalars(statement.order_by(PartCategory.code)).all()
                return [self._category_record(entity) for entity in entities]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc danh mục vật tư.") from exc

    def list_units(self, *, include_inactive: bool) -> list[StoredRecord]:
        try:
            with self.session_factory() as session:
                statement = select(UnitOfMeasure)
                if not include_inactive:
                    statement = statement.where(UnitOfMeasure.is_active.is_(True))
                entities = session.scalars(statement.order_by(UnitOfMeasure.code)).all()
                return [self._unit_record(entity) for entity in entities]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc đơn vị tính.") from exc

    def list_parts(
        self,
        *,
        filters: dict[str, Any],
        sort_by: str,
        sort_direction: str,
        page: int,
        page_size: int,
    ) -> StoredPage:
        try:
            with self.session_factory() as session:
                statement = select(SparePart)
                if filters.get("category_id"):
                    statement = statement.where(
                        SparePart.category_id == filters["category_id"]
                    )
                if filters.get("lifecycle_status"):
                    statement = statement.where(
                        SparePart.lifecycle_status == filters["lifecycle_status"]
                    )
                if filters.get("asset_type"):
                    statement = statement.where(
                        SparePart.compatible_asset_types.contains([filters["asset_type"]])
                    )
                search = str(filters.get("search") or "").strip()
                if search:
                    pattern = f"%{search}%"
                    statement = statement.where(
                        or_(
                            SparePart.part_number.ilike(pattern),
                            SparePart.name_vi.ilike(pattern),
                            SparePart.name_en.ilike(pattern),
                            SparePart.manufacturer_reference.ilike(pattern),
                        )
                    )
                records = [
                    self._part_record(session, entity)
                    for entity in session.scalars(statement).all()
                ]
                stock_state = filters.get("stock_state")
                if stock_state:
                    records = [
                        record
                        for record in records
                        if record.values["stock_state"] == stock_state
                    ]
                records.sort(
                    key=lambda item: self._part_sort_key(item.values, sort_by),
                    reverse=sort_direction == "desc",
                )
                total = len(records)
                start = (page - 1) * page_size
                return StoredPage(records[start : start + page_size], page, page_size, total)
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc danh mục spare part.") from exc

    def get_part(self, part_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(SparePart, part_id)
                return self._part_record(session, entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc spare part.") from exc

    def list_stock_locations(self, *, include_archived: bool) -> list[StoredRecord]:
        try:
            with self.session_factory() as session:
                statement = select(StockLocation)
                if not include_archived:
                    statement = statement.where(
                        StockLocation.lifecycle_status != StockLocationStatus.ARCHIVED
                    )
                entities = session.scalars(statement.order_by(StockLocation.code)).all()
                return [self._stock_location_record(entity) for entity in entities]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc stock location.") from exc

    def get_stock_location(self, location_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(StockLocation, location_id)
                return self._stock_location_record(entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc stock location.") from exc

    def list_balances(
        self,
        *,
        filters: dict[str, Any],
        sort_by: str,
        sort_direction: str,
        page: int,
        page_size: int,
    ) -> StoredPage:
        try:
            with self.session_factory() as session:
                statement = select(InventoryPosition)
                if filters.get("part_id"):
                    statement = statement.where(
                        InventoryPosition.part_id == filters["part_id"]
                    )
                if filters.get("stock_location_id"):
                    statement = statement.where(
                        InventoryPosition.stock_location_id
                        == filters["stock_location_id"]
                    )
                positions = session.scalars(statement).all()
                records = [self._balance_record(session, position) for position in positions]
                search = str(filters.get("search") or "").strip().casefold()
                if search:
                    records = [
                        item
                        for item in records
                        if search in str(item.values["part_number"]).casefold()
                        or search in str(item.values["part_name_vi"]).casefold()
                        or search in str(item.values["stock_location_code"]).casefold()
                        or search in str(item.values["stock_location_name"]).casefold()
                    ]
                if filters.get("stock_state"):
                    records = [
                        item
                        for item in records
                        if item.values["stock_state"] == filters["stock_state"]
                    ]
                if filters.get("low_stock_only"):
                    records = [
                        item
                        for item in records
                        if item.values["stock_state"]
                        in {"out_of_stock", "low_stock", "at_reorder_point"}
                    ]
                records.sort(
                    key=lambda item: self._balance_sort_key(item.values, sort_by),
                    reverse=sort_direction == "desc",
                )
                total = len(records)
                start = (page - 1) * page_size
                return StoredPage(records[start : start + page_size], page, page_size, total)
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc inventory balance.") from exc

    def list_movements(
        self,
        *,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> StoredPage:
        try:
            with self.session_factory() as session:
                statement = select(InventoryMovement)
                if filters.get("part_id"):
                    statement = statement.where(
                        InventoryMovement.part_id == filters["part_id"]
                    )
                if filters.get("stock_location_id"):
                    statement = statement.where(
                        InventoryMovement.stock_location_id
                        == filters["stock_location_id"]
                    )
                if filters.get("movement_type"):
                    statement = statement.where(
                        InventoryMovement.movement_type == filters["movement_type"]
                    )
                if filters.get("work_order_id"):
                    statement = statement.where(
                        InventoryMovement.work_order_id == filters["work_order_id"]
                    )
                if filters.get("occurred_from"):
                    statement = statement.where(
                        InventoryMovement.occurred_at >= filters["occurred_from"]
                    )
                if filters.get("occurred_to"):
                    statement = statement.where(
                        InventoryMovement.occurred_at <= filters["occurred_to"]
                    )
                total = int(
                    session.scalar(
                        select(func.count()).select_from(statement.subquery())
                    )
                    or 0
                )
                entities = session.scalars(
                    statement.order_by(
                        InventoryMovement.occurred_at.desc(),
                        InventoryMovement.movement_number.desc(),
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
                return StoredPage(
                    [self._movement_record(session, entity) for entity in entities],
                    page,
                    page_size,
                    total,
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc stock movement.") from exc

    def get_movement(self, movement_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(InventoryMovement, movement_id)
                return self._movement_record(session, entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc stock movement.") from exc

    def get_requirement(self, requirement_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(WorkOrderPartRequirement, requirement_id)
                return self._requirement_record(session, entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể đọc work-order part requirement."
            ) from exc

    def get_reservation(self, reservation_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(StockReservation, reservation_id)
                return self._reservation_record(session, entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc stock reservation.") from exc

    def list_reservations(
        self, *, filters: dict[str, Any], page: int, page_size: int
    ) -> StoredPage:
        try:
            with self.session_factory() as session:
                statement = select(StockReservation)
                if filters.get("work_order_id"):
                    statement = statement.where(
                        StockReservation.work_order_id == filters["work_order_id"]
                    )
                if filters.get("part_id"):
                    statement = statement.where(
                        StockReservation.part_id == filters["part_id"]
                    )
                if filters.get("stock_location_id"):
                    statement = statement.where(
                        StockReservation.stock_location_id
                        == filters["stock_location_id"]
                    )
                if filters.get("status"):
                    statement = statement.where(
                        StockReservation.status == filters["status"]
                    )
                total = int(
                    session.scalar(
                        select(func.count()).select_from(statement.subquery())
                    )
                    or 0
                )
                entities = session.scalars(
                    statement.order_by(StockReservation.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
                return StoredPage(
                    [self._reservation_record(session, entity) for entity in entities],
                    page,
                    page_size,
                    total,
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc stock reservations.") from exc

    def get_issue(self, issue_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(WorkOrderPartIssue, issue_id)
                return self._issue_record(session, entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc part issue.") from exc

    def get_work_order_state(self, work_order_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(WorkOrder, work_order_id)
                return self._work_order_state_record(entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc work order.") from exc

    def work_order_parts(self, work_order_id: UUID) -> StoredRecord:
        try:
            with self.session_factory() as session:
                work_order = self._require_work_order(session, work_order_id)
                requirements = session.scalars(
                    select(WorkOrderPartRequirement)
                    .where(WorkOrderPartRequirement.work_order_id == work_order_id)
                    .order_by(WorkOrderPartRequirement.created_at)
                ).all()
                reservations = session.scalars(
                    select(StockReservation)
                    .where(StockReservation.work_order_id == work_order_id)
                    .order_by(StockReservation.created_at)
                ).all()
                issues = session.scalars(
                    select(WorkOrderPartIssue)
                    .where(WorkOrderPartIssue.work_order_id == work_order_id)
                    .order_by(WorkOrderPartIssue.issued_at)
                ).all()
                movements = session.scalars(
                    select(InventoryMovement)
                    .where(InventoryMovement.work_order_id == work_order_id)
                    .order_by(InventoryMovement.occurred_at.desc())
                ).all()
                requirement_records = [
                    self._requirement_record(session, entity) for entity in requirements
                ]
                reservation_records = [
                    self._reservation_record(session, entity) for entity in reservations
                ]
                issue_records = [self._issue_record(session, entity) for entity in issues]
                planned = sum(
                    (
                        self._decimal(record.values["planned_quantity"])
                        for record in requirement_records
                    ),
                    ZERO,
                )
                reserved = sum(
                    (
                        self._decimal(record.values["remaining_quantity"])
                        for record in reservation_records
                        if record.values["status"]
                        in {
                            ReservationStatus.ACTIVE,
                            ReservationStatus.PARTIALLY_ISSUED,
                        }
                    ),
                    ZERO,
                )
                issued = sum(
                    (self._decimal(record.values["quantity"]) for record in issue_records),
                    ZERO,
                )
                returned = sum(
                    (
                        self._decimal(record.values["returned_quantity"])
                        for record in issue_records
                    ),
                    ZERO,
                )
                consumed = sum(
                    (
                        self._decimal(record.values["consumed_quantity"])
                        for record in issue_records
                    ),
                    ZERO,
                )
                shortage_count = sum(
                    1
                    for record in requirement_records
                    if self._decimal(record.values["shortage_quantity"]) > ZERO
                )
                unresolved = any(
                    self._decimal(record.values["outstanding_quantity"]) > ZERO
                    for record in issue_records
                )
                warning = (
                    "Work order còn vật tư đã issue nhưng chưa ghi consumption hoặc return."
                    if unresolved
                    else None
                )
                return StoredRecord(
                    {
                        "work_order_id": str(work_order.id),
                        "work_order_number": work_order.work_order_number,
                        "work_order_status": work_order.status,
                        "work_order_status_display": WORK_ORDER_STATUS_LABELS[
                            WorkOrderStatus(work_order.status)
                        ],
                        "assigned_to_user_id": self._uuid_text(
                            work_order.assigned_to_user_id
                        ),
                        "requirements": [
                            record.values for record in requirement_records
                        ],
                        "reservations": [
                            record.values for record in reservation_records
                        ],
                        "issues": [record.values for record in issue_records],
                        "movements": [
                            self._movement_record(session, movement).values
                            for movement in movements
                        ],
                        "total_planned_quantity": planned,
                        "total_reserved_quantity": reserved,
                        "total_issued_quantity": issued,
                        "total_returned_quantity": returned,
                        "net_consumed_quantity": consumed,
                        "open_shortage_count": shortage_count,
                        "has_unresolved_issued_stock": unresolved,
                        "completion_policy": "warning_only",
                        "completion_warning": warning,
                    }
                )
        except RecordNotFoundError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể đọc work-order inventory summary."
            ) from exc

    def inventory_metrics(self) -> StoredRecord:
        try:
            with self.session_factory() as session:
                positions = session.scalars(select(InventoryPosition)).all()
                balance_records = [
                    self._balance_record(session, position) for position in positions
                ]
                low_part_ids = {
                    record.values["part_id"]
                    for record in balance_records
                    if record.values["stock_state"]
                    in {
                        "low_stock",
                        "at_reorder_point",
                    }
                }
                out_part_ids = {
                    record.values["part_id"]
                    for record in balance_records
                    if record.values["stock_state"] == "out_of_stock"
                }
                requirements = session.scalars(
                    select(WorkOrderPartRequirement).where(
                        WorkOrderPartRequirement.status != RequirementStatus.CANCELLED
                    )
                ).all()
                shortage_requirements = [
                    requirement
                    for requirement in requirements
                    if self._decimal(
                        self._requirement_record(session, requirement).values[
                            "shortage_quantity"
                        ]
                    )
                    > ZERO
                ]
                movement_rows = session.execute(
                    select(
                        InventoryMovement.movement_type,
                        func.count(InventoryMovement.id),
                    ).group_by(InventoryMovement.movement_type)
                ).all()
                on_hand = sum(
                    (self._decimal(item.values["on_hand_quantity"]) for item in balance_records),
                    ZERO,
                )
                reserved = sum(
                    (self._decimal(item.values["reserved_quantity"]) for item in balance_records),
                    ZERO,
                )
                return StoredRecord(
                    {
                        "total_active_parts": int(
                            session.scalar(
                                select(func.count())
                                .select_from(SparePart)
                                .where(
                                    SparePart.lifecycle_status
                                    == PartLifecycleStatus.ACTIVE
                                )
                            )
                            or 0
                        ),
                        "total_on_hand_units": on_hand,
                        "total_reserved_units": reserved,
                        "total_available_units": on_hand - reserved,
                        "low_stock_parts": len(low_part_ids),
                        "out_of_stock_parts": len(out_part_ids),
                        "open_shortages": len(shortage_requirements),
                        "work_orders_waiting_for_parts": len(
                            {
                                requirement.work_order_id
                                for requirement in shortage_requirements
                            }
                        ),
                        "movements_by_type": {
                            str(movement_type): int(count)
                            for movement_type, count in movement_rows
                        },
                        "data_notice": (
                            "Tổng quantity cộng các đơn vị tính khác nhau chỉ dùng làm "
                            "chỉ báo vận hành; xem balance theo UOM để đối chiếu."
                        ),
                    }
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tính inventory metrics.") from exc

    def list_inventory_attachments(
        self, movement_id: UUID, *, include_deleted: bool = False
    ) -> list[StoredRecord]:
        try:
            with self.session_factory() as session:
                statement = select(InventoryAttachment).where(
                    InventoryAttachment.movement_id == movement_id
                )
                if not include_deleted:
                    statement = statement.where(InventoryAttachment.deleted_at.is_(None))
                entities = session.scalars(
                    statement.order_by(InventoryAttachment.created_at.desc())
                ).all()
                return [self._inventory_attachment_record(entity) for entity in entities]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc inventory evidence.") from exc

    def get_inventory_attachment(
        self, movement_id: UUID, attachment_id: UUID
    ) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.scalar(
                    select(InventoryAttachment).where(
                        InventoryAttachment.id == attachment_id,
                        InventoryAttachment.movement_id == movement_id,
                    )
                )
                return (
                    self._inventory_attachment_record(entity, include_storage_key=True)
                    if entity
                    else None
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc inventory evidence.") from exc
