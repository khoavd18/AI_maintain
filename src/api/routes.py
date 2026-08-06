"""FastAPI routes for processed maintenance intelligence outputs."""

from typing import Annotated, Literal
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

from src.asset_management.service import (
    ArchivedAssetLookupError,
    AssetDomainConflictError,
    AssetDomainError,
    AssetDomainNotFoundError,
)
from src.asset_management.storage import AttachmentStorageError, AttachmentValidationError
from src.api.schemas import (
    AssetArchiveRequest,
    AssetAttachmentRecord,
    AssetCatalogPage,
    AssetContextResponse,
    AssetCreateRequest,
    AssetDetailsResponse,
    AssetHistoryPage,
    AssetOverviewRecord,
    AssetOptionsResponse,
    AssetProfileResponse,
    AssetQrResponse,
    AssetRecord,
    AssetRestoreRequest,
    AssetUpdateRequest,
    MaintenanceLogCreateRequest,
    MaintenanceLogRecord,
    LifecycleTransitionRequest,
    LocationCreateRequest,
    LocationRecord,
    LocationUpdateRequest,
    OperationalStatusRequest,
    TicketCreateRequest,
    TicketRecord,
    TicketUpdateRequest,
    VersionedRequest,
)
from src.api.services import (
    AssetNotFoundError,
    ProcessedDataNotFoundError,
    ProcessedDataService,
    TicketNotFoundError,
)
from src.api.routers.analytics import (
    asset_anomaly_history,
    asset_risk_history,
    list_asset_anomalies,
    list_asset_risks,
    maintenance_kpis,
    preventive_maintenance,
    recurring_issues,
    router as analytics_router,
    summary,
    top_asset_risks,
)
from src.api.routers.copilot import (
    _copilot_rate_limiter,
    _copilot_service,
    ask_copilot,
    router as copilot_router,
)
from src.api.routers.dependencies import get_service
from src.api.routers.system import health, rag_readiness, router as system_router
from src.rag.vector_store import QdrantVectorStore
from src.repositories.contracts import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    RecordNotFoundError as RepositoryRecordNotFoundError,
    RepositoryError,
    StaleRecordError,
    StorageUnavailableError,
    UnsupportedStorageOperationError,
)
from src.repositories.csv_writes import (
    CsvRepositoryError,
    CsvWriteError,
    DuplicateRecordError,
    RecordNotFoundError,
)
from src.security.dependencies import audit_context, require_permission
from src.security.permissions import Permission, Role
from src.security.principal import CurrentUser

router = APIRouter()
router.include_router(system_router)
router.include_router(analytics_router)
router.include_router(copilot_router)


_service = get_service


ServiceDependency = Annotated[ProcessedDataService, Depends(_service)]
AssetsReadDependency = Annotated[CurrentUser, Depends(require_permission(Permission.ASSETS_READ))]
AssetsCreateDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.ASSETS_CREATE))
]
AssetsUpdateDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.ASSETS_UPDATE))
]
AssetsStatusDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.ASSETS_CHANGE_STATUS))
]
AssetsArchiveDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.ASSETS_ARCHIVE))
]
AssetsRestoreDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.ASSETS_RESTORE))
]
LocationsReadDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.LOCATIONS_READ))
]
LocationsCreateDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.LOCATIONS_CREATE))
]
LocationsUpdateDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.LOCATIONS_UPDATE))
]
LocationsArchiveDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.LOCATIONS_ARCHIVE))
]
AttachmentsReadDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.ATTACHMENTS_READ))
]
AttachmentsCreateDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.ATTACHMENTS_CREATE))
]
AttachmentsDeleteDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.ATTACHMENTS_DELETE))
]
TicketsReadDependency = Annotated[CurrentUser, Depends(require_permission(Permission.TICKETS_READ))]
TicketsCreateDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.TICKETS_CREATE))
]
TicketsUpdateDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.TICKETS_UPDATE))
]
LogsReadDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_LOGS_READ))
]
LogsCreateDependency = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_LOGS_CREATE))
]


