"""Inventory balance, movement and stock-changing endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from src.inventory_management.schemas import (
    AdjustmentRequest,
    InventoryBalancePage,
    InventoryMetricsResponse,
    InventoryMovementPage,
    InventoryMovementResponse,
    OpeningBalanceRequest,
    ReceiptRequest,
    TransferRequest,
    TransferResponse,
)

from .dependencies import (
    IdempotencyKey,
    InventoryAdjust,
    InventoryRead,
    InventoryReceive,
    InventoryTransfer,
    ServiceDependency,
)
from .error_mapping import _handle
from src.security.dependencies import audit_context

router = APIRouter()


@router.get("/inventory/balances", response_model=InventoryBalancePage, tags=["inventory"])
def list_inventory_balances(
    service: ServiceDependency,
    actor: InventoryRead,
    part_id: UUID | None = None,
    stock_location_id: UUID | None = None,
    stock_state: str | None = None,
    search: str | None = Query(default=None, max_length=100),
    sort_by: str = "part_number",
    sort_direction: str = "asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, object]:
    return _handle(service.list_balances, actor=actor, filters={"part_id": part_id, "stock_location_id": stock_location_id, "stock_state": stock_state, "search": search}, sort_by=sort_by, sort_direction=sort_direction, page=page, page_size=page_size)


@router.get("/inventory/low-stock", response_model=InventoryBalancePage, tags=["inventory"])
def list_low_stock(service: ServiceDependency, actor: InventoryRead, stock_location_id: UUID | None = None, search: str | None = Query(default=None, max_length=100), page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=200)) -> dict[str, object]:
    return _handle(service.list_balances, actor=actor, filters={"stock_location_id": stock_location_id, "search": search, "low_stock_only": True}, sort_by="stock_state", sort_direction="asc", page=page, page_size=page_size)


@router.get("/inventory/movements", response_model=InventoryMovementPage, tags=["inventory"])
def list_inventory_movements(service: ServiceDependency, actor: InventoryRead, part_id: UUID | None = None, stock_location_id: UUID | None = None, movement_type: str | None = None, work_order_id: UUID | None = None, occurred_from: datetime | None = None, occurred_to: datetime | None = None, page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=200)) -> dict[str, object]:
    return _handle(service.list_movements, actor=actor, filters={"part_id": part_id, "stock_location_id": stock_location_id, "movement_type": movement_type, "work_order_id": work_order_id, "occurred_from": occurred_from, "occurred_to": occurred_to}, page=page, page_size=page_size)


@router.get("/inventory/metrics", response_model=InventoryMetricsResponse, tags=["inventory"])
def inventory_metrics(service: ServiceDependency, actor: InventoryRead) -> dict[str, object]:
    return _handle(service.metrics, actor=actor)


@router.post("/inventory/opening-balances", response_model=InventoryMovementResponse, status_code=status.HTTP_201_CREATED, tags=["inventory-actions"])
def create_opening_balance(payload: OpeningBalanceRequest, idempotency_key: IdempotencyKey, service: ServiceDependency, http_request: Request, actor: InventoryReceive) -> dict[str, object]:
    return _handle(service.create_opening_balance, payload.model_dump(), idempotency_key=idempotency_key, actor=actor, audit_context=audit_context(actor, http_request))


@router.post("/inventory/receipts", response_model=InventoryMovementResponse, status_code=status.HTTP_201_CREATED, tags=["inventory-actions"])
def receive_inventory_stock(payload: ReceiptRequest, idempotency_key: IdempotencyKey, service: ServiceDependency, http_request: Request, actor: InventoryReceive) -> dict[str, object]:
    return _handle(service.receive_stock, payload.model_dump(), idempotency_key=idempotency_key, actor=actor, audit_context=audit_context(actor, http_request))


@router.post("/inventory/transfers", response_model=TransferResponse, status_code=status.HTTP_201_CREATED, tags=["inventory-actions"])
def transfer_inventory_stock(payload: TransferRequest, idempotency_key: IdempotencyKey, service: ServiceDependency, http_request: Request, actor: InventoryTransfer) -> dict[str, object]:
    return _handle(service.transfer_stock, payload.model_dump(), idempotency_key=idempotency_key, actor=actor, audit_context=audit_context(actor, http_request))


@router.post("/inventory/adjustments", response_model=InventoryMovementResponse, status_code=status.HTTP_201_CREATED, tags=["inventory-actions"])
def adjust_inventory_stock(payload: AdjustmentRequest, idempotency_key: IdempotencyKey, service: ServiceDependency, http_request: Request, actor: InventoryAdjust) -> dict[str, object]:
    return _handle(service.adjust_stock, payload.model_dump(), idempotency_key=idempotency_key, actor=actor, audit_context=audit_context(actor, http_request))
