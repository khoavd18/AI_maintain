"""Stock reservation listing and lifecycle endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from src.inventory_management.domain import ReservationStatus
from src.inventory_management.schemas import (
    ReservationActionRequest,
    ReservationReplaceRequest,
    StockReservationPage,
    StockReservationResponse,
)
from src.security.dependencies import audit_context

from .dependencies import IdempotencyKey, InventoryRead, InventoryReserve, ServiceDependency
from .error_mapping import _handle

router = APIRouter()


@router.get("/inventory/reservations", response_model=StockReservationPage, tags=["inventory"])
def list_stock_reservations(
    service: ServiceDependency,
    actor: InventoryRead,
    work_order_id: UUID | None = None,
    part_id: UUID | None = None,
    stock_location_id: UUID | None = None,
    reservation_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, object]:
    return _handle(service.list_reservations, actor=actor, filters={"work_order_id": work_order_id, "part_id": part_id, "stock_location_id": stock_location_id, "status": reservation_status}, page=page, page_size=page_size)


@router.post("/stock-reservations/{reservation_id}/release", response_model=StockReservationResponse, tags=["work-order-inventory"])
def release_stock_reservation(reservation_id: UUID, payload: ReservationActionRequest, idempotency_key: IdempotencyKey, service: ServiceDependency, http_request: Request, actor: InventoryReserve) -> dict[str, object]:
    return _handle(service.close_reservation, reservation_id, payload.model_dump(), target_status=ReservationStatus.RELEASED, idempotency_key=idempotency_key, actor=actor, audit_context=audit_context(actor, http_request))


@router.post("/stock-reservations/{reservation_id}/expire", response_model=StockReservationResponse, tags=["work-order-inventory"])
def expire_stock_reservation(reservation_id: UUID, payload: ReservationActionRequest, idempotency_key: IdempotencyKey, service: ServiceDependency, http_request: Request, actor: InventoryReserve) -> dict[str, object]:
    return _handle(service.close_reservation, reservation_id, payload.model_dump(), target_status=ReservationStatus.EXPIRED, idempotency_key=idempotency_key, actor=actor, audit_context=audit_context(actor, http_request))


@router.post("/stock-reservations/{reservation_id}/replace", response_model=StockReservationResponse, status_code=status.HTTP_201_CREATED, tags=["work-order-inventory"])
def replace_stock_reservation(reservation_id: UUID, payload: ReservationReplaceRequest, idempotency_key: IdempotencyKey, service: ServiceDependency, http_request: Request, actor: InventoryReserve) -> dict[str, object]:
    return _handle(service.replace_reservation, reservation_id, payload.model_dump(), idempotency_key=idempotency_key, actor=actor, audit_context=audit_context(actor, http_request))
