"""Work-order material requirement, reservation and issue endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status

from src.inventory_management.schemas import (
    PartConsumptionRequest,
    PartConsumptionResponse,
    PartIssueCreateRequest,
    PartIssueResponse,
    PartReturnCreateRequest,
    PartReturnResponse,
    ReservationCreateRequest,
    StockReservationResponse,
    WorkOrderPartRequirementCreateRequest,
    WorkOrderPartRequirementResponse,
    WorkOrderPartsSummaryResponse,
)
from src.security.dependencies import audit_context

from .dependencies import (
    IdempotencyKey,
    InventoryConsume,
    InventoryIssue,
    InventoryReserve,
    InventoryReturn,
    RequirementsManage,
    ServiceDependency,
    WorkOrderPartsRead,
)
from .error_mapping import _handle

router = APIRouter()


@router.get("/work-orders/{work_order_id}/parts", response_model=WorkOrderPartsSummaryResponse, tags=["work-order-inventory"])
def get_work_order_parts(work_order_id: UUID, service: ServiceDependency, actor: WorkOrderPartsRead) -> dict[str, object]:
    return _handle(service.work_order_parts, work_order_id, actor=actor)


@router.get("/work-orders/{work_order_id}/part-requirements", response_model=list[WorkOrderPartRequirementResponse], tags=["work-order-inventory"])
def list_work_order_part_requirements(work_order_id: UUID, service: ServiceDependency, actor: WorkOrderPartsRead) -> list[dict[str, object]]:
    summary = _handle(service.work_order_parts, work_order_id, actor=actor)
    return summary["requirements"]


@router.post("/work-orders/{work_order_id}/part-requirements", response_model=WorkOrderPartRequirementResponse, status_code=status.HTTP_201_CREATED, tags=["work-order-inventory"])
def create_work_order_part_requirement(work_order_id: UUID, payload: WorkOrderPartRequirementCreateRequest, service: ServiceDependency, http_request: Request, actor: RequirementsManage) -> dict[str, object]:
    return _handle(service.create_requirement, work_order_id, payload.model_dump(), actor=actor, audit_context=audit_context(actor, http_request))


@router.post("/work-order-part-requirements/{requirement_id}/reservations", response_model=StockReservationResponse, status_code=status.HTTP_201_CREATED, tags=["work-order-inventory"])
def reserve_requirement_stock(requirement_id: UUID, payload: ReservationCreateRequest, idempotency_key: IdempotencyKey, service: ServiceDependency, http_request: Request, actor: InventoryReserve) -> dict[str, object]:
    return _handle(service.reserve_stock, requirement_id, payload.model_dump(), idempotency_key=idempotency_key, actor=actor, audit_context=audit_context(actor, http_request))


@router.post("/work-orders/{work_order_id}/part-issues", response_model=PartIssueResponse, status_code=status.HTTP_201_CREATED, tags=["work-order-inventory"])
def issue_work_order_part(work_order_id: UUID, payload: PartIssueCreateRequest, idempotency_key: IdempotencyKey, service: ServiceDependency, http_request: Request, actor: InventoryIssue) -> dict[str, object]:
    return _handle(service.issue_stock, work_order_id, payload.model_dump(), idempotency_key=idempotency_key, actor=actor, audit_context=audit_context(actor, http_request))


@router.post("/part-issues/{issue_id}/consumptions", response_model=PartConsumptionResponse, status_code=status.HTTP_201_CREATED, tags=["work-order-inventory"])
def consume_work_order_part(issue_id: UUID, payload: PartConsumptionRequest, idempotency_key: IdempotencyKey, service: ServiceDependency, http_request: Request, actor: InventoryConsume) -> dict[str, object]:
    return _handle(service.consume_issue, issue_id, payload.model_dump(), idempotency_key=idempotency_key, actor=actor, audit_context=audit_context(actor, http_request))


@router.post("/part-issues/{issue_id}/returns", response_model=PartReturnResponse, status_code=status.HTTP_201_CREATED, tags=["work-order-inventory"])
def return_work_order_part(issue_id: UUID, payload: PartReturnCreateRequest, idempotency_key: IdempotencyKey, service: ServiceDependency, http_request: Request, actor: InventoryReturn) -> dict[str, object]:
    return _handle(service.return_issue, issue_id, payload.model_dump(), idempotency_key=idempotency_key, actor=actor, audit_context=audit_context(actor, http_request))
