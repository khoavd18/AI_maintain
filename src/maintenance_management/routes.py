"""FastAPI routes for preventive plans, checklists, and work orders."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)

from src.asset_management.storage import AttachmentStorageError, AttachmentValidationError
from src.maintenance_management.schemas import (
    ChecklistTemplateCreateRequest,
    ChecklistTemplatePage,
    ChecklistTemplateResponse,
    ChecklistTemplateVersionRequest,
    CorrectiveWorkOrderCreateRequest,
    GenerationRequest,
    GenerationResponse,
    MaintenanceOptionsResponse,
    MaintenancePlanArchiveRequest,
    MaintenancePlanCreateRequest,
    MaintenancePlanPage,
    MaintenancePlanResponse,
    MaintenancePlanResumeRequest,
    MaintenancePlanUpdateRequest,
    OccurrencePreviewResponse,
    ScheduleViewResponse,
    VersionRequest,
    WorkOrderAssignRequest,
    WorkOrderAttachmentResponse,
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
from src.maintenance_management.service import (
    MaintenanceAuthorizationError,
    MaintenanceConflictError,
    MaintenanceDomainError,
    MaintenanceNotFoundError,
    MaintenancePlanningService,
    build_maintenance_planning_service,
)
from src.repositories.contracts import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    RecordNotFoundError,
    RepositoryError,
    StaleRecordError,
    StorageUnavailableError,
    UnsupportedStorageOperationError,
)
from src.security.dependencies import audit_context, require_permission
from src.security.permissions import Permission
from src.security.service import CurrentUser

router = APIRouter()


@lru_cache(maxsize=1)
def get_maintenance_planning_service() -> MaintenancePlanningService:
    return build_maintenance_planning_service()


ServiceDependency = Annotated[
    MaintenancePlanningService, Depends(get_maintenance_planning_service)
]
PlansRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_PLANS_READ))
]
PlansCreate = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_PLANS_CREATE))
]
PlansUpdate = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_PLANS_UPDATE))
]
PlansPause = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_PLANS_PAUSE))
]
PlansArchive = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_PLANS_ARCHIVE))
]
TemplatesRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.CHECKLIST_TEMPLATES_READ))
]
TemplatesCreate = Annotated[
    CurrentUser, Depends(require_permission(Permission.CHECKLIST_TEMPLATES_CREATE))
]
TemplatesUpdate = Annotated[
    CurrentUser, Depends(require_permission(Permission.CHECKLIST_TEMPLATES_UPDATE))
]
WorkOrdersRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_READ))
]
WorkOrdersCreate = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_CREATE))
]
WorkOrdersAssign = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_ASSIGN))
]
WorkOrdersUpdate = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_UPDATE))
]
WorkOrdersExecute = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_EXECUTE))
]
WorkOrdersComplete = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_COMPLETE))
]
WorkOrdersVerify = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_VERIFY))
]
WorkOrdersCancel = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_CANCEL))
]
WorkOrdersReopen = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_REOPEN))
]
GenerationRun = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_GENERATION_RUN))
]
EvidenceRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDER_ATTACHMENTS_READ))
]
EvidenceCreate = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDER_ATTACHMENTS_CREATE))
]
EvidenceDelete = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDER_ATTACHMENTS_DELETE))
]


@router.get(
    "/maintenance/options",
    response_model=MaintenanceOptionsResponse,
    tags=["maintenance-planning"],
)
def maintenance_options(
    service: ServiceDependency, _actor: WorkOrdersRead
) -> dict[str, object]:
    return _handle(service.options)


@router.get(
    "/maintenance-plans",
    response_model=MaintenancePlanPage,
    tags=["maintenance-planning"],
)
def list_maintenance_plans(
    service: ServiceDependency,
    _actor: PlansRead,
    asset_id: str | None = None,
    plan_status: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=100),
    due_from: date | None = None,
    due_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, object]:
    return _handle(
        service.list_plans,
        asset_id=asset_id,
        status=plan_status,
        search=search,
        due_from=due_from,
        due_to=due_to,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/maintenance-plans",
    response_model=MaintenancePlanResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["maintenance-planning"],
)
def create_maintenance_plan(
    request: MaintenancePlanCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PlansCreate,
) -> dict[str, object]:
    return _handle(
        service.create_plan,
        request=request.model_dump(),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/maintenance-plans/generate/dry-run",
    response_model=GenerationResponse,
    tags=["maintenance-planning"],
)
def dry_run_generation(
    request: GenerationRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: GenerationRun,
) -> dict[str, object]:
    return _handle(
        service.generate,
        **request.model_dump(),
        dry_run=True,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/maintenance-plans/generate",
    response_model=GenerationResponse,
    tags=["maintenance-planning"],
)
def generate_maintenance_work_orders(
    request: GenerationRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: GenerationRun,
) -> dict[str, object]:
    return _handle(
        service.generate,
        **request.model_dump(),
        dry_run=False,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/maintenance-plans/{plan_id}",
    response_model=MaintenancePlanResponse,
    tags=["maintenance-planning"],
)
def get_maintenance_plan(
    plan_id: UUID, service: ServiceDependency, _actor: PlansRead
) -> dict[str, object]:
    return _handle(service.get_plan, plan_id=plan_id)


@router.patch(
    "/maintenance-plans/{plan_id}",
    response_model=MaintenancePlanResponse,
    tags=["maintenance-planning"],
)
def update_maintenance_plan(
    plan_id: UUID,
    request: MaintenancePlanUpdateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PlansUpdate,
) -> dict[str, object]:
    values = request.model_dump(exclude_unset=True)
    expected_version = values.pop("expected_version")
    return _handle(
        service.update_plan,
        plan_id=plan_id,
        updates=values,
        expected_version=expected_version,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/maintenance-plans/{plan_id}/pause",
    response_model=MaintenancePlanResponse,
    tags=["maintenance-planning"],
)
def pause_maintenance_plan(
    plan_id: UUID,
    request: VersionRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PlansPause,
) -> dict[str, object]:
    return _handle(
        service.pause_plan,
        plan_id=plan_id,
        expected_version=request.expected_version,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/maintenance-plans/{plan_id}/resume",
    response_model=MaintenancePlanResponse,
    tags=["maintenance-planning"],
)
def resume_maintenance_plan(
    plan_id: UUID,
    request: MaintenancePlanResumeRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PlansPause,
) -> dict[str, object]:
    return _handle(
        service.resume_plan,
        plan_id=plan_id,
        expected_version=request.expected_version,
        resume_date=request.resume_date,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/maintenance-plans/{plan_id}/archive",
    response_model=MaintenancePlanResponse,
    tags=["maintenance-planning"],
)
def archive_maintenance_plan(
    plan_id: UUID,
    request: MaintenancePlanArchiveRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PlansArchive,
) -> dict[str, object]:
    return _handle(
        service.archive_plan,
        plan_id=plan_id,
        expected_version=request.expected_version,
        archive_reason=request.archive_reason,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/maintenance-plans/{plan_id}/occurrences",
    response_model=OccurrencePreviewResponse,
    tags=["maintenance-planning"],
)
def preview_plan_occurrences(
    plan_id: UUID,
    service: ServiceDependency,
    _actor: PlansRead,
    date_from: date,
    date_to: date,
    limit: int = Query(default=50, ge=1, le=256),
) -> dict[str, object]:
    return _handle(
        service.preview_occurrences,
        plan_id=plan_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get(
    "/checklist-templates",
    response_model=ChecklistTemplatePage,
    tags=["maintenance-planning"],
)
def list_checklist_templates(
    service: ServiceDependency,
    _actor: TemplatesRead,
    template_status: str | None = Query(default=None, alias="status"),
    asset_type: str | None = None,
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, object]:
    return _handle(
        service.list_templates,
        status=template_status,
        asset_type=asset_type,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/checklist-templates",
    response_model=ChecklistTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["maintenance-planning"],
)
def create_checklist_template(
    request: ChecklistTemplateCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: TemplatesCreate,
) -> dict[str, object]:
    return _handle(
        service.create_template,
        request=request.model_dump(),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/checklist-templates/{template_id}",
    response_model=ChecklistTemplateResponse,
    tags=["maintenance-planning"],
)
def get_checklist_template(
    template_id: UUID, service: ServiceDependency, _actor: TemplatesRead
) -> dict[str, object]:
    return _handle(service.get_template, template_id=template_id)


@router.post(
    "/checklist-templates/{template_id}/versions",
    response_model=ChecklistTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["maintenance-planning"],
)
def version_checklist_template(
    template_id: UUID,
    request: ChecklistTemplateVersionRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: TemplatesUpdate,
) -> dict[str, object]:
    return _handle(
        service.version_template,
        template_id=template_id,
        request=request.model_dump(exclude_unset=True),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/checklist-templates/{template_id}/archive",
    response_model=ChecklistTemplateResponse,
    tags=["maintenance-planning"],
)
def archive_checklist_template(
    template_id: UUID,
    request: VersionRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: TemplatesUpdate,
) -> dict[str, object]:
    return _handle(
        service.archive_template,
        template_id=template_id,
        expected_version=request.expected_version,
        audit_context=audit_context(actor, http_request),
    )


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


@router.get(
    "/work-orders/{work_order_id}/attachments",
    response_model=list[WorkOrderAttachmentResponse],
    tags=["work-orders"],
)
def list_work_order_attachments(
    work_order_id: UUID, service: ServiceDependency, actor: EvidenceRead
) -> list[dict[str, object]]:
    return _handle(service.list_evidence, work_order_id=work_order_id, actor=actor)


@router.post(
    "/work-orders/{work_order_id}/attachments",
    response_model=WorkOrderAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["work-orders"],
)
async def upload_work_order_attachment(
    work_order_id: UUID,
    service: ServiceDependency,
    http_request: Request,
    actor: EvidenceCreate,
    category: Annotated[str, Form(min_length=1, max_length=40)],
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    try:
        content = await file.read(service.attachment_max_size_bytes + 1)
    finally:
        await file.close()
    return _handle(
        service.upload_evidence,
        work_order_id=work_order_id,
        category=category,
        filename=file.filename or "",
        claimed_media_type=file.content_type,
        content=content,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/work-orders/{work_order_id}/attachments/{attachment_id}",
    tags=["work-orders"],
)
def download_work_order_attachment(
    work_order_id: UUID,
    attachment_id: UUID,
    service: ServiceDependency,
    actor: EvidenceRead,
) -> Response:
    download = _handle(
        service.download_evidence,
        work_order_id=work_order_id,
        attachment_id=attachment_id,
        actor=actor,
    )
    filename = quote(download.filename, safe="")
    return Response(
        content=download.content,
        media_type=download.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/work-orders/{work_order_id}/attachments/{attachment_id}",
    response_model=WorkOrderAttachmentResponse,
    tags=["work-orders"],
)
def delete_work_order_attachment(
    work_order_id: UUID,
    attachment_id: UUID,
    service: ServiceDependency,
    http_request: Request,
    actor: EvidenceDelete,
) -> dict[str, object]:
    return _handle(
        service.delete_evidence,
        work_order_id=work_order_id,
        attachment_id=attachment_id,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


def _handle(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except MaintenanceAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (MaintenanceNotFoundError, RecordNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        MaintenanceConflictError,
        DuplicateIdentifierError,
        IntegrityViolationError,
        StaleRecordError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (AttachmentValidationError, MaintenanceDomainError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except (
        AttachmentStorageError,
        StorageUnavailableError,
        UnsupportedStorageOperationError,
        RepositoryError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