@router.get("/assets/options", response_model=AssetOptionsResponse, tags=["asset-management"])
def asset_options(
    service: ServiceDependency,
    _actor: AssetsReadDependency,
) -> dict[str, object]:
    """Return canonical codes and Vietnamese labels for asset forms."""

    return service.asset_management.options()


@router.get("/assets/catalog", response_model=AssetCatalogPage, tags=["asset-management"])
def asset_catalog(
    service: ServiceDependency,
    _actor: AssetsReadDependency,
    search: Annotated[str | None, Query(max_length=200)] = None,
    asset_type: Literal["hvac", "pump", "generator"] | None = None,
    criticality: Literal["low", "medium", "high", "critical"] | None = None,
    lifecycle_status: Literal["planned", "active", "inactive", "retired", "archived"] | None = None,
    operational_status: Literal[
        "running", "warning", "fault", "under_maintenance", "out_of_service"
    ]
    | None = None,
    location_id: UUID | None = None,
    include_archived: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, object]:
    """Return the rich paginated asset catalog without changing legacy `/assets`."""

    return _handle_asset_errors(
        service.asset_management.list_assets,
        filters={
            "search": search,
            "asset_type": asset_type,
            "criticality": criticality,
            "lifecycle_status": lifecycle_status,
            "operational_status": operational_status,
            "location_id": location_id,
            "include_archived": include_archived,
        },
        page=page,
        page_size=page_size,
    )


@router.post(
    "/assets",
    response_model=AssetProfileResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["asset-management"],
)
def create_asset(
    request: AssetCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: AssetsCreateDependency,
) -> dict[str, object]:
    """Register one asset with a canonical technical and lifecycle profile."""

    return _handle_asset_errors(
        service.asset_management.create_asset,
        request.model_dump(),
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/assets/{asset_id}/profile",
    response_model=AssetProfileResponse,
    tags=["asset-management"],
)
def asset_profile(
    asset_id: str,
    service: ServiceDependency,
    _actor: AssetsReadDependency,
) -> dict[str, object]:
    """Return the canonical management profile for one asset."""

    return _handle_asset_errors(service.asset_management.get_asset, asset_id=asset_id)


