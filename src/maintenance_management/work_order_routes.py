"""HTTP routes for executable work-order operations.

Preventive-plan and checklist routes remain in ``routes.py`` for the moment;
this module isolates the work-order lifecycle and ticket linkage while using
the same service dependency and error mapping.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from src.maintenance_management.route_support import (
    ServiceDependency,
    WorkOrdersAssign,
    WorkOrdersCancel,
    WorkOrdersComplete,
    WorkOrdersCreate,
    WorkOrdersExecute,
    WorkOrdersRead,
    WorkOrdersReopen,
    WorkOrdersUpdate,
    WorkOrdersVerify,
    _handle,
)
from src.maintenance_management.schemas import (
    CorrectiveWorkOrderCreateRequest,
    ScheduleViewResponse,
    VersionRequest,
    WorkOrderAssignRequest,
    WorkOrderCancelRequest,
    WorkOrderChecklistUpdateRequest,
    WorkOrderCompleteRequest,
    WorkOrderCreateRequest,
    WorkOrderMetricsResponse,
    WorkOrderPage,
    WorkOrderReopenRequest,
    WorkOrderResponse,
    WorkOrderTransitionRequest,
    WorkOrderUpdateRequest,
)
from src.security.dependencies import audit_context

router = APIRouter()


@router.get(
    "/work-orders",
    response_model=WorkOrderPage,
    tags=["work-orders"],
)
def list_work_orders(
    service: ServiceDependency,
    actor: WorkOrdersRead,
    work_order_status: str | None = Query(default=None, alias="status"),
    work_order_type: str | None = None,
    asset_id: str | None = None,
    assigned_to_user_id: UUID | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    overdue: bool | None = None,
    source_ticket_id: str | None = None,
    preventive_plan_id: UUID | None = None,
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, object]:
    return _handle(
        service.list_work_orders,
        actor=actor,
        filters={
            "status": work_order_status,
            "work_order_type": work_order_type,
            "asset_id": asset_id,
            "assigned_to_user_id": assigned_to_user_id,
            "due_from": due_from,
            "due_to": due_to,
            "overdue": overdue,
            "source_ticket_id": source_ticket_id,
            "preventive_plan_id": preventive_plan_id,
            "search": search,
        },
        page=page,
        page_size=page_size,
    )


@router.post(
    "/work-orders",
    response_model=WorkOrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["work-orders"],
)
def create_work_order(
    request: WorkOrderCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: WorkOrdersCreate,
) -> dict[str, object]:
    return _handle(
        service.create_work_order,
        request=request.model_dump(),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/work-orders/metrics",
    response_model=WorkOrderMetricsResponse,
    tags=["work-orders"],
)
def work_order_metrics(
    service: ServiceDependency,
    _actor: WorkOrdersRead,
    as_of_date: date,
) -> dict[str, object]:
    return _handle(service.metrics, as_of_date=as_of_date)


@router.get(
    "/work-orders/calendar",
    response_model=ScheduleViewResponse,
    tags=["work-orders"],
)
def work_order_calendar(
    service: ServiceDependency,
    actor: WorkOrdersRead,
    date_from: date,
    date_to: date,
    asset_id: str | None = None,
    assigned_to_user_id: UUID | None = None,
) -> dict[str, object]:
    return _handle(
        service.schedule_view,
        actor=actor,
        date_from=date_from,
        date_to=date_to,
        asset_id=asset_id,
        assigned_to_user_id=assigned_to_user_id,
    )


@router.get(
    "/work-orders/{work_order_id}",
    response_model=WorkOrderResponse,
    tags=["work-orders"],
)
def get_work_order(
    work_order_id: UUID, service: ServiceDependency, actor: WorkOrdersRead
) -> dict[str, object]:
    return _handle(service.get_work_order, work_order_id=work_order_id, actor=actor)


@router.patch(
    "/work-orders/{work_order_id}",
    response_model=WorkOrderResponse,
    tags=["work-orders"],
)
def update_work_order(
    work_order_id: UUID,
    request: WorkOrderUpdateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: WorkOrdersUpdate,
) -> dict[str, object]:
    values = request.model_dump(exclude_unset=True)
    expected_version = values.pop("expected_version")
    return _handle(
        service.update_work_order,
        work_order_id=work_order_id,
        updates=values,
        expected_version=expected_version,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/work-orders/{work_order_id}/assign",
    response_model=WorkOrderResponse,
    tags=["work-orders"],
)
def assign_work_order(
    work_order_id: UUID,
    request: WorkOrderAssignRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: WorkOrdersAssign,
) -> dict[str, object]:
    return _handle(
        service.assign_work_order,
        work_order_id=work_order_id,
        assigned_to_user_id=request.assigned_to_user_id,
        expected_version=request.expected_version,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/work-orders/{work_order_id}/transition",
    response_model=WorkOrderResponse,
    tags=["work-orders"],
)
def transition_work_order(
    work_order_id: UUID,
    request: WorkOrderTransitionRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: WorkOrdersExecute,
) -> dict[str, object]:
    return _handle(
        service.transition_work_order,
        work_order_id=work_order_id,
        target_status=request.target_status,
        hold_reason=request.hold_reason,
        expected_version=request.expected_version,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/work-orders/{work_order_id}/checklist",
    response_model=WorkOrderResponse,
    tags=["work-orders"],
)
def update_work_order_checklist(
    work_order_id: UUID,
    request: WorkOrderChecklistUpdateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: WorkOrdersExecute,
) -> dict[str, object]:
    return _handle(
        service.update_checklist,
        work_order_id=work_order_id,
        responses=[response.model_dump() for response in request.responses],
        expected_version=request.expected_version,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/work-orders/{work_order_id}/complete",
    response_model=WorkOrderResponse,
    tags=["work-orders"],
)
def complete_work_order(
    work_order_id: UUID,
    request: WorkOrderCompleteRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: WorkOrdersComplete,
) -> dict[str, object]:
    values = request.model_dump()
    expected_version = values.pop("expected_version")
    return _handle(
        service.complete_work_order,
        work_order_id=work_order_id,
        request=values,
        expected_version=expected_version,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/work-orders/{work_order_id}/verify",
    response_model=WorkOrderResponse,
    tags=["work-orders"],
)
def verify_work_order(
    work_order_id: UUID,
    request: VersionRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: WorkOrdersVerify,
) -> dict[str, object]:
    return _handle(
        service.verify_work_order,
        work_order_id=work_order_id,
        expected_version=request.expected_version,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/work-orders/{work_order_id}/cancel",
    response_model=WorkOrderResponse,
    tags=["work-orders"],
)
def cancel_work_order(
    work_order_id: UUID,
    request: WorkOrderCancelRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: WorkOrdersCancel,
) -> dict[str, object]:
    return _handle(
        service.cancel_work_order,
        work_order_id=work_order_id,
        expected_version=request.expected_version,
        cancellation_reason=request.cancellation_reason,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/work-orders/{work_order_id}/reopen",
    response_model=WorkOrderResponse,
    tags=["work-orders"],
)
def reopen_work_order(
    work_order_id: UUID,
    request: WorkOrderReopenRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: WorkOrdersReopen,
) -> dict[str, object]:
    return _handle(
        service.reopen_work_order,
        work_order_id=work_order_id,
        expected_version=request.expected_version,
        reason=request.reason,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/tickets/{ticket_id}/work-orders",
    response_model=list[WorkOrderResponse],
    tags=["work-orders"],
)
def ticket_work_orders(
    ticket_id: str, service: ServiceDependency, actor: WorkOrdersRead
) -> list[dict[str, object]]:
    return _handle(service.linked_work_orders, ticket_id=ticket_id, actor=actor)


@router.post(
    "/tickets/{ticket_id}/work-orders",
    response_model=WorkOrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["work-orders"],
)
def create_ticket_work_order(
    ticket_id: str,
    request: CorrectiveWorkOrderCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: WorkOrdersCreate,
) -> dict[str, object]:
    return _handle(
        service.create_corrective_from_ticket,
        ticket_id=ticket_id,
        request=request.model_dump(),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )
