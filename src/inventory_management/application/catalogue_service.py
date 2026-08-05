"""Read-only inventory catalogue application operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.config.value_mappings import ASSET_TYPE_CODE_TO_VI
from src.inventory_management.domain import (
    INVENTORY_ATTACHMENT_CATEGORIES,
    MOVEMENT_TYPE_LABELS,
    PART_LIFECYCLE_LABELS,
    REQUIREMENT_STATUS_LABELS,
    RESERVATION_STATUS_LABELS,
    STOCK_LOCATION_STATUS_LABELS,
    STOCK_LOCATION_TYPE_LABELS,
    STOCK_STATE_LABELS,
)
from src.repositories.contracts import InventoryRepository
from src.security.permissions import Permission
from src.security.service import CurrentUser


class InventoryCatalogueService:
    """Own inventory catalogue/options queries without stock mutations."""

    def __init__(
        self,
        repository_provider: Callable[[], InventoryRepository],
        require_permission: Callable[[CurrentUser, Permission], None],
        require_any_read: Callable[[CurrentUser], None],
    ) -> None:
        self._repository_provider = repository_provider
        self._require_permission = require_permission
        self._require_any_read = require_any_read

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
            for record in self._repository_provider().list_categories(
                include_inactive=include_inactive
            )
        ]

    def list_units(
        self, *, actor: CurrentUser, include_inactive: bool
    ) -> list[dict[str, Any]]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        return [
            dict(record.values)
            for record in self._repository_provider().list_units(
                include_inactive=include_inactive
            )
        ]


def _options(mapping: dict[Any, str]) -> list[dict[str, str]]:
    return [
        {"code": str(code), "display_name": display_name}
        for code, display_name in mapping.items()
    ]