@router.patch(
    "/assets/{asset_id}",
    response_model=AssetProfileResponse,
    tags=["asset-management"],
)
def update_asset_profile(
    asset_id: str,
    request: AssetUpdateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: AssetsUpdateDependency,
) -> dict[str, object]:
    """Update bounded profile fields with optimistic concurrency."""

    updates = request.model_dump(exclude_unset=True)
    expected_version = int(updates.pop("expected_version"))
    _authorize_asset_profile_update(actor, updates)
    return _handle_asset_errors(
        service.asset_management.update_asset,
        asset_id=asset_id,
        updates=updates,
        expected_version=expected_version,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/assets/{asset_id}/operational-status",
    response_model=AssetProfileResponse,
    tags=["asset-management"],
)
def change_asset_operational_status(
    asset_id: str,
    request: OperationalStatusRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: AssetsStatusDependency,
) -> dict[str, object]:
    """Apply an explicit temporary operational-status transition."""

    if actor.role is Role.TECHNICIAN and request.operational_status == "out_of_service":
        _forbidden("Kỹ thuật viên không có quyền đặt asset ở trạng thái ngừng hoạt động.")
    return _handle_asset_errors(
        service.asset_management.change_operational_status,
        asset_id=asset_id,
        operational_status=request.operational_status,
        expected_version=request.expected_version,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/assets/{asset_id}/lifecycle-transition",
    response_model=AssetProfileResponse,
    tags=["asset-management"],
)
def transition_asset_lifecycle(
    asset_id: str,
    request: LifecycleTransitionRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: AssetsUpdateDependency,
) -> dict[str, object]:
    """Apply a manager-controlled lifecycle transition."""

    _require_lifecycle_manager(actor)
    return _handle_asset_errors(
        service.asset_management.transition_lifecycle,
        asset_id=asset_id,
        lifecycle_status=request.lifecycle_status,
        expected_version=request.expected_version,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/assets/{asset_id}/archive",
    response_model=AssetProfileResponse,
    tags=["asset-management"],
)
def archive_asset(
    asset_id: str,
    request: AssetArchiveRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: AssetsArchiveDependency,
) -> dict[str, object]:
    """Archive an asset in place and preserve all linked history."""

    return _handle_asset_errors(
        service.asset_management.archive_asset,
        asset_id=asset_id,
        archive_reason=request.archive_reason,
        expected_version=request.expected_version,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/assets/{asset_id}/restore",
    response_model=AssetProfileResponse,
    tags=["asset-management"],
)
def restore_asset(
    asset_id: str,
    request: AssetRestoreRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: AssetsRestoreDependency,
) -> dict[str, object]:
    """Explicitly restore an archived asset."""

    return _handle_asset_errors(
        service.asset_management.restore_asset,
        asset_id=asset_id,
        expected_version=request.expected_version,
        lifecycle_status=request.lifecycle_status,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/assets/{asset_id}/history",
    response_model=AssetHistoryPage,
    tags=["asset-management"],
)
def asset_history(
    asset_id: str,
    service: ServiceDependency,
    _actor: AssetsReadDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, object]:
    """Return one redacted, de-duplicated asset timeline."""

    return _handle_asset_errors(
        service.asset_management.history,
        asset_id=asset_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/assets/{asset_id}/qr",
    response_model=AssetQrResponse,
    tags=["asset-management"],
)
def asset_qr(
    asset_id: str,
    service: ServiceDependency,
    _actor: AssetsReadDependency,
) -> dict[str, object]:
    """Return a deterministic QR label containing only a public-safe lookup URL."""

    return _handle_asset_errors(service.asset_management.qr_payload, asset_id=asset_id)


@router.get(
    "/asset-lookup/{lookup_token}",
    response_model=AssetProfileResponse,
    tags=["asset-management"],
)
def lookup_asset_from_qr(
    lookup_token: UUID,
    service: ServiceDependency,
    _actor: AssetsReadDependency,
) -> dict[str, object]:
    """Resolve a QR token after authentication."""

    return _handle_asset_errors(service.asset_management.lookup_qr, token=lookup_token)


@router.get(
    "/locations",
    response_model=list[LocationRecord],
    tags=["asset-management"],
)
def locations(
    service: ServiceDependency,
    _actor: LocationsReadDependency,
    include_archived: bool = False,
) -> list[dict[str, object]]:
    """List hierarchical locations with breadcrumbs."""

    return _handle_asset_errors(
        service.asset_management.list_locations,
        include_archived=include_archived,
    )


@router.post(
    "/locations",
    response_model=LocationRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["asset-management"],
)
def create_location(
    request: LocationCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: LocationsCreateDependency,
) -> dict[str, object]:
    """Create one location node under an optional active parent."""

    return _handle_asset_errors(
        service.asset_management.create_location,
        request.model_dump(),
        audit_context=audit_context(actor, http_request),
    )


@router.patch(
    "/locations/{location_id}",
    response_model=LocationRecord,
    tags=["asset-management"],
)
def update_location(
    location_id: UUID,
    request: LocationUpdateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: LocationsUpdateDependency,
) -> dict[str, object]:
    """Update one location while preventing hierarchy cycles."""

    updates = request.model_dump(exclude_unset=True)
    expected_version = int(updates.pop("expected_version"))
    return _handle_asset_errors(
        service.asset_management.update_location,
        location_id=location_id,
        updates=updates,
        expected_version=expected_version,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/locations/{location_id}/archive",
    response_model=LocationRecord,
    tags=["asset-management"],
)
def archive_location(
    location_id: UUID,
    request: VersionedRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: LocationsArchiveDependency,
) -> dict[str, object]:
    """Archive a location without deleting assigned assets."""

    return _handle_asset_errors(
        service.asset_management.archive_location,
        location_id=location_id,
        expected_version=request.expected_version,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/assets/{asset_id}/attachments",
    response_model=list[AssetAttachmentRecord],
    tags=["asset-management"],
)
def asset_attachments(
    asset_id: str,
    service: ServiceDependency,
    _actor: AttachmentsReadDependency,
) -> list[dict[str, object]]:
    """List active attachment metadata without storage paths."""

    return _handle_asset_errors(
        service.asset_management.list_attachments,
        asset_id=asset_id,
    )


