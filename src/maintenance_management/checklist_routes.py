"""HTTP routes for immutable checklist templates and versions."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from src.maintenance_management.route_support import (
    ServiceDependency,
    TemplatesCreate,
    TemplatesRead,
    TemplatesUpdate,
    _handle,
)
from src.maintenance_management.schemas import (
    ChecklistTemplateCreateRequest,
    ChecklistTemplatePage,
    ChecklistTemplateResponse,
    ChecklistTemplateVersionRequest,
    VersionRequest,
)
from src.security.dependencies import audit_context

router = APIRouter()


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


# Work-order lifecycle routes are registered from work_order_routes.py.
