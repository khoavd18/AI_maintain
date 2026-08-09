"""Inventory read capability for balances, movements, and work-order stock."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from src.inventory_management.errors import InventoryDomainError
from src.repositories.contracts import InventoryRepository, StoredPage
from src.security.permissions import Permission
from src.security.principal import CurrentUser


class InventoryStockQueryService:
    """Own stock read validation and projection mapping."""

    def __init__(
        self,
        repository_provider: Callable[[], InventoryRepository],
        *,
        require_permission: Callable[[CurrentUser, Permission], None],
        get_work_order: Callable[[UUID], dict[str, Any]],
        require_work_order_access: Callable[[dict[str, Any], CurrentUser], None],
    ) -> None:
        self._repository_provider = repository_provider
        self._require_permission = require_permission
        self._get_work_order = get_work_order
        self._require_work_order_access = require_work_order_access

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
            self._repository_provider().list_balances(
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
            self._repository_provider().list_movements(
                filters=filters, page=page, page_size=page_size
            )
        )

    def work_order_parts(self, work_order_id: UUID, *, actor: CurrentUser) -> dict[str, Any]:
        self._require_permission(actor, Permission.WORK_ORDER_PARTS_READ)
        work_order = self._get_work_order(work_order_id)
        self._require_work_order_access(work_order, actor)
        return dict(self._repository_provider().work_order_parts(work_order_id).values)

    def metrics(self, *, actor: CurrentUser) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        return dict(self._repository_provider().inventory_metrics().values)


def _page_values(page: StoredPage) -> dict[str, Any]:
    return {
        "items": [dict(record.values) for record in page.items],
        "page": page.page,
        "page_size": page.page_size,
        "total": page.total,
        "total_pages": (page.total + page.page_size - 1) // page.page_size,
    }
