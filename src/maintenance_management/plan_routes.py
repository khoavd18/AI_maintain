"""HTTP routes for preventive maintenance plans and generation."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from src.maintenance_management.route_support import (
    GenerationRun,
    PlansArchive,
    PlansCreate,
    PlansPause,
    PlansRead,
    PlansUpdate,
    ServiceDependency,
    WorkOrdersRead,
    _handle,
)
from src.maintenance_management.schemas import (
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
    VersionRequest,
)
from src.security.dependencies import audit_context

router = APIRouter()


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
