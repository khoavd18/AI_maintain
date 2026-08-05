"""Shared dependencies and request aliases for inventory route modules."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Header

from src.inventory_management.service import (
    InventoryManagementService,
    build_inventory_management_service,
)
from src.security.dependencies import get_current_user, require_permission
from src.security.permissions import Permission
from src.security.service import CurrentUser


@lru_cache(maxsize=1)
def get_inventory_management_service() -> InventoryManagementService:
    return build_inventory_management_service()


ServiceDependency = Annotated[
    InventoryManagementService, Depends(get_inventory_management_service)
]
InventoryRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.INVENTORY_READ))
]
PartsManage = Annotated[
    CurrentUser, Depends(require_permission(Permission.INVENTORY_PARTS_MANAGE))
]
LocationsManage = Annotated[
    CurrentUser, Depends(require_permission(Permission.INVENTORY_LOCATIONS_MANAGE))
]
InventoryReceive = Annotated[
    CurrentUser, Depends(require_permission(Permission.INVENTORY_RECEIVE))
]
InventoryReserve = Annotated[
    CurrentUser, Depends(require_permission(Permission.INVENTORY_RESERVE))
]
InventoryIssue = Annotated[
    CurrentUser, Depends(require_permission(Permission.INVENTORY_ISSUE))
]
InventoryReturn = Annotated[
    CurrentUser, Depends(require_permission(Permission.INVENTORY_RETURN))
]
InventoryTransfer = Annotated[
    CurrentUser, Depends(require_permission(Permission.INVENTORY_TRANSFER))
]
InventoryAdjust = Annotated[
    CurrentUser, Depends(require_permission(Permission.INVENTORY_ADJUST))
]
RequirementsManage = Annotated[
    CurrentUser,
    Depends(require_permission(Permission.INVENTORY_REQUIREMENTS_MANAGE)),
]
InventoryConsume = Annotated[
    CurrentUser, Depends(require_permission(Permission.INVENTORY_CONSUME))
]
WorkOrderPartsRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDER_PARTS_READ))
]
EvidenceRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.INVENTORY_ATTACHMENTS_READ))
]
EvidenceCreate = Annotated[
    CurrentUser,
    Depends(require_permission(Permission.INVENTORY_ATTACHMENTS_CREATE)),
]
EvidenceDelete = Annotated[
    CurrentUser,
    Depends(require_permission(Permission.INVENTORY_ATTACHMENTS_DELETE)),
]
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=100,
        description="Caller-stable key for one inventory operation.",
    ),
]

__all__ = [
    "Any",
    "Depends",
    "get_current_user",
    "ServiceDependency",
    "InventoryRead",
    "PartsManage",
    "LocationsManage",
    "InventoryReceive",
    "InventoryReserve",
    "InventoryIssue",
    "InventoryReturn",
    "InventoryTransfer",
    "InventoryAdjust",
    "RequirementsManage",
    "InventoryConsume",
    "WorkOrderPartsRead",
    "EvidenceRead",
    "EvidenceCreate",
    "EvidenceDelete",
    "IdempotencyKey",
    "get_inventory_management_service",
]
