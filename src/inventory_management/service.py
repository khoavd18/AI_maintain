"""Business service for spare-parts inventory and work-order stock control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
import re
from typing import Any
from uuid import UUID

from src.asset_management.storage import (
    AttachmentStorage,
    AttachmentStorageError,
    LocalAttachmentStorage,
    validate_attachment,
)
from src.config.settings import get_settings
from src.config.value_mappings import ASSET_TYPE_CODE_TO_VI
from src.database.session import get_session_factory
from src.inventory_management.domain import (
    INVENTORY_ATTACHMENT_CATEGORIES,
    ISSUABLE_WORK_ORDER_STATUSES,
    MOVEMENT_TYPE_LABELS,
    PART_LIFECYCLE_LABELS,
    REQUIREMENT_EDITABLE_WORK_ORDER_STATUSES,
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
)
from src.repositories.contracts import (
    InventoryRepository,
    StoredPage,
    StoredRecord,
    UnsupportedStorageOperationError,
)
from src.repositories.postgres_inventory import PostgresInventoryRepository
from src.security.audit import AuditContext
from src.security.permissions import Permission, Role
from src.security.service import CurrentUser

_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")
_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,99}$")


class InventoryDomainError(ValueError):
    """Raised when an inventory request violates the public domain contract."""


class InventoryNotFoundError(InventoryDomainError):
    """Raised when an inventory resource does not exist."""


class InventoryConflictError(InventoryDomainError):
    """Raised when lifecycle, stock, or relationship state rejects an action."""


class InventoryAuthorizationError(InventoryDomainError):
    """Raised when resource-level access is not allowed."""


@dataclass(frozen=True)
class InventoryEvidenceDownload:
    filename: str
    media_type: str
    content: bytes


class InventoryManagementService:
    """Canonical named inventory operations with human-controlled workflows."""

    def __init__(
        self,
        repository: InventoryRepository | None,
        attachment_storage: AttachmentStorage,
        *,
        attachment_max_size_bytes: int,
    ) -> None:
        self.repository = repository
        self.attachment_storage = attachment_storage
        self.attachment_max_size_bytes = attachment_max_size_bytes

    def options(self, *, actor: CurrentUser) -> dict[str, Any]:
        self._require_any_read(actor)
        return {
            "part_lifecycle_statuses": _options(PART_LIFECYCLE_LABELS),
            "stock_location_statuses": _options(STOCK_LOCATION_STATUS_LABELS),
            "stock_location_types": _options(STOCK_LOCATION_TYPE_LABELS),
            "movement_types": _options(MOVEMENT_TYPE_LABELS),
            "requirement_statuses": _options(REQUIREMENT_STATUS_LABELS),
            "reservation_statuses": _options(RESERVATION_STATUS_LABELS),
            "stock_states": _options(STOCK_STATE_LABELS),
            "attachment_categories": [
                {"code": code, "display_name": label}
                for code, label in INVENTORY_ATTACHMENT_CATEGORIES.items()
            ],
            "compatible_asset_types": [
                {"code": code, "display_name": display_name}
                for code, display_name in ASSET_TYPE_CODE_TO_VI.items()
            ],
        }

    def list_categories(
        self, *, actor: CurrentUser, include_inactive: bool
    ) -> list[dict[str, Any]]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        return [
            dict(record.values)
            for record in self._repository().list_categories(
                include_inactive=include_inactive
            )
        ]

    def create_category(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_PARTS_MANAGE)
        values = {
            "code": _normalized_code(request["code"], "code", maximum=50),
            "name_vi": _plain_text(request["name_vi"], "name_vi", maximum=200),
            "name_en": _optional_text(request.get("name_en"), maximum=200),
            "description": _optional_text(
                request.get("description"), maximum=1000
            ),
            "is_active": True,
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
        }
        return dict(
            self._repository()
            .create_category(values, audit_context=audit_context)
            .values
        )

    def list_units(
        self, *, actor: CurrentUser, include_inactive: bool
    ) -> list[dict[str, Any]]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        return [
            dict(record.values)
            for record in self._repository().list_units(
                include_inactive=include_inactive
            )
        ]

    def create_unit(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_PARTS_MANAGE)
        precision = int(request["quantity_precision"])
        if precision < 0 or precision > 3:
            raise InventoryDomainError(
                "quantity_precision phải nằm trong khoảng 0 đến 3."
            )
        values = {
            "code": _normalized_code(request["code"], "code", maximum=20),
            "name_vi": _plain_text(request["name_vi"], "name_vi", maximum=120),
            "name_en": _optional_text(request.get("name_en"), maximum=120),
            "symbol": _plain_text(request["symbol"], "symbol", maximum=20),
            "quantity_precision": precision,
            "is_active": True,
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
        }
        return dict(
            self._repository().create_unit(values, audit_context=audit_context).values
        )

    def list_parts(
        self,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        sort_by: str,
        sort_direction: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        if sort_by not in {
            "part_number",
            "name_vi",
            "available_quantity",
            "stock_state",
        }:
            raise InventoryDomainError("Trường sắp xếp spare part không hợp lệ.")
        if sort_direction not in {"asc", "desc"}:
            raise InventoryDomainError("sort_direction chỉ hỗ trợ asc hoặc desc.")
        result = _page_values(
            self._repository().list_parts(
                filters=filters,
                sort_by=sort_by,
                sort_direction=sort_direction,
                page=page,
                page_size=page_size,
            )
        )
        result["items"] = [
            self._scope_part(item, actor) for item in result["items"]
        ]
        return result

    def get_part(self, part_id: UUID, *, actor: CurrentUser) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        return self._scope_part(dict(self._part_record(part_id).values), actor)

    def create_part(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_PARTS_MANAGE)
        minimum, reorder, maximum = _thresholds(request)
        unit_cost, currency = _cost_values(request)
        asset_types = _asset_types(request.get("compatible_asset_types", []))
        values = {
            "part_number": _normalized_code(
                request["part_number"], "part_number", maximum=80
            ),
            "name_vi": _plain_text(request["name_vi"], "name_vi", maximum=200),
            "name_en": _optional_text(request.get("name_en"), maximum=200),
            "category_id": _uuid(request["category_id"], "category_id"),
            "unit_of_measure_id": _uuid(
                request["unit_of_measure_id"], "unit_of_measure_id"
            ),
            "manufacturer_reference": _optional_text(
                request.get("manufacturer_reference"), maximum=200
            ),
            "compatible_asset_types": asset_types,
            "lifecycle_status": PartLifecycleStatus.ACTIVE,
            "lifecycle_status_before_archive": None,
            "minimum_stock": minimum,
            "reorder_point": reorder,
            "maximum_stock": maximum,
            "unit_cost": unit_cost,
            "currency_code": currency,
            "archived_at": None,
            "archive_reason": None,
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
        }
        result = self._repository().create_part(
            values, audit_context=audit_context
        )
        return dict(result.values)

    def update_part(
        self,
        part_id: UUID,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_PARTS_MANAGE)
        current = dict(self._part_record(part_id).values)
        if current["lifecycle_status"] == PartLifecycleStatus.ARCHIVED:
            raise InventoryConflictError(
                "Hãy restore spare part trước khi cập nhật master data."
            )
        updates: dict[str, Any] = {}
        if request.get("name_vi") is not None:
            updates["name_vi"] = _plain_text(
                request["name_vi"], "name_vi", maximum=200
            )
        for field, maximum in (
            ("name_en", 200),
            ("manufacturer_reference", 200),
        ):
            if field in request:
                updates[field] = _optional_text(request.get(field), maximum=maximum)
        if request.get("category_id") is not None:
            updates["category_id"] = _uuid(request["category_id"], "category_id")
        if request.get("compatible_asset_types") is not None:
            updates["compatible_asset_types"] = _asset_types(
                request["compatible_asset_types"]
            )
        if "unit_cost" in request or "currency_code" in request:
            cost_request = {
                "unit_cost": request.get("unit_cost"),
                "currency_code": request.get("currency_code"),
            }
            updates["unit_cost"], updates["currency_code"] = _cost_values(
                cost_request
            )
        if not updates:
            raise InventoryDomainError("Không có field spare part nào để cập nhật.")
        return dict(
            self._repository()
            .update_part(
                part_id,
                updates,
                expected_version=int(request["expected_version"]),
                audit_action="inventory.part_updated",
                audit_context=audit_context,
            )
            .values
        )

    def change_part_lifecycle(
        self,
        part_id: UUID,
        *,
        action: str,
        expected_version: int,
        reason: str | None,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_PARTS_MANAGE)
        current = dict(self._part_record(part_id).values)
        current_status = PartLifecycleStatus(current["lifecycle_status"])
        now = _utc_now()
        if action == "activate":
            if current_status is not PartLifecycleStatus.INACTIVE:
                raise InventoryConflictError(
                    "Chỉ spare part inactive mới có thể activate."
                )
            updates = {"lifecycle_status": PartLifecycleStatus.ACTIVE}
        elif action == "deactivate":
            if current_status is not PartLifecycleStatus.ACTIVE:
                raise InventoryConflictError(
                    "Chỉ spare part active mới có thể deactivate."
                )
            updates = {"lifecycle_status": PartLifecycleStatus.INACTIVE}
        elif action == "archive":
            if current_status is PartLifecycleStatus.ARCHIVED:
                raise InventoryConflictError("Spare part đã được archive.")
            archive_reason = _plain_text(
                reason, "archive_reason", minimum=3, maximum=1000
            )
            updates = {
                "lifecycle_status": PartLifecycleStatus.ARCHIVED,
                "lifecycle_status_before_archive": current_status.value,
                "archived_at": now,
                "archive_reason": archive_reason,
            }
        elif action == "restore":
            if current_status is not PartLifecycleStatus.ARCHIVED:
                raise InventoryConflictError(
                    "Chỉ spare part archived mới có thể restore."
                )
            restore_status = current.get("lifecycle_status_before_archive") or "inactive"
            updates = {
                "lifecycle_status": restore_status,
                "lifecycle_status_before_archive": None,
                "archived_at": None,
                "archive_reason": None,
            }
        else:
            raise InventoryDomainError("Inventory lifecycle action không hợp lệ.")
        return dict(
            self._repository()
            .update_part(
                part_id,
                updates,
                expected_version=expected_version,
                audit_action=f"inventory.part_{action}d",
                audit_context=audit_context,
            )
            .values
        )

    def list_stock_locations(
        self, *, actor: CurrentUser, include_archived: bool
    ) -> list[dict[str, Any]]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        return [
            dict(record.values)
            for record in self._repository().list_stock_locations(
                include_archived=include_archived
            )
        ]

    def create_stock_location(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_LOCATIONS_MANAGE)
        values = {
            "code": _normalized_code(request["code"], "code", maximum=50),
            "name": _plain_text(request["name"], "name", maximum=200),
            "location_type": request["location_type"],
            "description": _optional_text(
                request.get("description"), maximum=1000
            ),
            "lifecycle_status": StockLocationStatus.ACTIVE,
            "lifecycle_status_before_archive": None,
            "archived_at": None,
            "archive_reason": None,
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
        }
        return dict(
            self._repository()
            .create_stock_location(values, audit_context=audit_context)
            .values
        )

    def update_stock_location(
        self,
        location_id: UUID,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_LOCATIONS_MANAGE)
        current = dict(self._stock_location_record(location_id).values)
        if current["lifecycle_status"] == StockLocationStatus.ARCHIVED:
            raise InventoryConflictError(
                "Hãy restore stock location trước khi cập nhật."
            )
        updates: dict[str, Any] = {}
        if request.get("name") is not None:
            updates["name"] = _plain_text(
                request["name"], "name", maximum=200
            )
        if request.get("location_type") is not None:
            updates["location_type"] = request["location_type"]
        if "description" in request:
            updates["description"] = _optional_text(
                request.get("description"), maximum=1000
            )
        if not updates:
            raise InventoryDomainError("Không có field stock location để cập nhật.")
        return dict(
            self._repository()
            .update_stock_location(
                location_id,
                updates,
                expected_version=int(request["expected_version"]),
                audit_action="inventory.stock_location_updated",
                audit_context=audit_context,
            )
            .values
        )

    def change_stock_location_lifecycle(
        self,
        location_id: UUID,
        *,
        action: str,
        expected_version: int,
        reason: str | None,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_LOCATIONS_MANAGE)
        current = dict(self._stock_location_record(location_id).values)
        current_status = StockLocationStatus(current["lifecycle_status"])
        now = _utc_now()
        if action == "activate":
            if current_status is not StockLocationStatus.INACTIVE:
                raise InventoryConflictError(
                    "Chỉ stock location inactive mới có thể activate."
                )
            updates = {"lifecycle_status": StockLocationStatus.ACTIVE}
        elif action == "deactivate":
            if current_status is not StockLocationStatus.ACTIVE:
                raise InventoryConflictError(
                    "Chỉ stock location active mới có thể deactivate."
                )
            updates = {"lifecycle_status": StockLocationStatus.INACTIVE}
        elif action == "archive":
            if current_status is StockLocationStatus.ARCHIVED:
                raise InventoryConflictError("Stock location đã được archive.")
            updates = {
                "lifecycle_status": StockLocationStatus.ARCHIVED,
                "lifecycle_status_before_archive": current_status.value,
                "archived_at": now,
                "archive_reason": _plain_text(
                    reason, "archive_reason", minimum=3, maximum=1000
                ),
            }
        elif action == "restore":
            if current_status is not StockLocationStatus.ARCHIVED:
                raise InventoryConflictError(
                    "Chỉ stock location archived mới có thể restore."
                )
            updates = {
                "lifecycle_status": current.get(
                    "lifecycle_status_before_archive"
                )
                or "inactive",
                "lifecycle_status_before_archive": None,
                "archived_at": None,
                "archive_reason": None,
            }
        else:
            raise InventoryDomainError("Stock-location lifecycle action không hợp lệ.")
        return dict(
            self._repository()
            .update_stock_location(
                location_id,
                updates,
                expected_version=expected_version,
                audit_action=f"inventory.stock_location_{action}d",
                audit_context=audit_context,
            )
            .values
        )

    def upsert_reorder_configuration(
        self,
        part_id: UUID,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_PARTS_MANAGE)
        self._part_record(part_id)
        minimum, reorder, maximum = _thresholds(request)
        values = {
            "part_id": part_id,
            "stock_location_id": _uuid(
                request["stock_location_id"], "stock_location_id"
            ),
            "minimum_stock": minimum,
            "reorder_point": reorder,
            "maximum_stock": maximum,
        }
        return dict(
            self._repository()
            .upsert_reorder_configuration(
                values,
                expected_version=request.get("expected_version"),
                audit_context=audit_context,
            )
            .values
        )

    def list_balances(
        self,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        sort_by: str,
        sort_direction: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        if sort_by not in {
            "part_number",
            "stock_location",
            "on_hand_quantity",
            "reserved_quantity",
            "available_quantity",
            "stock_state",
        }:
            raise InventoryDomainError("Trường sắp xếp balance không hợp lệ.")
        if sort_direction not in {"asc", "desc"}:
            raise InventoryDomainError("sort_direction chỉ hỗ trợ asc hoặc desc.")
        return _page_values(
            self._repository().list_balances(
                filters=filters,
                sort_by=sort_by,
                sort_direction=sort_direction,
                page=page,
                page_size=page_size,
            )
        )

    def list_movements(
        self,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        return _page_values(
            self._repository().list_movements(
                filters=filters, page=page, page_size=page_size
            )
        )

    def create_opening_balance(
        self,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_RECEIVE)
        values = self._stock_operation_values(request)
        return dict(
            self._repository()
            .create_opening_balance(
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def receive_stock(
        self,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_RECEIVE)
        values = self._stock_operation_values(request)
        return dict(
            self._repository()
            .receive_stock(
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def transfer_stock(
        self,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_TRANSFER)
        part = dict(self._part_record(_uuid(request["part_id"], "part_id")).values)
        source = _uuid(
            request["source_stock_location_id"], "source_stock_location_id"
        )
        destination = _uuid(
            request["destination_stock_location_id"],
            "destination_stock_location_id",
        )
        if source == destination:
            raise InventoryDomainError("Kho nguồn và kho đích phải khác nhau.")
        values = {
            "part_id": UUID(str(part["id"])),
            "source_stock_location_id": source,
            "destination_stock_location_id": destination,
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "business_reference": _plain_text(
                request["business_reference"],
                "business_reference",
                maximum=160,
            ),
            "occurred_at": _safe_timestamp(
                request.get("occurred_at"), "occurred_at"
            ),
            "reason": _plain_text(
                request["reason"], "reason", minimum=3, maximum=1000
            ),
            "unit_cost_snapshot": part.get("unit_cost"),
        }
        result = self._repository().transfer_stock(
            values,
            idempotency_key=_idempotency_key(idempotency_key),
            audit_context=audit_context,
        )
        return {
            "transfer_group_id": str(result["transfer_group_id"]),
            "transfer_out": dict(result["transfer_out"].values),
            "transfer_in": dict(result["transfer_in"].values),
        }

    def adjust_stock(
        self,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_ADJUST)
        values = self._stock_operation_values(request)
        adjustment_type = request["adjustment_type"]
        mapping = {
            "increase": (
                InventoryOperationType.ADJUSTMENT_INCREASE,
                InventoryMovementType.ADJUSTMENT_INCREASE,
            ),
            "decrease": (
                InventoryOperationType.ADJUSTMENT_DECREASE,
                InventoryMovementType.ADJUSTMENT_DECREASE,
            ),
            "damaged_scrapped": (
                InventoryOperationType.DAMAGED_SCRAPPED,
                InventoryMovementType.DAMAGED_SCRAPPED,
            ),
        }
        try:
            operation_type, movement_type = mapping[adjustment_type]
        except KeyError as exc:
            raise InventoryDomainError("adjustment_type không hợp lệ.") from exc
        values.update(
            {
                "operation_type": operation_type,
                "movement_type": movement_type,
                "supporting_note": _plain_text(
                    request["supporting_note"],
                    "supporting_note",
                    minimum=3,
                    maximum=2000,
                ),
            }
        )
        return dict(
            self._repository()
            .adjust_stock(
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def create_requirement(
        self,
        work_order_id: UUID,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_REQUIREMENTS_MANAGE)
        work_order = self._work_order(work_order_id)
        self._require_work_order_status(
            work_order, REQUIREMENT_EDITABLE_WORK_ORDER_STATUSES, "thêm requirement"
        )
        part = dict(self._part_record(_uuid(request["part_id"], "part_id")).values)
        if part["lifecycle_status"] != PartLifecycleStatus.ACTIVE:
            raise InventoryConflictError(
                "Chỉ spare part active mới được thêm vào requirement."
            )
        values = {
            "work_order_id": work_order_id,
            "part_id": UUID(str(part["id"])),
            "planned_quantity": _quantity(
                request["planned_quantity"], int(part["quantity_precision"])
            ),
            "required_by_date": _optional_date(request.get("required_by_date")),
            "source_stock_location_id": _uuid(
                request["source_stock_location_id"],
                "source_stock_location_id",
            ),
            "status": RequirementStatus.PLANNED,
            "notes": _optional_text(request.get("notes"), maximum=1000),
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
        }
        return dict(
            self._repository()
            .create_requirement(values, audit_context=audit_context)
            .values
        )

    def reserve_stock(
        self,
        requirement_id: UUID,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_RESERVE)
        requirement = self._requirement(requirement_id)
        work_order = self._work_order(UUID(str(requirement["work_order_id"])))
        self._require_work_order_status(
            work_order, REQUIREMENT_EDITABLE_WORK_ORDER_STATUSES, "reserve stock"
        )
        part = dict(self._part_record(UUID(str(requirement["part_id"]))).values)
        expires_at = _optional_future_timestamp(
            request.get("expires_at"), "expires_at"
        )
        values = {
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "expires_at": expires_at,
            "reason": _plain_text(
                request["reason"], "reason", minimum=3, maximum=1000
            ),
            "occurred_at": _utc_now(),
        }
        return dict(
            self._repository()
            .reserve_stock(
                requirement_id,
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                expected_requirement_version=int(
                    request["expected_requirement_version"]
                ),
                audit_context=audit_context,
            )
            .values
        )

    def close_reservation(
        self,
        reservation_id: UUID,
        request: dict[str, Any],
        *,
        target_status: ReservationStatus,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_RESERVE)
        self._reservation(reservation_id)
        return dict(
            self._repository()
            .close_reservation(
                reservation_id,
                target_status=target_status.value,
                reason=_plain_text(
                    request["reason"], "reason", minimum=3, maximum=1000
                ),
                expected_version=int(request["expected_version"]),
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def list_reservations(
        self,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        return _page_values(
            self._repository().list_reservations(
                filters=filters, page=page, page_size=page_size
            )
        )

    def replace_reservation(
        self,
        reservation_id: UUID,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_RESERVE)
        reservation = self._reservation(reservation_id)
        part = dict(self._part_record(UUID(str(reservation["part_id"]))).values)
        values = {
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "stock_location_id": _uuid(
                request["stock_location_id"], "stock_location_id"
            ),
            "expires_at": _optional_future_timestamp(
                request.get("expires_at"), "expires_at"
            ),
            "reason": _plain_text(
                request["reason"], "reason", minimum=3, maximum=1000
            ),
            "occurred_at": _utc_now(),
        }
        return dict(
            self._repository()
            .replace_reservation(
                reservation_id,
                values,
                expected_version=int(request["expected_version"]),
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def issue_stock(
        self,
        work_order_id: UUID,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_ISSUE)
        work_order = self._work_order(work_order_id)
        self._require_work_order_status(
            work_order, ISSUABLE_WORK_ORDER_STATUSES, "issue stock"
        )
        part = dict(self._part_record(_uuid(request["part_id"], "part_id")).values)
        values = {
            "part_id": UUID(str(part["id"])),
            "stock_location_id": _uuid(
                request["stock_location_id"], "stock_location_id"
            ),
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "requirement_id": _optional_uuid(
                request.get("requirement_id"), "requirement_id"
            ),
            "reservation_id": _optional_uuid(
                request.get("reservation_id"), "reservation_id"
            ),
            "issued_to_user_id": _optional_uuid(
                request.get("issued_to_user_id")
                or work_order.get("assigned_to_user_id"),
                "issued_to_user_id",
            ),
            "issued_at": _safe_timestamp(
                request.get("issued_at"), "issued_at"
            ),
            "reason": _plain_text(
                request["reason"], "reason", minimum=3, maximum=1000
            ),
            "business_reference": f"ISSUE-{work_order['work_order_number']}",
        }
        return dict(
            self._repository()
            .issue_stock(
                work_order_id,
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def consume_issue(
        self,
        issue_id: UUID,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_CONSUME)
        issue = self._issue(issue_id)
        work_order = self._work_order(UUID(str(issue["work_order_id"])))
        self._require_work_order_access(work_order, actor)
        if work_order["status"] in {"verified", "cancelled"}:
            raise InventoryConflictError(
                "Không thể ghi consumption cho work order verified hoặc cancelled."
            )
        part = dict(self._part_record(UUID(str(issue["part_id"]))).values)
        values = {
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "consumed_at": _safe_timestamp(
                request.get("consumed_at"), "consumed_at"
            ),
            "note": _optional_text(request.get("note"), maximum=1000),
        }
        return dict(
            self._repository()
            .consume_issue(
                issue_id,
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def return_issue(
        self,
        issue_id: UUID,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_RETURN)
        issue = self._issue(issue_id)
        part = dict(self._part_record(UUID(str(issue["part_id"]))).values)
        values = {
            "stock_location_id": _uuid(
                request["stock_location_id"], "stock_location_id"
            ),
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "returned_at": _safe_timestamp(
                request.get("returned_at"), "returned_at"
            ),
            "reason": _plain_text(
                request["reason"], "reason", minimum=3, maximum=1000
            ),
            "business_reference": f"RETURN-{issue['issue_number']}",
        }
        return dict(
            self._repository()
            .return_issue(
                issue_id,
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def work_order_parts(
        self, work_order_id: UUID, *, actor: CurrentUser
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.WORK_ORDER_PARTS_READ)
        work_order = self._work_order(work_order_id)
        self._require_work_order_access(work_order, actor)
        return dict(self._repository().work_order_parts(work_order_id).values)

    def metrics(self, *, actor: CurrentUser) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        return dict(self._repository().inventory_metrics().values)

    def list_evidence(
        self, movement_id: UUID, *, actor: CurrentUser
    ) -> list[dict[str, Any]]:
        self._require_permission(actor, Permission.INVENTORY_ATTACHMENTS_READ)
        movement = self._movement(movement_id)
        self._require_movement_access(movement, actor)
        return [
            dict(record.values)
            for record in self._repository().list_inventory_attachments(movement_id)
        ]

    def upload_evidence(
        self,
        movement_id: UUID,
        *,
        category: str,
        filename: str,
        claimed_media_type: str | None,
        content: bytes,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_ATTACHMENTS_CREATE)
        movement = self._movement(movement_id)
        self._require_movement_access(movement, actor)
        if category not in INVENTORY_ATTACHMENT_CATEGORIES:
            raise InventoryDomainError("Inventory evidence category không hợp lệ.")
        validated = validate_attachment(
            filename=filename,
            claimed_media_type=claimed_media_type,
            content=content,
            max_size_bytes=self.attachment_max_size_bytes,
        )
        storage_key = self.attachment_storage.save(
            validated, namespace="inventory"
        )
        try:
            record = self._repository().create_inventory_attachment(
                {
                    "movement_id": movement_id,
                    "category": category,
                    "original_filename": validated.original_filename,
                    "storage_key": storage_key,
                    "media_type": validated.media_type,
                    "size_bytes": validated.size_bytes,
                    "checksum": validated.checksum,
                    "uploaded_by_user_id": actor.id,
                    "deleted_at": None,
                    "deleted_by_user_id": None,
                },
                audit_context=audit_context,
            )
        except Exception:
            self.attachment_storage.delete(storage_key)
            raise
        return _public_attachment(record.values)

    def download_evidence(
        self,
        movement_id: UUID,
        attachment_id: UUID,
        *,
        actor: CurrentUser,
    ) -> InventoryEvidenceDownload:
        self._require_permission(actor, Permission.INVENTORY_ATTACHMENTS_READ)
        movement = self._movement(movement_id)
        self._require_movement_access(movement, actor)
        record = self._repository().get_inventory_attachment(
            movement_id, attachment_id
        )
        if record is None or record.values.get("deleted_at"):
            raise InventoryNotFoundError(
                f"Không tìm thấy inventory evidence: {attachment_id}"
            )
        content = self.attachment_storage.read(str(record.values["storage_key"]))
        if hashlib.sha256(content).hexdigest() != record.values["checksum"]:
            raise AttachmentStorageError("Checksum inventory evidence không khớp.")
        return InventoryEvidenceDownload(
            filename=str(record.values["original_filename"]),
            media_type=str(record.values["media_type"]),
            content=content,
        )

    def delete_evidence(
        self,
        movement_id: UUID,
        attachment_id: UUID,
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_ATTACHMENTS_DELETE)
        movement = self._movement(movement_id)
        self._require_movement_access(movement, actor)
        record = self._repository().delete_inventory_attachment(
            movement_id, attachment_id, audit_context=audit_context
        )
        self.attachment_storage.delete(str(record.values["storage_key"]))
        return _public_attachment(record.values)

    def _stock_operation_values(self, request: dict[str, Any]) -> dict[str, Any]:
        part = dict(self._part_record(_uuid(request["part_id"], "part_id")).values)
        return {
            "part_id": UUID(str(part["id"])),
            "stock_location_id": _uuid(
                request["stock_location_id"], "stock_location_id"
            ),
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "business_reference": _plain_text(
                request["business_reference"],
                "business_reference",
                maximum=160,
            ),
            "occurred_at": _safe_timestamp(
                request.get("occurred_at"), "occurred_at"
            ),
            "reason": _plain_text(
                request["reason"], "reason", minimum=3, maximum=1000
            ),
            "unit_cost_snapshot": (
                _optional_decimal(request.get("unit_cost_snapshot"))
                if request.get("unit_cost_snapshot") is not None
                else part.get("unit_cost")
            ),
        }

    def _part_record(self, part_id: UUID) -> StoredRecord:
        record = self._repository().get_part(part_id)
        if record is None:
            raise InventoryNotFoundError(f"Không tìm thấy spare part: {part_id}")
        return record

    def _stock_location_record(self, location_id: UUID) -> StoredRecord:
        record = self._repository().get_stock_location(location_id)
        if record is None:
            raise InventoryNotFoundError(
                f"Không tìm thấy stock location: {location_id}"
            )
        return record

    def _requirement(self, requirement_id: UUID) -> dict[str, Any]:
        record = self._repository().get_requirement(requirement_id)
        if record is None:
            raise InventoryNotFoundError(
                f"Không tìm thấy part requirement: {requirement_id}"
            )
        return dict(record.values)

    def _reservation(self, reservation_id: UUID) -> dict[str, Any]:
        record = self._repository().get_reservation(reservation_id)
        if record is None:
            raise InventoryNotFoundError(
                f"Không tìm thấy stock reservation: {reservation_id}"
            )
        return dict(record.values)

    def _issue(self, issue_id: UUID) -> dict[str, Any]:
        record = self._repository().get_issue(issue_id)
        if record is None:
            raise InventoryNotFoundError(f"Không tìm thấy part issue: {issue_id}")
        return dict(record.values)

    def _work_order(self, work_order_id: UUID) -> dict[str, Any]:
        record = self._repository().get_work_order_state(work_order_id)
        if record is None:
            raise InventoryNotFoundError(f"Không tìm thấy work order: {work_order_id}")
        return dict(record.values)

    def _movement(self, movement_id: UUID) -> dict[str, Any]:
        record = self._repository().get_movement(movement_id)
        if record is None:
            raise InventoryNotFoundError(
                f"Không tìm thấy stock movement: {movement_id}"
            )
        return dict(record.values)

    def _require_work_order_access(
        self, work_order: dict[str, Any], actor: CurrentUser
    ) -> None:
        if actor.role is Role.TECHNICIAN and str(
            work_order.get("assigned_to_user_id") or ""
        ) != str(actor.id):
            raise InventoryAuthorizationError(
                "Kỹ thuật viên chỉ được xem hoặc ghi vật tư cho work order được gán."
            )

    def _require_movement_access(
        self, movement: dict[str, Any], actor: CurrentUser
    ) -> None:
        if actor.role is not Role.TECHNICIAN:
            return
        work_order_id = movement.get("work_order_id")
        if not work_order_id:
            raise InventoryAuthorizationError(
                "Kỹ thuật viên chỉ được xem bằng chứng của vật tư thuộc work order được gán."
            )
        self._require_work_order_access(
            self._work_order(UUID(str(work_order_id))), actor
        )

    @staticmethod
    def _require_work_order_status(
        work_order: dict[str, Any], allowed: frozenset[str], action: str
    ) -> None:
        if work_order["status"] not in allowed:
            raise InventoryConflictError(
                f"Work order ở trạng thái {work_order['status']} không thể {action}."
            )

    @staticmethod
    def _scope_part(values: dict[str, Any], actor: CurrentUser) -> dict[str, Any]:
        result = dict(values)
        if actor.role is Role.HELPDESK:
            result["unit_cost"] = None
            result["currency_code"] = None
        return result

    @staticmethod
    def _require_permission(actor: CurrentUser, permission: Permission) -> None:
        if not actor.has(permission):
            raise InventoryAuthorizationError(
                "Bạn không có quyền thực hiện inventory action này."
            )

    def _require_any_read(self, actor: CurrentUser) -> None:
        if not (
            actor.has(Permission.INVENTORY_READ)
            or actor.has(Permission.WORK_ORDER_PARTS_READ)
        ):
            raise InventoryAuthorizationError(
                "Bạn không có quyền đọc inventory options."
            )

    def _repository(self) -> InventoryRepository:
        if self.repository is None:
            raise UnsupportedStorageOperationError(
                "Inventory management yêu cầu PostgreSQL product mode."
            )
        return self.repository


def build_inventory_management_service() -> InventoryManagementService:
    """Build the canonical inventory service from validated settings."""

    settings = get_settings()
    repository: InventoryRepository | None = None
    if settings.storage_backend == "postgresql":
        repository = PostgresInventoryRepository(
            get_session_factory(settings.database_url)
        )
    return InventoryManagementService(
        repository,
        LocalAttachmentStorage(Path(settings.attachment_storage_root)),
        attachment_max_size_bytes=settings.attachment_max_size_bytes,
    )


def _page_values(page: StoredPage) -> dict[str, Any]:
    return {
        "items": [dict(record.values) for record in page.items],
        "page": page.page,
        "page_size": page.page_size,
        "total": page.total,
        "total_pages": (page.total + page.page_size - 1) // page.page_size,
    }


def _options(mapping: dict[Any, str]) -> list[dict[str, str]]:
    return [
        {"code": str(code), "display_name": display_name}
        for code, display_name in mapping.items()
    ]


def _normalized_code(value: object, field: str, *, maximum: int) -> str:
    normalized = _plain_text(value, field, maximum=maximum).upper()
    if not _CODE_PATTERN.fullmatch(normalized):
        raise InventoryDomainError(
            f"{field} chỉ hỗ trợ chữ in hoa, số, dấu chấm, gạch dưới hoặc gạch ngang."
        )
    return normalized


def _plain_text(
    value: object,
    field: str,
    *,
    maximum: int,
    minimum: int = 1,
) -> str:
    normalized = str(value or "").strip()
    if (
        len(normalized) < minimum
        or len(normalized) > maximum
        or any(ord(character) < 32 and character not in "\n\t" for character in normalized)
    ):
        raise InventoryDomainError(f"{field} không hợp lệ.")
    return normalized


def _optional_text(value: object, *, maximum: int) -> str | None:
    if value is None or not str(value).strip():
        return None
    return _plain_text(value, "text", maximum=maximum)


def _uuid(value: object, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise InventoryDomainError(f"{field} không phải UUID hợp lệ.") from exc


def _optional_uuid(value: object, field: str) -> UUID | None:
    return None if value is None or not str(value).strip() else _uuid(value, field)


def _asset_types(values: object) -> list[str]:
    allowed = set(ASSET_TYPE_CODE_TO_VI)
    result = sorted({str(item) for item in list(values or [])})
    if any(item not in allowed for item in result):
        raise InventoryDomainError("compatible_asset_types có code không hợp lệ.")
    return result


def _thresholds(
    request: dict[str, Any],
) -> tuple[Decimal, Decimal, Decimal | None]:
    minimum = _non_negative_decimal(request.get("minimum_stock", 0), "minimum_stock")
    reorder = _non_negative_decimal(request.get("reorder_point", 0), "reorder_point")
    maximum = (
        _non_negative_decimal(request["maximum_stock"], "maximum_stock")
        if request.get("maximum_stock") is not None
        else None
    )
    if reorder < minimum:
        raise InventoryDomainError(
            "reorder_point phải lớn hơn hoặc bằng minimum_stock."
        )
    if maximum is not None and maximum < reorder:
        raise InventoryDomainError(
            "maximum_stock phải lớn hơn hoặc bằng reorder_point."
        )
    return minimum, reorder, maximum


def _cost_values(request: dict[str, Any]) -> tuple[Decimal | None, str | None]:
    raw_cost = request.get("unit_cost")
    raw_currency = request.get("currency_code")
    if raw_cost is None and raw_currency is None:
        return None, None
    if raw_cost is None or raw_currency is None:
        raise InventoryDomainError(
            "unit_cost và currency_code phải được cung cấp cùng nhau."
        )
    currency = str(raw_currency).strip().upper()
    if len(currency) != 3 or not currency.isalpha() or not currency.isascii():
        raise InventoryDomainError("currency_code phải là mã ba chữ cái.")
    return _non_negative_decimal(raw_cost, "unit_cost"), currency


def _quantity(value: object, precision: int) -> Decimal:
    quantity = _positive_decimal(value, "quantity")
    quantum = Decimal(1).scaleb(-precision)
    if quantity != quantity.quantize(quantum):
        raise InventoryDomainError(
            f"Quantity chỉ hỗ trợ tối đa {precision} chữ số thập phân cho UOM này."
        )
    return quantity


def _positive_decimal(value: object, field: str) -> Decimal:
    result = _decimal(value, field)
    if result <= 0:
        raise InventoryDomainError(f"{field} phải lớn hơn 0.")
    return result


def _non_negative_decimal(value: object, field: str) -> Decimal:
    result = _decimal(value, field)
    if result < 0:
        raise InventoryDomainError(f"{field} không được âm.")
    return result


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _non_negative_decimal(value, "decimal")


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise InventoryDomainError(f"{field} không phải số hợp lệ.") from exc
    if not result.is_finite() or result.as_tuple().exponent < -3:
        raise InventoryDomainError(f"{field} hỗ trợ tối đa 3 chữ số thập phân.")
    return result


def _idempotency_key(value: str) -> str:
    normalized = str(value or "").strip()
    if not _IDEMPOTENCY_PATTERN.fullmatch(normalized):
        raise InventoryDomainError(
            "Idempotency-Key phải dài 8-100 ký tự và chỉ chứa ký tự an toàn."
        )
    return normalized


def _safe_timestamp(value: object, field: str) -> datetime:
    if value is None:
        return _utc_now()
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InventoryDomainError(f"{field} phải có timezone.")
    normalized = parsed.astimezone(timezone.utc).replace(microsecond=0)
    if normalized > _utc_now() + timedelta(minutes=5):
        raise InventoryDomainError(f"{field} không được nằm trong tương lai.")
    return normalized


def _optional_future_timestamp(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InventoryDomainError(f"{field} phải có timezone.")
    normalized = parsed.astimezone(timezone.utc).replace(microsecond=0)
    if normalized <= _utc_now():
        raise InventoryDomainError(f"{field} phải nằm trong tương lai.")
    return normalized


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _public_attachment(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key != "storage_key"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
