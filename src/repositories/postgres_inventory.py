"""PostgreSQL repository for spare-parts inventory and stock control."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import (
    InventoryAttachment,
    InventoryMovement,
    InventoryOperation,
    InventoryPosition,
    PartCategory,
    PartReorderConfiguration,
    SparePart,
    StockLocation,
    StockReservation,
    StockReservationEvent,
    UnitOfMeasure,
    User,
    WorkOrder,
    WorkOrderPartConsumption,
    WorkOrderPartIssue,
    WorkOrderPartRequirement,
    WorkOrderPartReturn,
)
from src.inventory_management.domain import (
    ACTIVE_RESERVATION_STATUSES,
    MOVEMENT_TYPE_LABELS,
    PART_LIFECYCLE_LABELS,
    REQUIREMENT_STATUS_LABELS,
    RESERVATION_STATUS_LABELS,
    STOCK_LOCATION_STATUS_LABELS,
    STOCK_LOCATION_TYPE_LABELS,
    STOCK_STATE_LABELS,
    InventoryMovementType,
    InventoryOperationType,
    PartLifecycleStatus,
    RequirementStatus,
    ReservationStatus,
    StockLocationStatus,
    StockLocationType,
    available_quantity,
    derive_stock_state,
    reorder_suggestion,
)
from src.operations.outbox import enqueue_outbox_event
from src.repositories.contracts import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    RecordNotFoundError,
    RepositoryError,
    StaleRecordError,
    StorageUnavailableError,
    StoredPage,
    StoredRecord,
)
from src.repositories.postgres.inventory.attachments import InventoryAttachmentRepository
from src.repositories.postgres.inventory.catalogue import InventoryCatalogueRepository
from src.repositories.postgres.inventory.queries import InventoryQueryRepository
from src.security.audit import AuditContext, safe_state
from src.security.service import append_audit_event

MOVEMENT_SEQUENCE = "inventory_movement_number_seq"
RESERVATION_SEQUENCE = "stock_reservation_number_seq"
ISSUE_SEQUENCE = "part_issue_number_seq"
RETURN_SEQUENCE = "part_return_number_seq"
ZERO = Decimal("0")

PART_AUDIT_FIELDS = {
    "id",
    "part_number",
    "category_id",
    "unit_of_measure_id",
    "compatible_asset_types",
    "lifecycle_status",
    "minimum_stock",
    "reorder_point",
    "maximum_stock",
    "unit_cost",
    "currency_code",
    "archived_at",
    "version",
}
LOCATION_AUDIT_FIELDS = {
    "id",
    "code",
    "location_type",
    "lifecycle_status",
    "archived_at",
    "version",
}
MOVEMENT_AUDIT_FIELDS = {
    "id",
    "movement_number",
    "part_id",
    "stock_location_id",
    "quantity",
    "movement_type",
    "business_reference",
    "work_order_id",
    "occurred_at",
    "resulting_on_hand_quantity",
    "resulting_reserved_quantity",
}
REQUIREMENT_AUDIT_FIELDS = {
    "id",
    "work_order_id",
    "part_id",
    "planned_quantity",
    "source_stock_location_id",
    "status",
    "version",
}
RESERVATION_AUDIT_FIELDS = {
    "id",
    "reservation_number",
    "requirement_id",
    "work_order_id",
    "part_id",
    "stock_location_id",
    "quantity",
    "status",
    "version",
}
ISSUE_AUDIT_FIELDS = {
    "id",
    "issue_number",
    "work_order_id",
    "requirement_id",
    "reservation_id",
    "part_id",
    "stock_location_id",
    "quantity",
    "reserved_quantity_used",
    "issued_at",
}
ATTACHMENT_AUDIT_FIELDS = {
    "id",
    "movement_id",
    "category",
    "original_filename",
    "media_type",
    "size_bytes",
    "checksum",
    "uploaded_by_user_id",
    "created_at",
    "deleted_at",
    "deleted_by_user_id",
}


class PostgresInventoryRepository:
    """Persist inventory actions with row locks and append-only history."""

    backend_name = "postgresql"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self.queries = InventoryQueryRepository(
            session_factory,
            category_record=_category_record,
            unit_record=_unit_record,
            part_record=_part_record,
            stock_location_record=_stock_location_record,
            balance_record=_balance_record,
            movement_record=_movement_record,
            requirement_record=_requirement_record,
            reservation_record=_reservation_record,
            issue_record=_issue_record,
            work_order_state_record=_work_order_state_record,
            inventory_attachment_record=_inventory_attachment_record,
            part_sort_key=_part_sort_key,
            balance_sort_key=_balance_sort_key,
            require_work_order=_require_work_order,
            decimal_value=_decimal,
            uuid_text=_uuid_text,
        )
        self.catalogue = InventoryCatalogueRepository(
            session_factory,
            category_record=_category_record,
            unit_record=_unit_record,
            part_record=_part_record,
            stock_location_record=_stock_location_record,
            reorder_record=_reorder_record,
            require_active_reference=_require_active_reference,
            require_part=_require_part,
            require_stock_location=_require_stock_location,
            ensure_position=_ensure_position,
            audit=_audit,
            require_version=_require_version,
            raise_integrity=_raise_integrity,
            decimal_value=_decimal,
            part_audit_fields=PART_AUDIT_FIELDS,
            location_audit_fields=LOCATION_AUDIT_FIELDS,
        )
        self.attachments = InventoryAttachmentRepository(
            session_factory,
            attachment_record=_inventory_attachment_record,
            audit=_audit,
            raise_integrity=_raise_integrity,
            utc_now=_utc_now,
            audit_fields=ATTACHMENT_AUDIT_FIELDS,
        )

    def list_categories(self, *, include_inactive: bool) -> list[StoredRecord]:
        return self.queries.list_categories(include_inactive=include_inactive)

    def create_category(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        return self.catalogue.create_category(values, audit_context=audit_context)

    def list_units(self, *, include_inactive: bool) -> list[StoredRecord]:
        return self.queries.list_units(include_inactive=include_inactive)

    def create_unit(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        return self.catalogue.create_unit(values, audit_context=audit_context)

    def list_parts(
        self,
        *,
        filters: dict[str, Any],
        sort_by: str,
        sort_direction: str,
        page: int,
        page_size: int,
    ) -> StoredPage:
        return self.queries.list_parts(
            filters=filters,
            sort_by=sort_by,
            sort_direction=sort_direction,
            page=page,
            page_size=page_size,
        )

    def get_part(self, part_id: UUID) -> StoredRecord | None:
        return self.queries.get_part(part_id)

    def create_part(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        return self.catalogue.create_part(values, audit_context=audit_context)

    def update_part(
        self,
        part_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        return self.catalogue.update_part(
            part_id,
            updates,
            expected_version=expected_version,
            audit_action=audit_action,
            audit_context=audit_context,
        )

    def list_stock_locations(self, *, include_archived: bool) -> list[StoredRecord]:
        return self.queries.list_stock_locations(include_archived=include_archived)

    def get_stock_location(self, location_id: UUID) -> StoredRecord | None:
        return self.queries.get_stock_location(location_id)

    def create_stock_location(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        return self.catalogue.create_stock_location(values, audit_context=audit_context)

    def update_stock_location(
        self,
        location_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        return self.catalogue.update_stock_location(
            location_id,
            updates,
            expected_version=expected_version,
            audit_action=audit_action,
            audit_context=audit_context,
        )

    def upsert_reorder_configuration(
        self,
        values: dict[str, Any],
        *,
        expected_version: int | None,
        audit_context: AuditContext,
    ) -> StoredRecord:
        return self.catalogue.upsert_reorder_configuration(
            values,
            expected_version=expected_version,
            audit_context=audit_context,
        )

    def list_balances(
        self,
        *,
        filters: dict[str, Any],
        sort_by: str,
        sort_direction: str,
        page: int,
        page_size: int,
    ) -> StoredPage:
        return self.queries.list_balances(
            filters=filters,
            sort_by=sort_by,
            sort_direction=sort_direction,
            page=page,
            page_size=page_size,
        )

    def list_movements(
        self,
        *,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> StoredPage:
        return self.queries.list_movements(
            filters=filters,
            page=page,
            page_size=page_size,
        )

    def get_movement(self, movement_id: UUID) -> StoredRecord | None:
        return self.queries.get_movement(movement_id)

    def create_opening_balance(
        self,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        return self._increase_stock(
            values,
            operation_type=InventoryOperationType.OPENING_BALANCE,
            movement_type=InventoryMovementType.OPENING_BALANCE,
            idempotency_key=idempotency_key,
            audit_action="inventory.opening_balance_created",
            opening_only=True,
            audit_context=audit_context,
        )

    def receive_stock(
        self,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        return self._increase_stock(
            values,
            operation_type=InventoryOperationType.RECEIPT,
            movement_type=InventoryMovementType.RECEIPT,
            idempotency_key=idempotency_key,
            audit_action="inventory.receipt_created",
            opening_only=False,
            audit_context=audit_context,
        )

    def _increase_stock(
        self,
        values: dict[str, Any],
        *,
        operation_type: InventoryOperationType,
        movement_type: InventoryMovementType,
        idempotency_key: str,
        audit_action: str,
        opening_only: bool,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                operation, replay = _claim_operation(
                    session,
                    idempotency_key=idempotency_key,
                    operation_type=operation_type,
                    request_hash=_request_hash(operation_type, values),
                    actor_user_id=audit_context.actor_user_id,
                )
                if replay:
                    return _operation_movement_result(session, operation)
                part = _require_active_part(session, values["part_id"])
                location = _require_active_stock_location(
                    session, values["stock_location_id"]
                )
                position = _locked_position(session, part.id, location.id)
                if opening_only:
                    movement_count = int(
                        session.scalar(
                            select(func.count())
                            .select_from(InventoryMovement)
                            .where(
                                InventoryMovement.part_id == part.id,
                                InventoryMovement.stock_location_id == location.id,
                            )
                        )
                        or 0
                    )
                    if (
                        movement_count
                        or _decimal(position.on_hand_quantity) != ZERO
                        or _decimal(position.reserved_quantity) != ZERO
                    ):
                        raise IntegrityViolationError(
                            "Số dư đầu kỳ chỉ được tạo một lần cho part và stock location."
                        )
                position.on_hand_quantity = _decimal(position.on_hand_quantity) + _decimal(
                    values["quantity"]
                )
                movement = _new_movement(
                    session,
                    operation=operation,
                    part=part,
                    position=position,
                    movement_type=movement_type,
                    values=values,
                    audit_context=audit_context,
                )
                _complete_operation(operation, "inventory_movement", movement.id)
                session.flush()
                result = _movement_record(session, movement)
                _audit(
                    session,
                    audit_context,
                    action=audit_action,
                    resource_type="inventory_movement",
                    resource_id=str(movement.id),
                    after=result.values,
                    fields=MOVEMENT_AUDIT_FIELDS,
                )
            return result
        except (
            DuplicateIdentifierError,
            IntegrityViolationError,
            RecordNotFoundError,
        ):
            raise
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Inventory operation đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể ghi stock movement.") from exc

    # Atomic transfer: both positions, paired movements, idempotency, and audit stay together.
    def transfer_stock(
        self,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> dict[str, StoredRecord | UUID]:
        try:
            with self.session_factory() as session, session.begin():
                operation, replay = _claim_operation(
                    session,
                    idempotency_key=idempotency_key,
                    operation_type=InventoryOperationType.TRANSFER,
                    request_hash=_request_hash(
                        InventoryOperationType.TRANSFER, values
                    ),
                    actor_user_id=audit_context.actor_user_id,
                )
                if replay:
                    return _operation_transfer_result(session, operation)
                part = _require_active_part(session, values["part_id"])
                source = _require_active_stock_location(
                    session, values["source_stock_location_id"]
                )
                destination = _require_active_stock_location(
                    session, values["destination_stock_location_id"]
                )
                positions = _locked_positions(
                    session, part.id, [source.id, destination.id]
                )
                source_position = positions[source.id]
                destination_position = positions[destination.id]
                quantity = _decimal(values["quantity"])
                if available_quantity(
                    _decimal(source_position.on_hand_quantity),
                    _decimal(source_position.reserved_quantity),
                ) < quantity:
                    raise IntegrityViolationError(
                        "Available quantity tại kho nguồn không đủ để chuyển."
                    )
                source_position.on_hand_quantity = (
                    _decimal(source_position.on_hand_quantity) - quantity
                )
                destination_position.on_hand_quantity = (
                    _decimal(destination_position.on_hand_quantity) + quantity
                )
                transfer_group_id = uuid4()
                common = {
                    **values,
                    "source_location_id": source.id,
                    "destination_location_id": destination.id,
                    "transfer_group_id": transfer_group_id,
                }
                transfer_out = _new_movement(
                    session,
                    operation=operation,
                    part=part,
                    position=source_position,
                    movement_type=InventoryMovementType.TRANSFER_OUT,
                    values=common,
                    audit_context=audit_context,
                )
                transfer_in = _new_movement(
                    session,
                    operation=operation,
                    part=part,
                    position=destination_position,
                    movement_type=InventoryMovementType.TRANSFER_IN,
                    values=common,
                    audit_context=audit_context,
                )
                _complete_operation(operation, "inventory_transfer", transfer_group_id)
                session.flush()
                out_record = _movement_record(session, transfer_out)
                in_record = _movement_record(session, transfer_in)
                _audit(
                    session,
                    audit_context,
                    action="inventory.stock_transferred",
                    resource_type="inventory_transfer",
                    resource_id=str(transfer_group_id),
                    after={
                        "part_id": str(part.id),
                        "quantity": quantity,
                        "source_stock_location_id": str(source.id),
                        "destination_stock_location_id": str(destination.id),
                    },
                    fields={
                        "part_id",
                        "quantity",
                        "source_stock_location_id",
                        "destination_stock_location_id",
                    },
                    metadata={
                        "transfer_out_movement_id": str(transfer_out.id),
                        "transfer_in_movement_id": str(transfer_in.id),
                    },
                )
            return {
                "transfer_group_id": transfer_group_id,
                "transfer_out": out_record,
                "transfer_in": in_record,
            }
        except (
            DuplicateIdentifierError,
            IntegrityViolationError,
            RecordNotFoundError,
        ):
            raise
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Inventory transfer đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể chuyển stock giữa hai kho.") from exc

    def adjust_stock(
        self,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        operation_type = InventoryOperationType(values["operation_type"])
        movement_type = InventoryMovementType(values["movement_type"])
        try:
            with self.session_factory() as session, session.begin():
                operation, replay = _claim_operation(
                    session,
                    idempotency_key=idempotency_key,
                    operation_type=operation_type,
                    request_hash=_request_hash(operation_type, values),
                    actor_user_id=audit_context.actor_user_id,
                )
                if replay:
                    return _operation_movement_result(session, operation)
                part = _require_active_part(session, values["part_id"])
                location = _require_active_stock_location(
                    session, values["stock_location_id"]
                )
                position = _locked_position(session, part.id, location.id)
                quantity = _decimal(values["quantity"])
                if movement_type is InventoryMovementType.ADJUSTMENT_INCREASE:
                    position.on_hand_quantity = (
                        _decimal(position.on_hand_quantity) + quantity
                    )
                else:
                    if available_quantity(
                        _decimal(position.on_hand_quantity),
                        _decimal(position.reserved_quantity),
                    ) < quantity:
                        raise IntegrityViolationError(
                            "Không thể điều chỉnh làm available quantity âm."
                        )
                    position.on_hand_quantity = (
                        _decimal(position.on_hand_quantity) - quantity
                    )
                movement = _new_movement(
                    session,
                    operation=operation,
                    part=part,
                    position=position,
                    movement_type=movement_type,
                    values=values,
                    audit_context=audit_context,
                )
                _complete_operation(operation, "inventory_movement", movement.id)
                session.flush()
                result = _movement_record(session, movement)
                action = (
                    "inventory.damaged_stock_recorded"
                    if movement_type is InventoryMovementType.DAMAGED_SCRAPPED
                    else "inventory.stock_adjusted"
                )
                _audit(
                    session,
                    audit_context,
                    action=action,
                    resource_type="inventory_movement",
                    resource_id=str(movement.id),
                    after=result.values,
                    fields=MOVEMENT_AUDIT_FIELDS,
                    metadata={"supporting_note": values.get("supporting_note")},
                )
            return result
        except (
            DuplicateIdentifierError,
            IntegrityViolationError,
            RecordNotFoundError,
        ):
            raise
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Inventory adjustment đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể điều chỉnh stock.") from exc

    def create_requirement(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                work_order = _require_work_order(session, values["work_order_id"])
                _require_active_part(session, values["part_id"])
                _require_active_stock_location(
                    session, values["source_stock_location_id"]
                )
                entity = WorkOrderPartRequirement(id=uuid4(), **values)
                session.add(entity)
                session.flush()
                result = _requirement_record(session, entity)
                _audit(
                    session,
                    audit_context,
                    action="inventory.work_order_requirement_created",
                    resource_type="work_order_part_requirement",
                    resource_id=str(entity.id),
                    after=result.values,
                    fields=REQUIREMENT_AUDIT_FIELDS,
                    metadata={"work_order_number": work_order.work_order_number},
                )
            return result
        except RecordNotFoundError:
            raise
        except IntegrityError as exc:
            _raise_integrity(
                exc,
                duplicate_message=(
                    "Work order đã có requirement cho part và stock location này."
                ),
            )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể tạo work-order part requirement."
            ) from exc

    def get_requirement(self, requirement_id: UUID) -> StoredRecord | None:
        return self.queries.get_requirement(requirement_id)

    # Atomic reservation: position lock, reservation event, requirement state, and audit.
    def reserve_stock(
        self,
        requirement_id: UUID,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        expected_requirement_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                operation, replay = _claim_operation(
                    session,
                    idempotency_key=idempotency_key,
                    operation_type=InventoryOperationType.RESERVE,
                    request_hash=_request_hash(
                        InventoryOperationType.RESERVE,
                        {
                            "requirement_id": requirement_id,
                            "expected_requirement_version": expected_requirement_version,
                            **values,
                        },
                    ),
                    actor_user_id=audit_context.actor_user_id,
                )
                if replay:
                    return _operation_reservation_result(session, operation)
                requirement = session.scalar(
                    select(WorkOrderPartRequirement)
                    .where(WorkOrderPartRequirement.id == requirement_id)
                    .with_for_update()
                )
                if requirement is None:
                    raise RecordNotFoundError(
                        f"Không tìm thấy part requirement: {requirement_id}"
                    )
                _require_version(
                    requirement.version,
                    expected_requirement_version,
                    str(requirement.id),
                )
                if requirement.status == RequirementStatus.CANCELLED:
                    raise IntegrityViolationError(
                        "Không thể reserve cho requirement đã hủy."
                    )
                active = session.scalar(
                    select(StockReservation).where(
                        StockReservation.requirement_id == requirement.id,
                        StockReservation.status.in_(
                            [status.value for status in ACTIVE_RESERVATION_STATUSES]
                        ),
                    )
                )
                if active is not None:
                    raise IntegrityViolationError(
                        "Requirement đã có active reservation; hãy dùng replace."
                    )
                part = _require_active_part(session, requirement.part_id)
                location = _require_active_stock_location(
                    session, requirement.source_stock_location_id
                )
                position = _locked_position(session, part.id, location.id)
                quantity = _decimal(values["quantity"])
                if available_quantity(
                    _decimal(position.on_hand_quantity),
                    _decimal(position.reserved_quantity),
                ) < quantity:
                    raise IntegrityViolationError(
                        "Available quantity không đủ để reserve."
                    )
                totals = _requirement_totals(session, requirement.id)
                shortage = max(
                    _decimal(requirement.planned_quantity)
                    - totals["consumed"]
                    - totals["outstanding_issued"],
                    ZERO,
                )
                if quantity > shortage:
                    raise IntegrityViolationError(
                        "Reservation vượt quá quantity còn thiếu của requirement."
                    )
                occurrence = (
                    int(
                        session.scalar(
                            select(func.max(StockReservation.occurrence_number)).where(
                                StockReservation.requirement_id == requirement.id
                            )
                        )
                        or 0
                    )
                    + 1
                )
                position.reserved_quantity = (
                    _decimal(position.reserved_quantity) + quantity
                )
                reservation = StockReservation(
                    id=uuid4(),
                    reservation_number=_next_number(
                        session, RESERVATION_SEQUENCE, "RES"
                    ),
                    operation_id=operation.id,
                    requirement_id=requirement.id,
                    work_order_id=requirement.work_order_id,
                    part_id=requirement.part_id,
                    stock_location_id=requirement.source_stock_location_id,
                    occurrence_number=occurrence,
                    quantity=quantity,
                    status=ReservationStatus.ACTIVE,
                    expires_at=values.get("expires_at"),
                    created_by_user_id=audit_context.actor_user_id,
                )
                session.add(reservation)
                session.add(
                    _reservation_event(
                        reservation_id=reservation.id,
                        operation_id=operation.id,
                        event_type="reserved",
                        quantity=quantity,
                        reason=values["reason"],
                        audit_context=audit_context,
                        occurred_at=values["occurred_at"],
                    )
                )
                session.flush()
                _sync_requirement_status(session, requirement, audit_context.actor_user_id)
                _complete_operation(operation, "stock_reservation", reservation.id)
                session.flush()
                result = _reservation_record(session, reservation)
                _audit(
                    session,
                    audit_context,
                    action="inventory.stock_reserved",
                    resource_type="stock_reservation",
                    resource_id=str(reservation.id),
                    after=result.values,
                    fields=RESERVATION_AUDIT_FIELDS,
                )
            return result
        except (
            DuplicateIdentifierError,
            IntegrityViolationError,
            RecordNotFoundError,
            StaleRecordError,
        ):
            raise
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Active reservation đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể reserve stock.") from exc

    def get_reservation(self, reservation_id: UUID) -> StoredRecord | None:
        return self.queries.get_reservation(reservation_id)

    def list_reservations(
        self, *, filters: dict[str, Any], page: int, page_size: int
    ) -> StoredPage:
        return self.queries.list_reservations(
            filters=filters,
            page=page,
            page_size=page_size,
        )

    def close_reservation(
        self,
        reservation_id: UUID,
        *,
        target_status: str,
        reason: str,
        expected_version: int,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        operation_type = (
            InventoryOperationType.RELEASE_RESERVATION
            if target_status == ReservationStatus.RELEASED
            else InventoryOperationType.EXPIRE_RESERVATION
        )
        event_type = "released" if target_status == ReservationStatus.RELEASED else "expired"
        try:
            with self.session_factory() as session, session.begin():
                operation, replay = _claim_operation(
                    session,
                    idempotency_key=idempotency_key,
                    operation_type=operation_type,
                    request_hash=_request_hash(
                        operation_type,
                        {
                            "reservation_id": reservation_id,
                            "target_status": target_status,
                            "reason": reason,
                            "expected_version": expected_version,
                        },
                    ),
                    actor_user_id=audit_context.actor_user_id,
                )
                if replay:
                    return _operation_reservation_result(session, operation)
                reservation = session.scalar(
                    select(StockReservation)
                    .where(StockReservation.id == reservation_id)
                    .with_for_update()
                )
                if reservation is None:
                    raise RecordNotFoundError(
                        f"Không tìm thấy stock reservation: {reservation_id}"
                    )
                _require_version(
                    reservation.version, expected_version, reservation.reservation_number
                )
                if ReservationStatus(reservation.status) not in ACTIVE_RESERVATION_STATUSES:
                    raise IntegrityViolationError(
                        "Chỉ active reservation mới có thể release hoặc expire."
                    )
                remaining = _reservation_remaining(session, reservation)
                if remaining <= ZERO:
                    raise IntegrityViolationError(
                        "Reservation không còn quantity để giải phóng."
                    )
                position = _locked_position(
                    session, reservation.part_id, reservation.stock_location_id
                )
                if _decimal(position.reserved_quantity) < remaining:
                    raise IntegrityViolationError(
                        "Reserved position không khớp reservation history."
                    )
                position.reserved_quantity = (
                    _decimal(position.reserved_quantity) - remaining
                )
                reservation.status = target_status
                session.add(
                    _reservation_event(
                        reservation_id=reservation.id,
                        operation_id=operation.id,
                        event_type=event_type,
                        quantity=remaining,
                        reason=reason,
                        audit_context=audit_context,
                        occurred_at=_utc_now(),
                    )
                )
                session.flush()
                requirement = session.get(
                    WorkOrderPartRequirement, reservation.requirement_id
                )
                if requirement is not None:
                    _sync_requirement_status(
                        session, requirement, audit_context.actor_user_id
                    )
                _complete_operation(operation, "stock_reservation", reservation.id)
                session.flush()
                result = _reservation_record(session, reservation)
                _audit(
                    session,
                    audit_context,
                    action=(
                        "inventory.reservation_released"
                        if target_status == ReservationStatus.RELEASED
                        else "inventory.reservation_expired"
                    ),
                    resource_type="stock_reservation",
                    resource_id=str(reservation.id),
                    after=result.values,
                    fields=RESERVATION_AUDIT_FIELDS,
                    metadata={"released_quantity": remaining},
                )
            return result
        except (
            DuplicateIdentifierError,
            IntegrityViolationError,
            RecordNotFoundError,
            StaleRecordError,
        ):
            raise
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Reservation action đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể release hoặc expire reservation."
            ) from exc

    def replace_reservation(
        self,
        reservation_id: UUID,
        values: dict[str, Any],
        *,
        expected_version: int,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                operation, replay = _claim_operation(
                    session,
                    idempotency_key=idempotency_key,
                    operation_type=InventoryOperationType.REPLACE_RESERVATION,
                    request_hash=_request_hash(
                        InventoryOperationType.REPLACE_RESERVATION,
                        {
                            "reservation_id": reservation_id,
                            "expected_version": expected_version,
                            **values,
                        },
                    ),
                    actor_user_id=audit_context.actor_user_id,
                )
                if replay:
                    return _operation_reservation_result(session, operation)
                old = session.scalar(
                    select(StockReservation)
                    .where(StockReservation.id == reservation_id)
                    .with_for_update()
                )
                if old is None:
                    raise RecordNotFoundError(
                        f"Không tìm thấy stock reservation: {reservation_id}"
                    )
                _require_version(old.version, expected_version, old.reservation_number)
                if ReservationStatus(old.status) not in ACTIVE_RESERVATION_STATUSES:
                    raise IntegrityViolationError(
                        "Chỉ active reservation mới có thể được thay thế."
                    )
                requirement = session.scalar(
                    select(WorkOrderPartRequirement)
                    .where(WorkOrderPartRequirement.id == old.requirement_id)
                    .with_for_update()
                )
                if requirement is None:
                    raise RecordNotFoundError(
                        f"Không tìm thấy part requirement: {old.requirement_id}"
                    )
                part = _require_active_part(session, old.part_id)
                destination = _require_active_stock_location(
                    session, values["stock_location_id"]
                )
                positions = _locked_positions(
                    session,
                    part.id,
                    [old.stock_location_id, destination.id],
                )
                old_position = positions[old.stock_location_id]
                new_position = positions[destination.id]
                old_remaining = _reservation_remaining(session, old)
                if _decimal(old_position.reserved_quantity) < old_remaining:
                    raise IntegrityViolationError(
                        "Reserved position không khớp reservation history."
                    )
                old_position.reserved_quantity = (
                    _decimal(old_position.reserved_quantity) - old_remaining
                )
                quantity = _decimal(values["quantity"])
                if available_quantity(
                    _decimal(new_position.on_hand_quantity),
                    _decimal(new_position.reserved_quantity),
                ) < quantity:
                    raise IntegrityViolationError(
                        "Available quantity không đủ cho replacement reservation."
                    )
                totals = _requirement_totals(session, requirement.id)
                shortage = max(
                    _decimal(requirement.planned_quantity)
                    - totals["consumed"]
                    - totals["outstanding_issued"],
                    ZERO,
                )
                if quantity > shortage:
                    raise IntegrityViolationError(
                        "Replacement reservation vượt quantity còn thiếu."
                    )
                occurrence = (
                    int(
                        session.scalar(
                            select(func.max(StockReservation.occurrence_number)).where(
                                StockReservation.requirement_id == requirement.id
                            )
                        )
                        or 0
                    )
                    + 1
                )
                old.status = ReservationStatus.REPLACED
                session.flush()
                replacement = StockReservation(
                    id=uuid4(),
                    reservation_number=_next_number(
                        session, RESERVATION_SEQUENCE, "RES"
                    ),
                    operation_id=operation.id,
                    requirement_id=requirement.id,
                    work_order_id=requirement.work_order_id,
                    part_id=requirement.part_id,
                    stock_location_id=destination.id,
                    occurrence_number=occurrence,
                    quantity=quantity,
                    status=ReservationStatus.ACTIVE,
                    expires_at=values.get("expires_at"),
                    created_by_user_id=audit_context.actor_user_id,
                )
                session.add(replacement)
                session.flush()
                old.replaced_by_reservation_id = replacement.id
                new_position.reserved_quantity = (
                    _decimal(new_position.reserved_quantity) + quantity
                )
                session.add_all(
                    [
                        _reservation_event(
                            reservation_id=old.id,
                            operation_id=operation.id,
                            event_type="replaced",
                            quantity=old_remaining,
                            reason=values["reason"],
                            audit_context=audit_context,
                            occurred_at=values["occurred_at"],
                        ),
                        _reservation_event(
                            reservation_id=replacement.id,
                            operation_id=operation.id,
                            event_type="reserved",
                            quantity=quantity,
                            reason=values["reason"],
                            audit_context=audit_context,
                            occurred_at=values["occurred_at"],
                        ),
                    ]
                )
                session.flush()
                _sync_requirement_status(session, requirement, audit_context.actor_user_id)
                _complete_operation(operation, "stock_reservation", replacement.id)
                session.flush()
                result = _reservation_record(session, replacement)
                _audit(
                    session,
                    audit_context,
                    action="inventory.reservation_replaced",
                    resource_type="stock_reservation",
                    resource_id=str(replacement.id),
                    after=result.values,
                    fields=RESERVATION_AUDIT_FIELDS,
                    metadata={
                        "replaced_reservation_id": str(old.id),
                        "released_quantity": old_remaining,
                    },
                )
            return result
        except (
            DuplicateIdentifierError,
            IntegrityViolationError,
            RecordNotFoundError,
            StaleRecordError,
        ):
            raise
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Replacement reservation đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể replace reservation.") from exc

    # Atomic issue: reservation/requirement locks, movements, issue rows, audit, and outbox.
    def issue_stock(
        self,
        work_order_id: UUID,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                operation, replay = _claim_operation(
                    session,
                    idempotency_key=idempotency_key,
                    operation_type=InventoryOperationType.ISSUE,
                    request_hash=_request_hash(
                        InventoryOperationType.ISSUE,
                        {"work_order_id": work_order_id, **values},
                    ),
                    actor_user_id=audit_context.actor_user_id,
                )
                if replay:
                    return _operation_issue_result(session, operation)
                work_order = session.scalar(
                    select(WorkOrder)
                    .where(WorkOrder.id == work_order_id)
                    .with_for_update()
                )
                if work_order is None:
                    raise RecordNotFoundError(f"Không tìm thấy work order: {work_order_id}")
                part = _require_active_part(session, values["part_id"])
                location = _require_active_stock_location(
                    session, values["stock_location_id"]
                )
                requirement: WorkOrderPartRequirement | None = None
                reservation: StockReservation | None = None
                if values.get("requirement_id"):
                    requirement = session.scalar(
                        select(WorkOrderPartRequirement)
                        .where(
                            WorkOrderPartRequirement.id == values["requirement_id"]
                        )
                        .with_for_update()
                    )
                    if requirement is None:
                        raise RecordNotFoundError(
                            f"Không tìm thấy part requirement: {values['requirement_id']}"
                        )
                    if (
                        requirement.work_order_id != work_order.id
                        or requirement.part_id != part.id
                    ):
                        raise IntegrityViolationError(
                            "Requirement không thuộc work order hoặc spare part đã chọn."
                        )
                if values.get("reservation_id"):
                    reservation = session.scalar(
                        select(StockReservation)
                        .where(StockReservation.id == values["reservation_id"])
                        .with_for_update()
                    )
                    if reservation is None:
                        raise RecordNotFoundError(
                            f"Không tìm thấy stock reservation: {values['reservation_id']}"
                        )
                    if (
                        reservation.work_order_id != work_order.id
                        or reservation.part_id != part.id
                        or reservation.stock_location_id != location.id
                        or (
                            requirement is not None
                            and reservation.requirement_id != requirement.id
                        )
                    ):
                        raise IntegrityViolationError(
                            "Reservation không khớp work order, part, location hoặc requirement."
                        )
                    if ReservationStatus(reservation.status) not in ACTIVE_RESERVATION_STATUSES:
                        raise IntegrityViolationError(
                            "Reservation không còn active để issue."
                        )
                issued_to = None
                if values.get("issued_to_user_id"):
                    issued_to = _require_active_user(
                        session, values["issued_to_user_id"]
                    )
                position = _locked_position(session, part.id, location.id)
                quantity = _decimal(values["quantity"])
                reservation_remaining = (
                    _reservation_remaining(session, reservation)
                    if reservation is not None
                    else ZERO
                )
                reserved_used = min(quantity, reservation_remaining)
                unreserved_quantity = quantity - reserved_used
                current_available = available_quantity(
                    _decimal(position.on_hand_quantity),
                    _decimal(position.reserved_quantity),
                )
                if unreserved_quantity > current_available:
                    raise IntegrityViolationError(
                        "Available quantity cộng reservation hợp lệ không đủ để issue."
                    )
                position.on_hand_quantity = (
                    _decimal(position.on_hand_quantity) - quantity
                )
                position.reserved_quantity = (
                    _decimal(position.reserved_quantity) - reserved_used
                )
                movement_values = {
                    "quantity": quantity,
                    "business_reference": values["business_reference"],
                    "occurred_at": values["issued_at"],
                    "reason": values["reason"],
                    "work_order_id": work_order.id,
                    "unit_cost_snapshot": part.unit_cost,
                }
                movement = _new_movement(
                    session,
                    operation=operation,
                    part=part,
                    position=position,
                    movement_type=InventoryMovementType.ISSUE,
                    values=movement_values,
                    audit_context=audit_context,
                )
                session.flush()
                issue = WorkOrderPartIssue(
                    id=uuid4(),
                    issue_number=_next_number(session, ISSUE_SEQUENCE, "ISS"),
                    operation_id=operation.id,
                    work_order_id=work_order.id,
                    requirement_id=requirement.id if requirement else None,
                    reservation_id=reservation.id if reservation else None,
                    part_id=part.id,
                    stock_location_id=location.id,
                    quantity=quantity,
                    reserved_quantity_used=reserved_used,
                    issued_to_user_id=issued_to.id if issued_to else None,
                    issued_by_user_id=audit_context.actor_user_id,
                    issued_at=values["issued_at"],
                    reason=values["reason"],
                    movement_id=movement.id,
                )
                session.add(issue)
                if reservation is not None and reserved_used > ZERO:
                    session.add(
                        _reservation_event(
                            reservation_id=reservation.id,
                            operation_id=operation.id,
                            event_type="issued",
                            quantity=reserved_used,
                            reason=values["reason"],
                            audit_context=audit_context,
                            occurred_at=values["issued_at"],
                        )
                    )
                    if reservation_remaining == reserved_used:
                        reservation.status = ReservationStatus.FULFILLED
                        session.add(
                            _reservation_event(
                                reservation_id=reservation.id,
                                operation_id=operation.id,
                                event_type="fulfilled",
                                quantity=reserved_used,
                                reason="Reservation đã được issue hết.",
                                audit_context=audit_context,
                                occurred_at=values["issued_at"],
                            )
                        )
                    else:
                        reservation.status = ReservationStatus.PARTIALLY_ISSUED
                session.flush()
                if requirement is not None:
                    _sync_requirement_status(
                        session, requirement, audit_context.actor_user_id
                    )
                _complete_operation(operation, "work_order_part_issue", issue.id)
                session.flush()
                result = _issue_record(session, issue)
                _audit(
                    session,
                    audit_context,
                    action="inventory.part_issued",
                    resource_type="work_order_part_issue",
                    resource_id=str(issue.id),
                    after=result.values,
                    fields=ISSUE_AUDIT_FIELDS,
                    metadata={"movement_id": str(movement.id)},
                )
                enqueue_outbox_event(
                    session,
                    event_type="inventory.issue_completed",
                    aggregate_type="inventory_issue",
                    aggregate_id=str(issue.id),
                    payload={
                        "issue_id": str(issue.id),
                        "issue_number": issue.issue_number,
                        "work_order_id": str(issue.work_order_id),
                        "part_id": str(issue.part_id),
                        "stock_location_id": str(issue.stock_location_id),
                        "issued_to_user_id": (
                            str(issue.issued_to_user_id)
                            if issue.issued_to_user_id
                            else None
                        ),
                    },
                    idempotency_key=f"inventory-issue:{issue.id}:completed",
                )
            return result
        except (
            DuplicateIdentifierError,
            IntegrityViolationError,
            RecordNotFoundError,
        ):
            raise
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Part issue đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể issue spare part.") from exc

    def get_issue(self, issue_id: UUID) -> StoredRecord | None:
        return self.queries.get_issue(issue_id)

    def consume_issue(
        self,
        issue_id: UUID,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                operation, replay = _claim_operation(
                    session,
                    idempotency_key=idempotency_key,
                    operation_type=InventoryOperationType.CONSUME,
                    request_hash=_request_hash(
                        InventoryOperationType.CONSUME,
                        {"issue_id": issue_id, **values},
                    ),
                    actor_user_id=audit_context.actor_user_id,
                )
                if replay:
                    return _operation_consumption_result(session, operation)
                issue = session.scalar(
                    select(WorkOrderPartIssue)
                    .where(WorkOrderPartIssue.id == issue_id)
                    .with_for_update()
                )
                if issue is None:
                    raise RecordNotFoundError(f"Không tìm thấy part issue: {issue_id}")
                totals = _issue_totals(session, issue.id)
                quantity = _decimal(values["quantity"])
                outstanding = (
                    _decimal(issue.quantity) - totals["consumed"] - totals["returned"]
                )
                if quantity > outstanding:
                    raise IntegrityViolationError(
                        "Consumed quantity vượt quá issued quantity chưa xử lý."
                    )
                consumption = WorkOrderPartConsumption(
                    id=uuid4(),
                    operation_id=operation.id,
                    issue_id=issue.id,
                    work_order_id=issue.work_order_id,
                    part_id=issue.part_id,
                    quantity=quantity,
                    consumed_by_user_id=audit_context.actor_user_id,
                    consumed_at=values["consumed_at"],
                    note=values.get("note"),
                )
                session.add(consumption)
                # Sessions deliberately disable autoflush. Persist the new
                # consumption before deriving the requirement lifecycle state
                # from aggregate issue totals.
                session.flush()
                if issue.requirement_id:
                    requirement = session.get(
                        WorkOrderPartRequirement, issue.requirement_id
                    )
                    if requirement is not None:
                        _sync_requirement_status(
                            session, requirement, audit_context.actor_user_id
                        )
                _complete_operation(
                    operation, "work_order_part_consumption", consumption.id
                )
                session.flush()
                result = _consumption_record(session, consumption)
                _audit(
                    session,
                    audit_context,
                    action="inventory.part_consumed",
                    resource_type="work_order_part_consumption",
                    resource_id=str(consumption.id),
                    after=result.values,
                    fields={
                        "id",
                        "issue_id",
                        "work_order_id",
                        "part_id",
                        "quantity",
                        "consumed_at",
                    },
                )
            return result
        except (
            DuplicateIdentifierError,
            IntegrityViolationError,
            RecordNotFoundError,
        ):
            raise
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Consumption event đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể ghi part consumption.") from exc

    def return_issue(
        self,
        issue_id: UUID,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                operation, replay = _claim_operation(
                    session,
                    idempotency_key=idempotency_key,
                    operation_type=InventoryOperationType.RETURN,
                    request_hash=_request_hash(
                        InventoryOperationType.RETURN,
                        {"issue_id": issue_id, **values},
                    ),
                    actor_user_id=audit_context.actor_user_id,
                )
                if replay:
                    return _operation_return_result(session, operation)
                issue = session.scalar(
                    select(WorkOrderPartIssue)
                    .where(WorkOrderPartIssue.id == issue_id)
                    .with_for_update()
                )
                if issue is None:
                    raise RecordNotFoundError(f"Không tìm thấy part issue: {issue_id}")
                part = _require_part(session, issue.part_id)
                location = _require_active_stock_location(
                    session, values["stock_location_id"]
                )
                totals = _issue_totals(session, issue.id)
                quantity = _decimal(values["quantity"])
                outstanding = (
                    _decimal(issue.quantity) - totals["consumed"] - totals["returned"]
                )
                if quantity > outstanding:
                    raise IntegrityViolationError(
                        "Return quantity vượt quá issued quantity chưa dùng hoặc chưa trả."
                    )
                position = _locked_position(session, part.id, location.id)
                position.on_hand_quantity = (
                    _decimal(position.on_hand_quantity) + quantity
                )
                work_order = _require_work_order(session, issue.work_order_id)
                movement_values = {
                    "quantity": quantity,
                    "business_reference": values.get("business_reference")
                    or f"RETURN-{work_order.work_order_number}",
                    "occurred_at": values["returned_at"],
                    "reason": values["reason"],
                    "work_order_id": issue.work_order_id,
                    "unit_cost_snapshot": part.unit_cost,
                }
                movement = _new_movement(
                    session,
                    operation=operation,
                    part=part,
                    position=position,
                    movement_type=InventoryMovementType.RETURN,
                    values=movement_values,
                    audit_context=audit_context,
                )
                session.flush()
                returned = WorkOrderPartReturn(
                    id=uuid4(),
                    return_number=_next_number(session, RETURN_SEQUENCE, "RET"),
                    operation_id=operation.id,
                    issue_id=issue.id,
                    work_order_id=issue.work_order_id,
                    part_id=issue.part_id,
                    stock_location_id=location.id,
                    quantity=quantity,
                    returned_by_user_id=audit_context.actor_user_id,
                    returned_at=values["returned_at"],
                    reason=values["reason"],
                    movement_id=movement.id,
                )
                session.add(returned)
                # Sessions deliberately disable autoflush. Persist the new
                # return before deriving the requirement lifecycle state from
                # aggregate issue totals.
                session.flush()
                if issue.requirement_id:
                    requirement = session.get(
                        WorkOrderPartRequirement, issue.requirement_id
                    )
                    if requirement is not None:
                        _sync_requirement_status(
                            session, requirement, audit_context.actor_user_id
                        )
                _complete_operation(operation, "work_order_part_return", returned.id)
                session.flush()
                result = _return_record(session, returned)
                _audit(
                    session,
                    audit_context,
                    action="inventory.part_returned",
                    resource_type="work_order_part_return",
                    resource_id=str(returned.id),
                    after=result.values,
                    fields={
                        "id",
                        "issue_id",
                        "work_order_id",
                        "part_id",
                        "stock_location_id",
                        "quantity",
                        "returned_at",
                    },
                    metadata={"movement_id": str(movement.id)},
                )
            return result
        except (
            DuplicateIdentifierError,
            IntegrityViolationError,
            RecordNotFoundError,
        ):
            raise
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Part return đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể return spare part.") from exc

    def get_work_order_state(self, work_order_id: UUID) -> StoredRecord | None:
        return self.queries.get_work_order_state(work_order_id)

    def work_order_parts(self, work_order_id: UUID) -> StoredRecord:
        return self.queries.work_order_parts(work_order_id)

    def inventory_metrics(self) -> StoredRecord:
        return self.queries.inventory_metrics()

    def list_inventory_attachments(
        self, movement_id: UUID, *, include_deleted: bool = False
    ) -> list[StoredRecord]:
        return self.queries.list_inventory_attachments(
            movement_id,
            include_deleted=include_deleted,
        )

    def get_inventory_attachment(
        self, movement_id: UUID, attachment_id: UUID
    ) -> StoredRecord | None:
        return self.queries.get_inventory_attachment(movement_id, attachment_id)

    def create_inventory_attachment(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        return self.attachments.create(values, audit_context=audit_context)

    def delete_inventory_attachment(
        self,
        movement_id: UUID,
        attachment_id: UUID,
        *,
        audit_context: AuditContext,
    ) -> StoredRecord:
        return self.attachments.delete(
            movement_id,
            attachment_id,
            audit_context=audit_context,
        )


def _category_record(entity: PartCategory) -> StoredRecord:
    return StoredRecord(
        {
            "id": str(entity.id),
            "code": entity.code,
            "name_vi": entity.name_vi,
            "name_en": entity.name_en,
            "description": entity.description,
            "is_active": entity.is_active,
            "version": entity.version,
            "created_at": _iso_datetime(entity.created_at),
            "updated_at": _iso_datetime(entity.updated_at),
        },
        version=entity.version,
    )


def _unit_record(entity: UnitOfMeasure) -> StoredRecord:
    return StoredRecord(
        {
            "id": str(entity.id),
            "code": entity.code,
            "name_vi": entity.name_vi,
            "name_en": entity.name_en,
            "symbol": entity.symbol,
            "quantity_precision": entity.quantity_precision,
            "is_active": entity.is_active,
            "version": entity.version,
            "created_at": _iso_datetime(entity.created_at),
            "updated_at": _iso_datetime(entity.updated_at),
        },
        version=entity.version,
    )


def _part_record(session: Session, entity: SparePart) -> StoredRecord:
    category = session.get(PartCategory, entity.category_id)
    unit = session.get(UnitOfMeasure, entity.unit_of_measure_id)
    if category is None or unit is None:
        raise IntegrityViolationError("Spare part tham chiếu reference data không tồn tại.")
    totals = session.execute(
        select(
            func.coalesce(func.sum(InventoryPosition.on_hand_quantity), 0),
            func.coalesce(func.sum(InventoryPosition.reserved_quantity), 0),
        ).where(InventoryPosition.part_id == entity.id)
    ).one()
    on_hand = _decimal(totals[0])
    reserved = _decimal(totals[1])
    available = available_quantity(on_hand, reserved)
    stock_state = derive_stock_state(
        on_hand=on_hand,
        reserved=reserved,
        minimum_stock=_decimal(entity.minimum_stock),
        reorder_point=_decimal(entity.reorder_point),
        maximum_stock=_optional_decimal(entity.maximum_stock),
    )
    values = {
        "id": str(entity.id),
        "part_number": entity.part_number,
        "name_vi": entity.name_vi,
        "name_en": entity.name_en,
        "category_id": str(category.id),
        "category_code": category.code,
        "category_name_vi": category.name_vi,
        "unit_of_measure_id": str(unit.id),
        "unit_code": unit.code,
        "unit_name_vi": unit.name_vi,
        "unit_symbol": unit.symbol,
        "quantity_precision": unit.quantity_precision,
        "manufacturer_reference": entity.manufacturer_reference,
        "compatible_asset_types": list(entity.compatible_asset_types or []),
        "lifecycle_status": entity.lifecycle_status,
        "lifecycle_status_before_archive": entity.lifecycle_status_before_archive,
        "lifecycle_status_display": PART_LIFECYCLE_LABELS[
            PartLifecycleStatus(entity.lifecycle_status)
        ],
        "minimum_stock": _decimal(entity.minimum_stock),
        "reorder_point": _decimal(entity.reorder_point),
        "maximum_stock": _optional_decimal(entity.maximum_stock),
        "unit_cost": _optional_decimal(entity.unit_cost),
        "currency_code": entity.currency_code,
        "total_on_hand_quantity": on_hand,
        "total_reserved_quantity": reserved,
        "total_available_quantity": available,
        "stock_state": stock_state,
        "stock_state_display": STOCK_STATE_LABELS[stock_state],
        "archived_at": _iso_datetime(entity.archived_at),
        "archive_reason": entity.archive_reason,
        "version": entity.version,
        "created_at": _iso_datetime(entity.created_at),
        "updated_at": _iso_datetime(entity.updated_at),
    }
    return StoredRecord(values, version=entity.version)


def _stock_location_record(entity: StockLocation) -> StoredRecord:
    status = StockLocationStatus(entity.lifecycle_status)
    location_type = StockLocationType(entity.location_type)
    return StoredRecord(
        {
            "id": str(entity.id),
            "code": entity.code,
            "name": entity.name,
            "location_type": entity.location_type,
            "location_type_display": STOCK_LOCATION_TYPE_LABELS[location_type],
            "description": entity.description,
            "lifecycle_status": entity.lifecycle_status,
            "lifecycle_status_before_archive": entity.lifecycle_status_before_archive,
            "lifecycle_status_display": STOCK_LOCATION_STATUS_LABELS[status],
            "archived_at": _iso_datetime(entity.archived_at),
            "archive_reason": entity.archive_reason,
            "version": entity.version,
            "created_at": _iso_datetime(entity.created_at),
            "updated_at": _iso_datetime(entity.updated_at),
        },
        version=entity.version,
    )


def _reorder_record(
    session: Session, entity: PartReorderConfiguration
) -> StoredRecord:
    location = session.get(StockLocation, entity.stock_location_id)
    if location is None:
        raise IntegrityViolationError(
            "Reorder configuration tham chiếu stock location không tồn tại."
        )
    return StoredRecord(
        {
            "id": str(entity.id),
            "part_id": str(entity.part_id),
            "stock_location_id": str(entity.stock_location_id),
            "stock_location_code": location.code,
            "stock_location_name": location.name,
            "minimum_stock": _decimal(entity.minimum_stock),
            "reorder_point": _decimal(entity.reorder_point),
            "maximum_stock": _optional_decimal(entity.maximum_stock),
            "version": entity.version,
            "created_at": _iso_datetime(entity.created_at),
            "updated_at": _iso_datetime(entity.updated_at),
        },
        version=entity.version,
    )


def _balance_record(session: Session, entity: InventoryPosition) -> StoredRecord:
    part = session.get(SparePart, entity.part_id)
    location = session.get(StockLocation, entity.stock_location_id)
    if part is None or location is None:
        raise IntegrityViolationError("Inventory position có reference không tồn tại.")
    unit = session.get(UnitOfMeasure, part.unit_of_measure_id)
    if unit is None:
        raise IntegrityViolationError("Đơn vị tính của spare part không tồn tại.")
    configuration = session.scalar(
        select(PartReorderConfiguration).where(
            PartReorderConfiguration.part_id == entity.part_id,
            PartReorderConfiguration.stock_location_id == entity.stock_location_id,
        )
    )
    minimum = _decimal(
        configuration.minimum_stock if configuration else part.minimum_stock
    )
    reorder_point = _decimal(
        configuration.reorder_point if configuration else part.reorder_point
    )
    maximum = _optional_decimal(
        configuration.maximum_stock if configuration else part.maximum_stock
    )
    on_hand = _decimal(entity.on_hand_quantity)
    reserved = _decimal(entity.reserved_quantity)
    available = available_quantity(on_hand, reserved)
    stock_state = derive_stock_state(
        on_hand=on_hand,
        reserved=reserved,
        minimum_stock=minimum,
        reorder_point=reorder_point,
        maximum_stock=maximum,
    )
    return StoredRecord(
        {
            "id": str(entity.id),
            "part_id": str(part.id),
            "part_number": part.part_number,
            "part_name_vi": part.name_vi,
            "lifecycle_status": part.lifecycle_status,
            "stock_location_id": str(location.id),
            "stock_location_code": location.code,
            "stock_location_name": location.name,
            "stock_location_status": location.lifecycle_status,
            "unit_of_measure_id": str(unit.id),
            "unit_code": unit.code,
            "unit_symbol": unit.symbol,
            "on_hand_quantity": on_hand,
            "reserved_quantity": reserved,
            "available_quantity": available,
            "minimum_stock": minimum,
            "reorder_point": reorder_point,
            "maximum_stock": maximum,
            "stock_state": stock_state,
            "stock_state_display": STOCK_STATE_LABELS[stock_state],
            "suggested_reorder_quantity": reorder_suggestion(
                available=available,
                reorder_point=reorder_point,
                maximum_stock=maximum,
            ),
            "version": entity.version,
            "updated_at": _iso_datetime(entity.updated_at),
        },
        version=entity.version,
    )


def _movement_record(session: Session, entity: InventoryMovement) -> StoredRecord:
    part = session.get(SparePart, entity.part_id)
    location = session.get(StockLocation, entity.stock_location_id)
    unit = session.get(UnitOfMeasure, entity.unit_of_measure_id)
    actor = session.get(User, entity.actor_user_id)
    work_order = (
        session.get(WorkOrder, entity.work_order_id) if entity.work_order_id else None
    )
    source = (
        session.get(StockLocation, entity.source_location_id)
        if entity.source_location_id
        else None
    )
    destination = (
        session.get(StockLocation, entity.destination_location_id)
        if entity.destination_location_id
        else None
    )
    if part is None or location is None or unit is None or actor is None:
        raise IntegrityViolationError("Stock movement có reference không tồn tại.")
    movement_type = InventoryMovementType(entity.movement_type)
    resulting_on_hand = _decimal(entity.resulting_on_hand_quantity)
    resulting_reserved = _decimal(entity.resulting_reserved_quantity)
    return StoredRecord(
        {
            "id": str(entity.id),
            "movement_number": entity.movement_number,
            "part_id": str(part.id),
            "part_number": part.part_number,
            "part_name_vi": part.name_vi,
            "stock_location_id": str(location.id),
            "stock_location_code": location.code,
            "stock_location_name": location.name,
            "quantity": _decimal(entity.quantity),
            "unit_of_measure_id": str(unit.id),
            "unit_code": unit.code,
            "unit_symbol": unit.symbol,
            "movement_type": entity.movement_type,
            "movement_type_display": MOVEMENT_TYPE_LABELS[movement_type],
            "business_reference": entity.business_reference,
            "actor_user_id": str(actor.id),
            "actor_display_name": actor.display_name,
            "occurred_at": _iso_datetime(entity.occurred_at),
            "reason": entity.reason,
            "work_order_id": _uuid_text(entity.work_order_id),
            "work_order_number": work_order.work_order_number if work_order else None,
            "source_location_id": _uuid_text(entity.source_location_id),
            "source_location_code": source.code if source else None,
            "destination_location_id": _uuid_text(entity.destination_location_id),
            "destination_location_code": destination.code if destination else None,
            "transfer_group_id": _uuid_text(entity.transfer_group_id),
            "unit_cost_snapshot": _optional_decimal(entity.unit_cost_snapshot),
            "resulting_on_hand_quantity": resulting_on_hand,
            "resulting_reserved_quantity": resulting_reserved,
            "resulting_available_quantity": available_quantity(
                resulting_on_hand, resulting_reserved
            ),
            "idempotency_key": entity.idempotency_key,
            "created_at": _iso_datetime(entity.created_at),
        }
    )


def _requirement_record(
    session: Session, entity: WorkOrderPartRequirement
) -> StoredRecord:
    work_order = session.get(WorkOrder, entity.work_order_id)
    part = session.get(SparePart, entity.part_id)
    location = session.get(StockLocation, entity.source_stock_location_id)
    if work_order is None or part is None or location is None:
        raise IntegrityViolationError("Part requirement có reference không tồn tại.")
    unit = session.get(UnitOfMeasure, part.unit_of_measure_id)
    if unit is None:
        raise IntegrityViolationError("Đơn vị tính của spare part không tồn tại.")
    totals = _requirement_totals(session, entity.id)
    planned = _decimal(entity.planned_quantity)
    covered = totals["reserved"] + totals["outstanding_issued"] + totals["consumed"]
    shortage = max(planned - covered, ZERO)
    status = _derived_requirement_status(entity, totals)
    return StoredRecord(
        {
            "id": str(entity.id),
            "work_order_id": str(work_order.id),
            "work_order_number": work_order.work_order_number,
            "part_id": str(part.id),
            "part_number": part.part_number,
            "part_name_vi": part.name_vi,
            "unit_code": unit.code,
            "unit_symbol": unit.symbol,
            "planned_quantity": planned,
            "required_by_date": _iso_date(entity.required_by_date),
            "source_stock_location_id": str(location.id),
            "source_stock_location_code": location.code,
            "source_stock_location_name": location.name,
            "status": status.value,
            "status_display": REQUIREMENT_STATUS_LABELS[status],
            "notes": entity.notes,
            "reserved_quantity": totals["reserved"],
            "issued_quantity": totals["issued"],
            "returned_quantity": totals["returned"],
            "consumed_quantity": totals["consumed"],
            "outstanding_issued_quantity": totals["outstanding_issued"],
            "shortage_quantity": shortage,
            "version": entity.version,
            "created_at": _iso_datetime(entity.created_at),
            "updated_at": _iso_datetime(entity.updated_at),
        },
        version=entity.version,
    )


def _reservation_record(session: Session, entity: StockReservation) -> StoredRecord:
    requirement = session.get(WorkOrderPartRequirement, entity.requirement_id)
    work_order = session.get(WorkOrder, entity.work_order_id)
    part = session.get(SparePart, entity.part_id)
    location = session.get(StockLocation, entity.stock_location_id)
    if requirement is None or work_order is None or part is None or location is None:
        raise IntegrityViolationError("Reservation có reference không tồn tại.")
    issued, closed = _reservation_quantities(session, entity.id)
    remaining = max(_decimal(entity.quantity) - issued - closed, ZERO)
    events = session.scalars(
        select(StockReservationEvent)
        .where(StockReservationEvent.reservation_id == entity.id)
        .order_by(StockReservationEvent.occurred_at)
    ).all()
    status = ReservationStatus(entity.status)
    return StoredRecord(
        {
            "id": str(entity.id),
            "reservation_number": entity.reservation_number,
            "requirement_id": str(requirement.id),
            "work_order_id": str(work_order.id),
            "work_order_number": work_order.work_order_number,
            "part_id": str(part.id),
            "part_number": part.part_number,
            "part_name_vi": part.name_vi,
            "stock_location_id": str(location.id),
            "stock_location_code": location.code,
            "stock_location_name": location.name,
            "occurrence_number": entity.occurrence_number,
            "quantity": _decimal(entity.quantity),
            "issued_quantity": issued,
            "remaining_quantity": remaining,
            "status": entity.status,
            "status_display": RESERVATION_STATUS_LABELS[status],
            "expires_at": _iso_datetime(entity.expires_at),
            "replaced_by_reservation_id": _uuid_text(
                entity.replaced_by_reservation_id
            ),
            "version": entity.version,
            "created_at": _iso_datetime(entity.created_at),
            "updated_at": _iso_datetime(entity.updated_at),
            "events": [_reservation_event_record(session, event) for event in events],
        },
        version=entity.version,
    )


def _reservation_event_record(
    session: Session, entity: StockReservationEvent
) -> dict[str, Any]:
    actor = session.get(User, entity.actor_user_id)
    if actor is None:
        raise IntegrityViolationError("Reservation event actor không tồn tại.")
    return {
        "id": str(entity.id),
        "event_type": entity.event_type,
        "quantity": _decimal(entity.quantity),
        "reason": entity.reason,
        "actor_user_id": str(actor.id),
        "actor_display_name": actor.display_name,
        "occurred_at": _iso_datetime(entity.occurred_at),
    }


def _issue_record(session: Session, entity: WorkOrderPartIssue) -> StoredRecord:
    work_order = session.get(WorkOrder, entity.work_order_id)
    part = session.get(SparePart, entity.part_id)
    location = session.get(StockLocation, entity.stock_location_id)
    unit = session.get(UnitOfMeasure, part.unit_of_measure_id) if part else None
    issued_by = session.get(User, entity.issued_by_user_id)
    issued_to = (
        session.get(User, entity.issued_to_user_id) if entity.issued_to_user_id else None
    )
    if (
        work_order is None
        or part is None
        or location is None
        or unit is None
        or issued_by is None
    ):
        raise IntegrityViolationError("Part issue có reference không tồn tại.")
    consumptions = session.scalars(
        select(WorkOrderPartConsumption)
        .where(WorkOrderPartConsumption.issue_id == entity.id)
        .order_by(WorkOrderPartConsumption.consumed_at)
    ).all()
    returns = session.scalars(
        select(WorkOrderPartReturn)
        .where(WorkOrderPartReturn.issue_id == entity.id)
        .order_by(WorkOrderPartReturn.returned_at)
    ).all()
    totals = _issue_totals(session, entity.id)
    outstanding = max(
        _decimal(entity.quantity) - totals["consumed"] - totals["returned"], ZERO
    )
    return StoredRecord(
        {
            "id": str(entity.id),
            "issue_number": entity.issue_number,
            "work_order_id": str(work_order.id),
            "work_order_number": work_order.work_order_number,
            "requirement_id": _uuid_text(entity.requirement_id),
            "reservation_id": _uuid_text(entity.reservation_id),
            "part_id": str(part.id),
            "part_number": part.part_number,
            "part_name_vi": part.name_vi,
            "stock_location_id": str(location.id),
            "stock_location_code": location.code,
            "stock_location_name": location.name,
            "unit_code": unit.code,
            "unit_symbol": unit.symbol,
            "quantity": _decimal(entity.quantity),
            "reserved_quantity_used": _decimal(entity.reserved_quantity_used),
            "consumed_quantity": totals["consumed"],
            "returned_quantity": totals["returned"],
            "outstanding_quantity": outstanding,
            "issued_to_user_id": _uuid_text(entity.issued_to_user_id),
            "issued_to_display_name": issued_to.display_name if issued_to else None,
            "issued_by_user_id": str(issued_by.id),
            "issued_by_display_name": issued_by.display_name,
            "issued_at": _iso_datetime(entity.issued_at),
            "reason": entity.reason,
            "movement_id": str(entity.movement_id),
            "consumptions": [
                _consumption_record(session, item).values for item in consumptions
            ],
            "returns": [_return_record(session, item).values for item in returns],
        }
    )


def _consumption_record(
    session: Session, entity: WorkOrderPartConsumption
) -> StoredRecord:
    actor = session.get(User, entity.consumed_by_user_id)
    if actor is None:
        raise IntegrityViolationError("Consumption actor không tồn tại.")
    return StoredRecord(
        {
            "id": str(entity.id),
            "issue_id": str(entity.issue_id),
            "work_order_id": str(entity.work_order_id),
            "part_id": str(entity.part_id),
            "quantity": _decimal(entity.quantity),
            "consumed_by_user_id": str(actor.id),
            "consumed_by_display_name": actor.display_name,
            "consumed_at": _iso_datetime(entity.consumed_at),
            "note": entity.note,
        }
    )


def _return_record(session: Session, entity: WorkOrderPartReturn) -> StoredRecord:
    actor = session.get(User, entity.returned_by_user_id)
    part = session.get(SparePart, entity.part_id)
    location = session.get(StockLocation, entity.stock_location_id)
    if actor is None or part is None or location is None:
        raise IntegrityViolationError("Part return có reference không tồn tại.")
    return StoredRecord(
        {
            "id": str(entity.id),
            "return_number": entity.return_number,
            "issue_id": str(entity.issue_id),
            "work_order_id": str(entity.work_order_id),
            "part_id": str(part.id),
            "part_number": part.part_number,
            "stock_location_id": str(location.id),
            "stock_location_code": location.code,
            "quantity": _decimal(entity.quantity),
            "returned_by_user_id": str(actor.id),
            "returned_by_display_name": actor.display_name,
            "returned_at": _iso_datetime(entity.returned_at),
            "reason": entity.reason,
            "movement_id": str(entity.movement_id),
        }
    )


def _work_order_state_record(entity: WorkOrder) -> StoredRecord:
    return StoredRecord(
        {
            "id": str(entity.id),
            "work_order_number": entity.work_order_number,
            "asset_id": entity.asset_id,
            "status": entity.status,
            "assigned_to_user_id": _uuid_text(entity.assigned_to_user_id),
            "due_date": _iso_date(entity.due_date),
            "version": entity.version,
        },
        version=entity.version,
    )


def _inventory_attachment_record(
    entity: InventoryAttachment, *, include_storage_key: bool = False
) -> StoredRecord:
    values: dict[str, Any] = {
        "id": str(entity.id),
        "movement_id": str(entity.movement_id),
        "category": entity.category,
        "original_filename": entity.original_filename,
        "media_type": entity.media_type,
        "size_bytes": entity.size_bytes,
        "checksum": entity.checksum,
        "uploaded_by_user_id": str(entity.uploaded_by_user_id),
        "created_at": _iso_datetime(entity.created_at),
        "deleted_at": _iso_datetime(entity.deleted_at),
    }
    if include_storage_key:
        values["storage_key"] = entity.storage_key
    return StoredRecord(values)


def _claim_operation(
    session: Session,
    *,
    idempotency_key: str,
    operation_type: InventoryOperationType,
    request_hash: str,
    actor_user_id: UUID,
) -> tuple[InventoryOperation, bool]:
    operation_id = uuid4()
    inserted_id = session.scalar(
        pg_insert(InventoryOperation)
        .values(
            id=operation_id,
            idempotency_key=idempotency_key,
            operation_type=operation_type.value,
            request_hash=request_hash,
            actor_user_id=actor_user_id,
        )
        .on_conflict_do_nothing(index_elements=[InventoryOperation.idempotency_key])
        .returning(InventoryOperation.id)
    )
    if inserted_id is not None:
        entity = session.get(InventoryOperation, inserted_id)
        if entity is None:  # pragma: no cover - returned insert is visible in transaction
            raise RepositoryError("Không thể khởi tạo inventory operation.")
        return entity, False
    existing = session.scalar(
        select(InventoryOperation).where(
            InventoryOperation.idempotency_key == idempotency_key
        )
    )
    if existing is None:  # pragma: no cover - unique conflict always has a row
        raise RepositoryError("Không thể đọc inventory operation idempotent.")
    if existing.operation_type != operation_type.value:
        raise DuplicateIdentifierError(
            "Idempotency-Key đã được dùng cho loại inventory operation khác."
        )
    if existing.request_hash != request_hash:
        raise DuplicateIdentifierError(
            "Idempotency-Key đã được dùng với payload inventory khác."
        )
    if not existing.result_type or not existing.result_id:
        raise RepositoryError(
            "Inventory operation chưa có kết quả hoàn chỉnh; hãy kiểm tra lại giao dịch."
        )
    return existing, True


def _complete_operation(
    operation: InventoryOperation, result_type: str, result_id: UUID
) -> None:
    operation.result_type = result_type
    operation.result_id = str(result_id)


def _operation_movement_result(
    session: Session, operation: InventoryOperation
) -> StoredRecord:
    if operation.result_type != "inventory_movement":
        raise DuplicateIdentifierError("Idempotency-Key không thuộc stock movement này.")
    entity = session.get(InventoryMovement, UUID(str(operation.result_id)))
    if entity is None:
        raise IntegrityViolationError("Kết quả idempotent stock movement không tồn tại.")
    return _movement_record(session, entity)


def _operation_transfer_result(
    session: Session, operation: InventoryOperation
) -> dict[str, StoredRecord | UUID]:
    if operation.result_type != "inventory_transfer":
        raise DuplicateIdentifierError("Idempotency-Key không thuộc stock transfer này.")
    transfer_group_id = UUID(str(operation.result_id))
    entities = session.scalars(
        select(InventoryMovement).where(
            InventoryMovement.transfer_group_id == transfer_group_id
        )
    ).all()
    by_type = {entity.movement_type: entity for entity in entities}
    if {
        InventoryMovementType.TRANSFER_OUT,
        InventoryMovementType.TRANSFER_IN,
    } - set(by_type):
        raise IntegrityViolationError("Stock transfer idempotent không đủ hai movement.")
    return {
        "transfer_group_id": transfer_group_id,
        "transfer_out": _movement_record(
            session, by_type[InventoryMovementType.TRANSFER_OUT]
        ),
        "transfer_in": _movement_record(
            session, by_type[InventoryMovementType.TRANSFER_IN]
        ),
    }


def _operation_reservation_result(
    session: Session, operation: InventoryOperation
) -> StoredRecord:
    if operation.result_type != "stock_reservation":
        raise DuplicateIdentifierError("Idempotency-Key không thuộc reservation này.")
    entity = session.get(StockReservation, UUID(str(operation.result_id)))
    if entity is None:
        raise IntegrityViolationError("Kết quả idempotent reservation không tồn tại.")
    return _reservation_record(session, entity)


def _operation_issue_result(
    session: Session, operation: InventoryOperation
) -> StoredRecord:
    if operation.result_type != "work_order_part_issue":
        raise DuplicateIdentifierError("Idempotency-Key không thuộc part issue này.")
    entity = session.get(WorkOrderPartIssue, UUID(str(operation.result_id)))
    if entity is None:
        raise IntegrityViolationError("Kết quả idempotent part issue không tồn tại.")
    return _issue_record(session, entity)


def _operation_consumption_result(
    session: Session, operation: InventoryOperation
) -> StoredRecord:
    if operation.result_type != "work_order_part_consumption":
        raise DuplicateIdentifierError("Idempotency-Key không thuộc consumption này.")
    entity = session.get(WorkOrderPartConsumption, UUID(str(operation.result_id)))
    if entity is None:
        raise IntegrityViolationError("Kết quả idempotent consumption không tồn tại.")
    return _consumption_record(session, entity)


def _operation_return_result(
    session: Session, operation: InventoryOperation
) -> StoredRecord:
    if operation.result_type != "work_order_part_return":
        raise DuplicateIdentifierError("Idempotency-Key không thuộc part return này.")
    entity = session.get(WorkOrderPartReturn, UUID(str(operation.result_id)))
    if entity is None:
        raise IntegrityViolationError("Kết quả idempotent part return không tồn tại.")
    return _return_record(session, entity)


def _new_movement(
    session: Session,
    *,
    operation: InventoryOperation,
    part: SparePart,
    position: InventoryPosition,
    movement_type: InventoryMovementType,
    values: dict[str, Any],
    audit_context: AuditContext,
) -> InventoryMovement:
    entity = InventoryMovement(
        id=uuid4(),
        movement_number=_next_number(session, MOVEMENT_SEQUENCE, "MOV"),
        operation_id=operation.id,
        part_id=part.id,
        stock_location_id=position.stock_location_id,
        quantity=_decimal(values["quantity"]),
        unit_of_measure_id=part.unit_of_measure_id,
        movement_type=movement_type.value,
        business_reference=values["business_reference"],
        actor_user_id=audit_context.actor_user_id,
        occurred_at=values["occurred_at"],
        reason=values["reason"],
        work_order_id=values.get("work_order_id"),
        source_location_id=values.get("source_location_id"),
        destination_location_id=values.get("destination_location_id"),
        transfer_group_id=values.get("transfer_group_id"),
        unit_cost_snapshot=values.get("unit_cost_snapshot"),
        resulting_on_hand_quantity=_decimal(position.on_hand_quantity),
        resulting_reserved_quantity=_decimal(position.reserved_quantity),
        idempotency_key=operation.idempotency_key,
    )
    session.add(entity)
    return entity


def _reservation_event(
    *,
    reservation_id: UUID,
    operation_id: UUID,
    event_type: str,
    quantity: Decimal,
    reason: str,
    audit_context: AuditContext,
    occurred_at: datetime,
) -> StockReservationEvent:
    return StockReservationEvent(
        id=uuid4(),
        reservation_id=reservation_id,
        operation_id=operation_id,
        event_type=event_type,
        quantity=quantity,
        reason=reason,
        actor_user_id=audit_context.actor_user_id,
        occurred_at=occurred_at,
    )


def _ensure_position(
    session: Session, part_id: UUID, stock_location_id: UUID
) -> None:
    session.execute(
        pg_insert(InventoryPosition)
        .values(
            id=uuid4(),
            part_id=part_id,
            stock_location_id=stock_location_id,
            on_hand_quantity=ZERO,
            reserved_quantity=ZERO,
        )
        .on_conflict_do_nothing(
            index_elements=[
                InventoryPosition.part_id,
                InventoryPosition.stock_location_id,
            ]
        )
    )


def _locked_position(
    session: Session, part_id: UUID, stock_location_id: UUID
) -> InventoryPosition:
    _ensure_position(session, part_id, stock_location_id)
    entity = session.scalar(
        select(InventoryPosition)
        .where(
            InventoryPosition.part_id == part_id,
            InventoryPosition.stock_location_id == stock_location_id,
        )
        .with_for_update()
    )
    if entity is None:  # pragma: no cover - insert/select is transactionally visible
        raise RepositoryError("Không thể khóa inventory position.")
    return entity


def _locked_positions(
    session: Session, part_id: UUID, stock_location_ids: list[UUID]
) -> dict[UUID, InventoryPosition]:
    unique_ids = sorted(set(stock_location_ids), key=str)
    for location_id in unique_ids:
        _ensure_position(session, part_id, location_id)
    entities = session.scalars(
        select(InventoryPosition)
        .where(
            InventoryPosition.part_id == part_id,
            InventoryPosition.stock_location_id.in_(unique_ids),
        )
        .order_by(InventoryPosition.stock_location_id)
        .with_for_update()
    ).all()
    if len(entities) != len(unique_ids):  # pragma: no cover - ensured above
        raise RepositoryError("Không thể khóa đầy đủ inventory positions.")
    return {entity.stock_location_id: entity for entity in entities}


def _requirement_totals(
    session: Session, requirement_id: UUID
) -> dict[str, Decimal]:
    reservations = session.scalars(
        select(StockReservation).where(
            StockReservation.requirement_id == requirement_id,
            StockReservation.status.in_(
                [status.value for status in ACTIVE_RESERVATION_STATUSES]
            ),
        )
    ).all()
    reserved = sum(
        (_reservation_remaining(session, reservation) for reservation in reservations),
        ZERO,
    )
    issues = session.scalars(
        select(WorkOrderPartIssue).where(
            WorkOrderPartIssue.requirement_id == requirement_id
        )
    ).all()
    issued = sum((_decimal(issue.quantity) for issue in issues), ZERO)
    consumed = ZERO
    returned = ZERO
    for issue in issues:
        totals = _issue_totals(session, issue.id)
        consumed += totals["consumed"]
        returned += totals["returned"]
    outstanding = max(issued - consumed - returned, ZERO)
    return {
        "reserved": reserved,
        "issued": issued,
        "consumed": consumed,
        "returned": returned,
        "outstanding_issued": outstanding,
    }


def _sync_requirement_status(
    session: Session,
    requirement: WorkOrderPartRequirement,
    actor_user_id: UUID,
) -> None:
    totals = _requirement_totals(session, requirement.id)
    requirement.status = _derived_requirement_status(requirement, totals).value
    requirement.updated_by_user_id = actor_user_id


def _derived_requirement_status(
    requirement: WorkOrderPartRequirement,
    totals: dict[str, Decimal],
) -> RequirementStatus:
    if requirement.status == RequirementStatus.CANCELLED:
        return RequirementStatus.CANCELLED
    planned = _decimal(requirement.planned_quantity)
    issued_coverage = totals["outstanding_issued"] + totals["consumed"]
    if totals["consumed"] >= planned:
        return RequirementStatus.FULFILLED
    elif totals["consumed"] > ZERO:
        return RequirementStatus.PARTIALLY_CONSUMED
    elif issued_coverage >= planned:
        return RequirementStatus.ISSUED
    elif issued_coverage > ZERO:
        return RequirementStatus.PARTIALLY_ISSUED
    elif totals["reserved"] >= planned:
        return RequirementStatus.RESERVED
    elif totals["reserved"] > ZERO:
        return RequirementStatus.PARTIALLY_RESERVED
    return RequirementStatus.PLANNED


def _reservation_quantities(
    session: Session, reservation_id: UUID
) -> tuple[Decimal, Decimal]:
    issued = _decimal(
        session.scalar(
            select(func.coalesce(func.sum(WorkOrderPartIssue.reserved_quantity_used), 0))
            .where(WorkOrderPartIssue.reservation_id == reservation_id)
        )
    )
    closed = _decimal(
        session.scalar(
            select(func.coalesce(func.sum(StockReservationEvent.quantity), 0)).where(
                StockReservationEvent.reservation_id == reservation_id,
                StockReservationEvent.event_type.in_(
                    ["released", "expired", "replaced"]
                ),
            )
        )
    )
    return issued, closed


def _reservation_remaining(
    session: Session, reservation: StockReservation | None
) -> Decimal:
    if reservation is None:
        return ZERO
    issued, closed = _reservation_quantities(session, reservation.id)
    return max(_decimal(reservation.quantity) - issued - closed, ZERO)


def _issue_totals(session: Session, issue_id: UUID) -> dict[str, Decimal]:
    consumed = _decimal(
        session.scalar(
            select(func.coalesce(func.sum(WorkOrderPartConsumption.quantity), 0))
            .where(WorkOrderPartConsumption.issue_id == issue_id)
        )
    )
    returned = _decimal(
        session.scalar(
            select(func.coalesce(func.sum(WorkOrderPartReturn.quantity), 0)).where(
                WorkOrderPartReturn.issue_id == issue_id
            )
        )
    )
    return {"consumed": consumed, "returned": returned}


def _require_active_reference(
    session: Session,
    model: type[PartCategory] | type[UnitOfMeasure],
    identifier: UUID,
    label: str,
) -> PartCategory | UnitOfMeasure:
    entity = session.get(model, identifier)
    if entity is None:
        raise RecordNotFoundError(f"Không tìm thấy {label}: {identifier}")
    if not entity.is_active:
        raise IntegrityViolationError(f"{label.capitalize()} không còn active.")
    return entity


def _require_part(session: Session, part_id: UUID) -> SparePart:
    entity = session.get(SparePart, part_id)
    if entity is None:
        raise RecordNotFoundError(f"Không tìm thấy spare part: {part_id}")
    return entity


def _require_active_part(session: Session, part_id: UUID) -> SparePart:
    entity = _require_part(session, part_id)
    if entity.lifecycle_status != PartLifecycleStatus.ACTIVE:
        raise IntegrityViolationError(
            "Spare part phải active để thực hiện inventory action."
        )
    return entity


def _require_stock_location(
    session: Session, location_id: UUID
) -> StockLocation:
    entity = session.get(StockLocation, location_id)
    if entity is None:
        raise RecordNotFoundError(f"Không tìm thấy stock location: {location_id}")
    return entity


def _require_active_stock_location(
    session: Session, location_id: UUID
) -> StockLocation:
    entity = _require_stock_location(session, location_id)
    if entity.lifecycle_status != StockLocationStatus.ACTIVE:
        raise IntegrityViolationError(
            "Stock location phải active để thực hiện inventory action."
        )
    return entity


def _require_active_user(session: Session, user_id: UUID) -> User:
    entity = session.get(User, user_id)
    if entity is None:
        raise RecordNotFoundError(f"Không tìm thấy user: {user_id}")
    if not entity.is_active:
        raise IntegrityViolationError("User nhận vật tư không còn active.")
    return entity


def _require_work_order(session: Session, work_order_id: UUID) -> WorkOrder:
    entity = session.get(WorkOrder, work_order_id)
    if entity is None:
        raise RecordNotFoundError(f"Không tìm thấy work order: {work_order_id}")
    return entity


def _part_sort_key(values: dict[str, Any], sort_by: str) -> Any:
    if sort_by == "name_vi":
        return str(values["name_vi"]).casefold()
    if sort_by == "available_quantity":
        return _decimal(values["total_available_quantity"])
    if sort_by == "stock_state":
        order = {
            "out_of_stock": 0,
            "low_stock": 1,
            "at_reorder_point": 2,
            "healthy": 3,
            "overstock": 4,
        }
        return order[str(values["stock_state"])]
    return str(values["part_number"]).casefold()


def _balance_sort_key(values: dict[str, Any], sort_by: str) -> Any:
    if sort_by in {"on_hand_quantity", "reserved_quantity", "available_quantity"}:
        return _decimal(values[sort_by])
    if sort_by == "stock_state":
        order = {
            "out_of_stock": 0,
            "low_stock": 1,
            "at_reorder_point": 2,
            "healthy": 3,
            "overstock": 4,
        }
        return order[str(values["stock_state"])]
    if sort_by == "stock_location":
        return str(values["stock_location_code"]).casefold()
    return str(values["part_number"]).casefold()


def _request_hash(
    operation_type: InventoryOperationType, values: dict[str, Any]
) -> str:
    # Event timestamps default to the server clock. Excluding them keeps an
    # otherwise identical retry stable while the first committed timestamp wins.
    fingerprint_values = {
        key: value
        for key, value in values.items()
        if key not in {"occurred_at", "issued_at", "consumed_at", "returned_at"}
    }
    payload = json.dumps(
        {"operation_type": operation_type.value, "values": fingerprint_values},
        default=_json_fingerprint_value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_fingerprint_value(value: Any) -> str:
    if isinstance(value, datetime):
        return _iso_datetime(value) or ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _next_number(session: Session, sequence: str, prefix: str) -> str:
    number = session.scalar(text(f"SELECT nextval('{sequence}')"))
    if number is None:  # pragma: no cover - PostgreSQL nextval always returns a value
        raise RepositoryError(f"Không thể sinh {prefix} number.")
    return f"{prefix}-{int(number):06d}"


def _audit(
    session: Session,
    context: AuditContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    fields: set[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    append_audit_event(
        session,
        actor_user_id=context.actor_user_id,
        actor_display_name=context.actor_display_name,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=context.request_id,
        before_state=safe_state(before or {}, fields or set()) or None,
        after_state=safe_state(after or {}, fields or set()) or None,
        metadata=metadata,
    )


def _require_version(current: int, expected: int, identifier: str) -> None:
    if current != expected:
        raise StaleRecordError(
            f"Dữ liệu {identifier} đã thay đổi. Hãy tải lại trước khi cập nhật."
        )


def _raise_integrity(exc: IntegrityError, *, duplicate_message: str) -> None:
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if sqlstate == "23505":
        raise DuplicateIdentifierError(duplicate_message) from exc
    if sqlstate == "23514":
        raise IntegrityViolationError(
            "Inventory operation vi phạm quantity hoặc lifecycle constraint."
        ) from exc
    if sqlstate == "23503":
        raise IntegrityViolationError(
            "Inventory operation tham chiếu resource không tồn tại."
        ) from exc
    raise IntegrityViolationError(
        "Inventory operation vi phạm ràng buộc toàn vẹn PostgreSQL."
    ) from exc


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else _decimal(value)


def _iso_date(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _uuid_text(value: UUID | None) -> str | None:
    return str(value) if value else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
