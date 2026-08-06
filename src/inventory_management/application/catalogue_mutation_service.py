"""Inventory catalogue and lifecycle application operations.

This collaborator owns catalogue validation, authorization, and presentation
for master-data commands. The repository remains the transaction owner for
every write and optimistic-version check.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from src.inventory_management.domain import PartLifecycleStatus, StockLocationStatus
from src.inventory_management.errors import InventoryConflictError, InventoryDomainError
from src.repositories.contracts import InventoryRepository, StoredRecord
from src.security.audit import AuditContext
from src.security.permissions import Permission
from src.security.principal import CurrentUser


class InventoryCatalogueMutationService:
    """Own inventory master-data commands without owning database transactions."""

    def __init__(
        self,
        repository_provider: Callable[[], InventoryRepository],
        require_permission: Callable[[CurrentUser, Permission], None],
        part_record: Callable[[UUID], StoredRecord],
        stock_location_record: Callable[[UUID], StoredRecord],
        normalized_code: Callable[..., str],
        plain_text: Callable[..., str],
        optional_text: Callable[..., str | None],
        uuid_value: Callable[..., UUID],
        asset_types: Callable[[object], list[str]],
        thresholds: Callable[[dict[str, Any]], tuple[Any, Any, Any]],
        cost_values: Callable[[dict[str, Any]], tuple[Any, str | None]],
        utc_now: Callable[[], datetime],
    ) -> None:
        self._repository_provider = repository_provider
        self._require_permission = require_permission
        self._part_record = part_record
        self._stock_location_record = stock_location_record
        self._normalized_code = normalized_code
        self._plain_text = plain_text
        self._optional_text = optional_text
        self._uuid = uuid_value
        self._asset_types = asset_types
        self._thresholds = thresholds
        self._cost_values = cost_values
        self._utc_now = utc_now

    def create_category(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_PARTS_MANAGE)
        values = {
            "code": self._normalized_code(request["code"], "code", maximum=50),
            "name_vi": self._plain_text(request["name_vi"], "name_vi", maximum=200),
            "name_en": self._optional_text(request.get("name_en"), maximum=200),
            "description": self._optional_text(
                request.get("description"), maximum=1000
            ),
            "is_active": True,
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
        }
        return dict(
            self._repository_provider()
            .create_category(values, audit_context=audit_context)
            .values
        )

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
            "code": self._normalized_code(request["code"], "code", maximum=20),
            "name_vi": self._plain_text(request["name_vi"], "name_vi", maximum=120),
            "name_en": self._optional_text(request.get("name_en"), maximum=120),
            "symbol": self._plain_text(request["symbol"], "symbol", maximum=20),
            "quantity_precision": precision,
            "is_active": True,
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
        }
        return dict(
            self._repository_provider().create_unit(values, audit_context=audit_context).values
        )

    def create_part(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_PARTS_MANAGE)
        minimum, reorder, maximum = self._thresholds(request)
        unit_cost, currency = self._cost_values(request)
        values = {
            "part_number": self._normalized_code(
                request["part_number"], "part_number", maximum=80
            ),
            "name_vi": self._plain_text(request["name_vi"], "name_vi", maximum=200),
            "name_en": self._optional_text(request.get("name_en"), maximum=200),
            "category_id": self._uuid(request["category_id"], "category_id"),
            "unit_of_measure_id": self._uuid(
                request["unit_of_measure_id"], "unit_of_measure_id"
            ),
            "manufacturer_reference": self._optional_text(
                request.get("manufacturer_reference"), maximum=200
            ),
            "compatible_asset_types": self._asset_types(
                request.get("compatible_asset_types", [])
            ),
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
        return dict(
            self._repository_provider().create_part(values, audit_context=audit_context).values
        )

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
            updates["name_vi"] = self._plain_text(
                request["name_vi"], "name_vi", maximum=200
            )
        for field, maximum in (("name_en", 200), ("manufacturer_reference", 200)):
            if field in request:
                updates[field] = self._optional_text(request.get(field), maximum=maximum)
        if request.get("category_id") is not None:
            updates["category_id"] = self._uuid(request["category_id"], "category_id")
        if request.get("compatible_asset_types") is not None:
            updates["compatible_asset_types"] = self._asset_types(
                request["compatible_asset_types"]
            )
        if "unit_cost" in request or "currency_code" in request:
            updates["unit_cost"], updates["currency_code"] = self._cost_values(
                {"unit_cost": request.get("unit_cost"), "currency_code": request.get("currency_code")}
            )
        if not updates:
            raise InventoryDomainError("Không có field spare part nào để cập nhật.")
        return dict(
            self._repository_provider()
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
        now = self._utc_now()
        if action == "activate":
            if current_status is not PartLifecycleStatus.INACTIVE:
                raise InventoryConflictError("Chỉ spare part inactive mới có thể activate.")
            updates = {"lifecycle_status": PartLifecycleStatus.ACTIVE}
        elif action == "deactivate":
            if current_status is not PartLifecycleStatus.ACTIVE:
                raise InventoryConflictError("Chỉ spare part active mới có thể deactivate.")
            updates = {"lifecycle_status": PartLifecycleStatus.INACTIVE}
        elif action == "archive":
            if current_status is PartLifecycleStatus.ARCHIVED:
                raise InventoryConflictError("Spare part đã được archive.")
            updates = {
                "lifecycle_status": PartLifecycleStatus.ARCHIVED,
                "lifecycle_status_before_archive": current_status.value,
                "archived_at": now,
                "archive_reason": self._plain_text(
                    reason, "archive_reason", minimum=3, maximum=1000
                ),
            }
        elif action == "restore":
            if current_status is not PartLifecycleStatus.ARCHIVED:
                raise InventoryConflictError("Chỉ spare part archived mới có thể restore.")
            updates = {
                "lifecycle_status": current.get("lifecycle_status_before_archive")
                or "inactive",
                "lifecycle_status_before_archive": None,
                "archived_at": None,
                "archive_reason": None,
            }
        else:
            raise InventoryDomainError("Inventory lifecycle action không hợp lệ.")
        return dict(
            self._repository_provider()
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
            for record in self._repository_provider().list_stock_locations(
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
            "code": self._normalized_code(request["code"], "code", maximum=50),
            "name": self._plain_text(request["name"], "name", maximum=200),
            "location_type": request["location_type"],
            "description": self._optional_text(
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
            self._repository_provider()
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
            raise InventoryConflictError("Hãy restore stock location trước khi cập nhật.")
        updates: dict[str, Any] = {}
        if request.get("name") is not None:
            updates["name"] = self._plain_text(request["name"], "name", maximum=200)
        if request.get("location_type") is not None:
            updates["location_type"] = request["location_type"]
        if "description" in request:
            updates["description"] = self._optional_text(
                request.get("description"), maximum=1000
            )
        if not updates:
            raise InventoryDomainError("Không có field stock location để cập nhật.")
        return dict(
            self._repository_provider()
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
        now = self._utc_now()
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
                "archive_reason": self._plain_text(
                    reason, "archive_reason", minimum=3, maximum=1000
                ),
            }
        elif action == "restore":
            if current_status is not StockLocationStatus.ARCHIVED:
                raise InventoryConflictError(
                    "Chỉ stock location archived mới có thể restore."
                )
            updates = {
                "lifecycle_status": current.get("lifecycle_status_before_archive")
                or "inactive",
                "lifecycle_status_before_archive": None,
                "archived_at": None,
                "archive_reason": None,
            }
        else:
            raise InventoryDomainError("Stock-location lifecycle action không hợp lệ.")
        return dict(
            self._repository_provider()
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
        minimum, reorder, maximum = self._thresholds(request)
        values = {
            "part_id": part_id,
            "stock_location_id": self._uuid(
                request["stock_location_id"], "stock_location_id"
            ),
            "minimum_stock": minimum,
            "reorder_point": reorder,
            "maximum_stock": maximum,
        }
        return dict(
            self._repository_provider()
            .upsert_reorder_configuration(
                values,
                expected_version=request.get("expected_version"),
                audit_context=audit_context,
            )
            .values
        )