@router.post(
    "/assets/{asset_id}/attachments",
    response_model=AssetAttachmentRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["asset-management"],
)
async def upload_asset_attachment(
    asset_id: str,
    service: ServiceDependency,
    http_request: Request,
    actor: AttachmentsCreateDependency,
    category: Annotated[str, Form(min_length=1, max_length=40)],
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    """Validate and store one bounded PDF or image attachment."""

    try:
        content = await file.read(service.asset_management.attachment_max_size_bytes + 1)
    finally:
        await file.close()
    return _handle_asset_errors(
        service.asset_management.upload_attachment,
        asset_id=asset_id,
        category=category,
        filename=file.filename or "",
        media_type=file.content_type,
        content=content,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/assets/{asset_id}/attachments/{attachment_id}",
    tags=["asset-management"],
)
def download_asset_attachment(
    asset_id: str,
    attachment_id: UUID,
    service: ServiceDependency,
    _actor: AttachmentsReadDependency,
) -> Response:
    """Authorize and download one attachment without exposing its storage key."""

    metadata, content = _handle_asset_errors(
        service.asset_management.download_attachment,
        asset_id=asset_id,
        attachment_id=attachment_id,
    )
    filename = quote(str(metadata["original_filename"]), safe="")
    return Response(
        content=content,
        media_type=str(metadata["media_type"]),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/assets/{asset_id}/attachments/{attachment_id}",
    response_model=AssetAttachmentRecord,
    tags=["asset-management"],
)
def delete_asset_attachment(
    asset_id: str,
    attachment_id: UUID,
    service: ServiceDependency,
    http_request: Request,
    actor: AttachmentsDeleteDependency,
) -> dict[str, object]:
    """Soft-delete attachment metadata and remove local bytes when possible."""

    return _handle_asset_errors(
        service.asset_management.delete_attachment,
        asset_id=asset_id,
        attachment_id=attachment_id,
        audit_context=audit_context(actor, http_request),
    )


@router.get("/assets/{asset_id}/context", response_model=AssetContextResponse, tags=["assets"])
def asset_context(
    asset_id: str,
    service: ServiceDependency,
    _actor: AssetsReadDependency,
) -> dict[str, object]:
    """Return combined asset context for future dashboard and copilot use."""

    return _handle_service_errors(service.get_asset_context, asset_id=asset_id)


@router.get("/assets", response_model=list[AssetOverviewRecord], tags=["assets"])
def list_assets(
    service: ServiceDependency,
    _actor: AssetsReadDependency,
    asset_type: str | None = None,
    location: str | None = None,
    criticality: str | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    """List asset master rows enriched with latest maintenance signals."""

    return _handle_service_errors(
        service.list_assets,
        asset_type=asset_type,
        location=location,
        criticality=criticality,
        status=status,
    )


@router.get(
    "/assets/{asset_id}/details",
    response_model=AssetDetailsResponse,
    tags=["assets"],
)
def asset_details(
    asset_id: str,
    service: ServiceDependency,
    actor: AssetsReadDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict[str, object]:
    """Return one consolidated manager-facing asset view."""

    result = _handle_service_errors(
        service.get_asset_details,
        asset_id=asset_id,
        limit=limit,
    )
    return _scope_asset_details(result, actor)


@router.get("/assets/{asset_id}", response_model=AssetRecord, tags=["assets"])
def asset_master_record(
    asset_id: str,
    service: ServiceDependency,
    _actor: AssetsReadDependency,
) -> dict[str, object]:
    """Return one raw asset master record."""

    return _handle_service_errors(service.get_asset, asset_id=asset_id)


@router.get("/tickets", response_model=list[TicketRecord], tags=["maintenance"])
def tickets(
    service: ServiceDependency,
    actor: TicketsReadDependency,
    asset_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    failure_category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[dict[str, object]]:
    """List raw ticket records with focused filters."""

    return _handle_service_errors(
        service.list_tickets,
        asset_id=asset_id,
        status=status,
        priority=priority,
        failure_category=failure_category,
        technician_id=actor.technician_id if actor.role is Role.TECHNICIAN else None,
        limit=limit,
    )


@router.post(
    "/tickets",
    response_model=TicketRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["maintenance"],
)
def create_ticket(
    request: TicketCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: TicketsCreateDependency,
) -> dict[str, object]:
    """Create one local inspection ticket without recalculating analytics."""

    if request.technician_id != "UNASSIGNED" and not actor.has(Permission.TICKETS_ASSIGN):
        _forbidden("Bạn không có quyền phân công kỹ thuật viên khi tạo ticket.")
    return _handle_write_errors(
        service.create_ticket,
        **request.model_dump(),
        audit_context=audit_context(actor, http_request),
        actor=actor,
    )


@router.patch(
    "/tickets/{ticket_id}",
    response_model=TicketRecord,
    tags=["maintenance"],
)
def update_ticket(
    ticket_id: str,
    request: TicketUpdateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: TicketsUpdateDependency,
) -> dict[str, object]:
    """Assign or move a local ticket through the linear MVP workflow."""

    updates = request.model_dump(exclude_unset=True)
    current_ticket = _handle_write_errors(service.get_ticket, ticket_id=ticket_id)
    _authorize_ticket_update(actor, current_ticket, updates)
    return _handle_write_errors(
        service.update_ticket,
        ticket_id=ticket_id,
        updates=updates,
        audit_context=audit_context(actor, http_request),
        actor=actor,
    )


@router.get(
    "/maintenance/logs",
    response_model=list[MaintenanceLogRecord],
    tags=["maintenance"],
)
def maintenance_logs(
    service: ServiceDependency,
    actor: LogsReadDependency,
    asset_id: str | None = None,
    maintenance_result: str | None = None,
    follow_up_required: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[dict[str, object]]:
    """List maintenance log records with focused filters."""

    return _handle_service_errors(
        service.list_maintenance_logs,
        asset_id=asset_id,
        maintenance_result=maintenance_result,
        follow_up_required=follow_up_required,
        technician_id=actor.technician_id if actor.role is Role.TECHNICIAN else None,
        limit=limit,
    )


@router.post(
    "/maintenance/logs",
    response_model=MaintenanceLogRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["maintenance"],
)
def create_maintenance_log(
    request: MaintenanceLogCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: LogsCreateDependency,
) -> dict[str, object]:
    """Record a technician result for the next analytics batch."""

    current_ticket = _handle_write_errors(service.get_ticket, ticket_id=request.ticket_id)
    if actor.role is Role.TECHNICIAN:
        _require_assigned_ticket(actor, current_ticket)
    return _handle_write_errors(
        service.create_maintenance_log,
        **request.model_dump(),
        audit_context=audit_context(actor, http_request),
    )


def _authorize_ticket_update(
    actor: CurrentUser,
    ticket: dict[str, object],
    updates: dict[str, object],
) -> None:
    if actor.role is Role.TECHNICIAN:
        _require_assigned_ticket(actor, ticket)
        disallowed = set(updates) - {"status", "note", "resolved_at"}
        if disallowed:
            _forbidden("Kỹ thuật viên chỉ được cập nhật trạng thái và ghi chú công việc của mình.")
    if actor.role is Role.HELPDESK:
        disallowed = set(updates) - {"priority", "note"}
        if disallowed:
            _forbidden("Bộ phận tiếp nhận chỉ được cập nhật mức ưu tiên và ghi chú.")
    if "technician_id" in updates and updates["technician_id"] != ticket.get("technician_id"):
        if not actor.has(Permission.TICKETS_ASSIGN):
            _forbidden("Bạn không có quyền phân công kỹ thuật viên.")
    if updates.get("status") == "Đã xử lý" and not actor.has(Permission.TICKETS_RESOLVE):
        _forbidden("Bạn không có quyền hoàn tất ticket kỹ thuật.")


def _require_assigned_ticket(
    actor: CurrentUser,
    ticket: dict[str, object],
) -> None:
    if not actor.technician_id or ticket.get("technician_id") != actor.technician_id:
        _forbidden("Ticket này không được phân công cho kỹ thuật viên đang đăng nhập.")


def _scope_asset_details(
    payload: dict[str, object],
    actor: CurrentUser,
) -> dict[str, object]:
    if actor.role is not Role.TECHNICIAN:
        return payload
    technician_id = actor.technician_id
    scoped = dict(payload)
    scoped["recent_tickets"] = [
        row
        for row in payload.get("recent_tickets", [])
        if isinstance(row, dict) and row.get("technician_id") == technician_id
    ]
    scoped["recent_maintenance_logs"] = [
        row
        for row in payload.get("recent_maintenance_logs", [])
        if isinstance(row, dict) and row.get("technician_id") == technician_id
    ]
    return scoped


def _authorize_asset_profile_update(
    actor: CurrentUser,
    updates: dict[str, object],
) -> None:
    if actor.role is not Role.PROPERTY_MANAGER:
        return
    manager_fields = {
        "location_id",
        "criticality",
        "ownership_type",
        "description",
        "warranty_start_date",
        "warranty_end_date",
        "warranty_provider",
        "warranty_reference",
        "maintenance_interval_days",
        "last_maintenance_date",
        "next_maintenance_date",
    }
    if set(updates) - manager_fields:
        _forbidden(
            "Quản lý cơ sở chỉ được cập nhật vị trí, mức quan trọng, bảo hành và lịch bảo trì."
        )


def _require_lifecycle_manager(actor: CurrentUser) -> None:
    if actor.role not in {Role.ADMINISTRATOR, Role.PROPERTY_MANAGER}:
        _forbidden("Chỉ quản trị viên hoặc quản lý cơ sở được thay đổi lifecycle asset.")


def _forbidden(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _handle_service_errors(function, **kwargs):
    try:
        return function(**kwargs)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProcessedDataNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _handle_write_errors(function, **kwargs):
    try:
        return function(**kwargs)
    except (
        AssetNotFoundError,
        TicketNotFoundError,
        RecordNotFoundError,
        RepositoryRecordNotFoundError,
    ) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        AssetDomainConflictError,
        DuplicateRecordError,
        DuplicateIdentifierError,
        StaleRecordError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityViolationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CsvWriteError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CsvRepositoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _handle_asset_errors(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ArchivedAssetLookupError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    except (AssetDomainNotFoundError, RepositoryRecordNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        AssetDomainConflictError,
        DuplicateIdentifierError,
        IntegrityViolationError,
        StaleRecordError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (AttachmentValidationError, AssetDomainError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    except (
        AttachmentStorageError,
        StorageUnavailableError,
        UnsupportedStorageOperationError,
        RepositoryError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


__all__ = [
    "_copilot_rate_limiter",
    "_copilot_service",
    "_service",
    "ask_copilot",
    "asset_anomaly_history",
    "asset_risk_history",
    "health",
    "list_asset_anomalies",
    "list_asset_risks",
    "maintenance_kpis",
    "preventive_maintenance",
    "rag_readiness",
    "recurring_issues",
    "router",
    "summary",
    "top_asset_risks",
    "QdrantVectorStore",
]
