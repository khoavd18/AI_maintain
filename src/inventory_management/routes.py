"""FastAPI routes for spare-parts inventory and work-order stock control."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)

from src.asset_management.storage import AttachmentStorageError, AttachmentValidationError
from src.inventory_management.domain import ReservationStatus
from src.inventory_management.schemas import (
    AdjustmentRequest,
    InventoryAttachmentResponse,
    InventoryBalancePage,
    InventoryMetricsResponse,
    InventoryMovementPage,
    InventoryMovementResponse,
    InventoryOptionsResponse,
    LifecycleRequest,
    OpeningBalanceRequest,
    PartCategoryCreateRequest,
    PartCategoryResponse,
    PartConsumptionRequest,
    PartConsumptionResponse,
    PartIssueCreateRequest,
    PartIssueResponse,
    PartReturnCreateRequest,
    PartReturnResponse,
    ReceiptRequest,
    ReorderConfigurationRequest,
    ReorderConfigurationResponse,
    ReservationActionRequest,
    ReservationCreateRequest,
    ReservationReplaceRequest,
    SparePartCreateRequest,
    SparePartPage,
    SparePartResponse,
    SparePartUpdateRequest,
    StockLocationCreateRequest,
    StockLocationResponse,
    StockLocationUpdateRequest,
    StockReservationPage,
    StockReservationResponse,
    TransferRequest,
    TransferResponse,
    UnitOfMeasureCreateRequest,
    UnitOfMeasureResponse,
    WorkOrderPartRequirementCreateRequest,
    WorkOrderPartRequirementResponse,
    WorkOrderPartsSummaryResponse,
)
from src.inventory_management.service import (
    InventoryAuthorizationError,
    InventoryConflictError,
    InventoryDomainError,
    InventoryManagementService,
    InventoryNotFoundError,
    build_inventory_management_service,
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
from src.security.dependencies import audit_context, get_current_user, require_permission
from src.security.permissions import Permission
from src.security.service import CurrentUser

router = APIRouter()


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


@router.get(
    "/inventory/options",
    response_model=InventoryOptionsResponse,
    tags=["inventory"],
)
def inventory_options(
    service: ServiceDependency,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    return _handle(service.options, actor=actor)


@router.get(
    "/part-categories",
    response_model=list[PartCategoryResponse],
    tags=["inventory-master"],
)
def list_part_categories(
    service: ServiceDependency,
    actor: InventoryRead,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    return _handle(
        service.list_categories,
        actor=actor,
        include_inactive=include_inactive,
    )


@router.post(
    "/part-categories",
    response_model=PartCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory-master"],
)
def create_part_category(
    payload: PartCategoryCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PartsManage,
) -> dict[str, Any]:
    return _handle(
        service.create_category,
        payload.model_dump(),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/units-of-measure",
    response_model=list[UnitOfMeasureResponse],
    tags=["inventory-master"],
)
def list_units_of_measure(
    service: ServiceDependency,
    actor: InventoryRead,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    return _handle(
        service.list_units,
        actor=actor,
        include_inactive=include_inactive,
    )


@router.post(
    "/units-of-measure",
    response_model=UnitOfMeasureResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory-master"],
)
def create_unit_of_measure(
    payload: UnitOfMeasureCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PartsManage,
) -> dict[str, Any]:
    return _handle(
        service.create_unit,
        payload.model_dump(),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get("/parts", response_model=SparePartPage, tags=["inventory-master"])
def list_spare_parts(
    service: ServiceDependency,
    actor: InventoryRead,
    category_id: UUID | None = None,
    lifecycle_status: str | None = None,
    asset_type: str | None = None,
    stock_state: str | None = None,
    search: str | None = Query(default=None, max_length=100),
    sort_by: str = "part_number",
    sort_direction: str = "asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, Any]:
    return _handle(
        service.list_parts,
        actor=actor,
        filters={
            "category_id": category_id,
            "lifecycle_status": lifecycle_status,
            "asset_type": asset_type,
            "stock_state": stock_state,
            "search": search,
        },
        sort_by=sort_by,
        sort_direction=sort_direction,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/parts",
    response_model=SparePartResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory-master"],
)
def create_spare_part(
    payload: SparePartCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PartsManage,
) -> dict[str, Any]:
    return _handle(
        service.create_part,
        payload.model_dump(),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/parts/{part_id}",
    response_model=SparePartResponse,
    tags=["inventory-master"],
)
def get_spare_part(
    part_id: UUID,
    service: ServiceDependency,
    actor: InventoryRead,
) -> dict[str, Any]:
    return _handle(service.get_part, part_id, actor=actor)


@router.patch(
    "/parts/{part_id}",
    response_model=SparePartResponse,
    tags=["inventory-master"],
)
def update_spare_part(
    part_id: UUID,
    payload: SparePartUpdateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PartsManage,
) -> dict[str, Any]:
    return _handle(
        service.update_part,
        part_id,
        payload.model_dump(exclude_unset=True),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


def _part_lifecycle_action(
    part_id: UUID,
    action: str,
    payload: LifecycleRequest,
    service: InventoryManagementService,
    http_request: Request,
    actor: CurrentUser,
) -> dict[str, Any]:
    return _handle(
        service.change_part_lifecycle,
        part_id,
        action=action,
        expected_version=payload.expected_version,
        reason=payload.reason,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/parts/{part_id}/activate",
    response_model=SparePartResponse,
    tags=["inventory-master"],
)
def activate_spare_part(
    part_id: UUID,
    payload: LifecycleRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PartsManage,
) -> dict[str, Any]:
    return _part_lifecycle_action(
        part_id, "activate", payload, service, http_request, actor
    )


@router.post(
    "/parts/{part_id}/deactivate",
    response_model=SparePartResponse,
    tags=["inventory-master"],
)
def deactivate_spare_part(
    part_id: UUID,
    payload: LifecycleRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PartsManage,
) -> dict[str, Any]:
    return _part_lifecycle_action(
        part_id, "deactivate", payload, service, http_request, actor
    )


@router.post(
    "/parts/{part_id}/archive",
    response_model=SparePartResponse,
    tags=["inventory-master"],
)
def archive_spare_part(
    part_id: UUID,
    payload: LifecycleRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PartsManage,
) -> dict[str, Any]:
    return _part_lifecycle_action(
        part_id, "archive", payload, service, http_request, actor
    )


@router.post(
    "/parts/{part_id}/restore",
    response_model=SparePartResponse,
    tags=["inventory-master"],
)
def restore_spare_part(
    part_id: UUID,
    payload: LifecycleRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PartsManage,
) -> dict[str, Any]:
    return _part_lifecycle_action(
        part_id, "restore", payload, service, http_request, actor
    )


@router.post(
    "/parts/{part_id}/reorder-configurations",
    response_model=ReorderConfigurationResponse,
    tags=["inventory-master"],
)
def upsert_reorder_configuration(
    part_id: UUID,
    payload: ReorderConfigurationRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PartsManage,
) -> dict[str, Any]:
    return _handle(
        service.upsert_reorder_configuration,
        part_id,
        payload.model_dump(),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/parts/{part_id}/history",
    response_model=InventoryMovementPage,
    tags=["inventory-master"],
)
def spare_part_history(
    part_id: UUID,
    service: ServiceDependency,
    actor: InventoryRead,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, Any]:
    _handle(service.get_part, part_id, actor=actor)
    return _handle(
        service.list_movements,
        actor=actor,
        filters={"part_id": part_id},
        page=page,
        page_size=page_size,
    )


@router.get(
    "/stock-locations",
    response_model=list[StockLocationResponse],
    tags=["inventory-master"],
)
def list_stock_locations(
    service: ServiceDependency,
    actor: InventoryRead,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    return _handle(
        service.list_stock_locations,
        actor=actor,
        include_archived=include_archived,
    )


@router.post(
    "/stock-locations",
    response_model=StockLocationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory-master"],
)
def create_stock_location(
    payload: StockLocationCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: LocationsManage,
) -> dict[str, Any]:
    return _handle(
        service.create_stock_location,
        payload.model_dump(),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.patch(
    "/stock-locations/{location_id}",
    response_model=StockLocationResponse,
    tags=["inventory-master"],
)
def update_stock_location(
    location_id: UUID,
    payload: StockLocationUpdateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: LocationsManage,
) -> dict[str, Any]:
    return _handle(
        service.update_stock_location,
        location_id,
        payload.model_dump(exclude_unset=True),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


def _stock_location_lifecycle_action(
    location_id: UUID,
    action: str,
    payload: LifecycleRequest,
    service: InventoryManagementService,
    http_request: Request,
    actor: CurrentUser,
) -> dict[str, Any]:
    return _handle(
        service.change_stock_location_lifecycle,
        location_id,
        action=action,
        expected_version=payload.expected_version,
        reason=payload.reason,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/stock-locations/{location_id}/activate",
    response_model=StockLocationResponse,
    tags=["inventory-master"],
)
def activate_stock_location(
    location_id: UUID,
    payload: LifecycleRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: LocationsManage,
) -> dict[str, Any]:
    return _stock_location_lifecycle_action(
        location_id, "activate", payload, service, http_request, actor
    )


@router.post(
    "/stock-locations/{location_id}/deactivate",
    response_model=StockLocationResponse,
    tags=["inventory-master"],
)
def deactivate_stock_location(
    location_id: UUID,
    payload: LifecycleRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: LocationsManage,
) -> dict[str, Any]:
    return _stock_location_lifecycle_action(
        location_id, "deactivate", payload, service, http_request, actor
    )


@router.post(
    "/stock-locations/{location_id}/archive",
    response_model=StockLocationResponse,
    tags=["inventory-master"],
)
def archive_stock_location(
    location_id: UUID,
    payload: LifecycleRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: LocationsManage,
) -> dict[str, Any]:
    return _stock_location_lifecycle_action(
        location_id, "archive", payload, service, http_request, actor
    )


@router.post(
    "/stock-locations/{location_id}/restore",
    response_model=StockLocationResponse,
    tags=["inventory-master"],
)
def restore_stock_location(
    location_id: UUID,
    payload: LifecycleRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: LocationsManage,
) -> dict[str, Any]:
    return _stock_location_lifecycle_action(
        location_id, "restore", payload, service, http_request, actor
    )


@router.get(
    "/inventory/balances",
    response_model=InventoryBalancePage,
    tags=["inventory"],
)
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
) -> dict[str, Any]:
    return _handle(
        service.list_balances,
        actor=actor,
        filters={
            "part_id": part_id,
            "stock_location_id": stock_location_id,
            "stock_state": stock_state,
            "search": search,
        },
        sort_by=sort_by,
        sort_direction=sort_direction,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/inventory/low-stock",
    response_model=InventoryBalancePage,
    tags=["inventory"],
)
def list_low_stock(
    service: ServiceDependency,
    actor: InventoryRead,
    stock_location_id: UUID | None = None,
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, Any]:
    return _handle(
        service.list_balances,
        actor=actor,
        filters={
            "stock_location_id": stock_location_id,
            "search": search,
            "low_stock_only": True,
        },
        sort_by="stock_state",
        sort_direction="asc",
        page=page,
        page_size=page_size,
    )


@router.get(
    "/inventory/movements",
    response_model=InventoryMovementPage,
    tags=["inventory"],
)
def list_inventory_movements(
    service: ServiceDependency,
    actor: InventoryRead,
    part_id: UUID | None = None,
    stock_location_id: UUID | None = None,
    movement_type: str | None = None,
    work_order_id: UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, Any]:
    return _handle(
        service.list_movements,
        actor=actor,
        filters={
            "part_id": part_id,
            "stock_location_id": stock_location_id,
            "movement_type": movement_type,
            "work_order_id": work_order_id,
            "occurred_from": occurred_from,
            "occurred_to": occurred_to,
        },
        page=page,
        page_size=page_size,
    )


@router.get(
    "/inventory/metrics",
    response_model=InventoryMetricsResponse,
    tags=["inventory"],
)
def inventory_metrics(
    service: ServiceDependency, actor: InventoryRead
) -> dict[str, Any]:
    return _handle(service.metrics, actor=actor)


@router.post(
    "/inventory/opening-balances",
    response_model=InventoryMovementResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory-actions"],
)
def create_opening_balance(
    payload: OpeningBalanceRequest,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    http_request: Request,
    actor: InventoryReceive,
) -> dict[str, Any]:
    return _handle(
        service.create_opening_balance,
        payload.model_dump(),
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/inventory/receipts",
    response_model=InventoryMovementResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory-actions"],
)
def receive_inventory_stock(
    payload: ReceiptRequest,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    http_request: Request,
    actor: InventoryReceive,
) -> dict[str, Any]:
    return _handle(
        service.receive_stock,
        payload.model_dump(),
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/inventory/transfers",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory-actions"],
)
def transfer_inventory_stock(
    payload: TransferRequest,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    http_request: Request,
    actor: InventoryTransfer,
) -> dict[str, Any]:
    return _handle(
        service.transfer_stock,
        payload.model_dump(),
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/inventory/adjustments",
    response_model=InventoryMovementResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory-actions"],
)
def adjust_inventory_stock(
    payload: AdjustmentRequest,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    http_request: Request,
    actor: InventoryAdjust,
) -> dict[str, Any]:
    return _handle(
        service.adjust_stock,
        payload.model_dump(),
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/inventory/reservations",
    response_model=StockReservationPage,
    tags=["inventory"],
)
def list_stock_reservations(
    service: ServiceDependency,
    actor: InventoryRead,
    work_order_id: UUID | None = None,
    part_id: UUID | None = None,
    stock_location_id: UUID | None = None,
    reservation_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, Any]:
    return _handle(
        service.list_reservations,
        actor=actor,
        filters={
            "work_order_id": work_order_id,
            "part_id": part_id,
            "stock_location_id": stock_location_id,
            "status": reservation_status,
        },
        page=page,
        page_size=page_size,
    )


@router.get(
    "/work-orders/{work_order_id}/parts",
    response_model=WorkOrderPartsSummaryResponse,
    tags=["work-order-inventory"],
)
def get_work_order_parts(
    work_order_id: UUID,
    service: ServiceDependency,
    actor: WorkOrderPartsRead,
) -> dict[str, Any]:
    return _handle(service.work_order_parts, work_order_id, actor=actor)


@router.get(
    "/work-orders/{work_order_id}/part-requirements",
    response_model=list[WorkOrderPartRequirementResponse],
    tags=["work-order-inventory"],
)
def list_work_order_part_requirements(
    work_order_id: UUID,
    service: ServiceDependency,
    actor: WorkOrderPartsRead,
) -> list[dict[str, Any]]:
    summary = _handle(service.work_order_parts, work_order_id, actor=actor)
    return summary["requirements"]


@router.post(
    "/work-orders/{work_order_id}/part-requirements",
    response_model=WorkOrderPartRequirementResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["work-order-inventory"],
)
def create_work_order_part_requirement(
    work_order_id: UUID,
    payload: WorkOrderPartRequirementCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: RequirementsManage,
) -> dict[str, Any]:
    return _handle(
        service.create_requirement,
        work_order_id,
        payload.model_dump(),
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/work-order-part-requirements/{requirement_id}/reservations",
    response_model=StockReservationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["work-order-inventory"],
)
def reserve_requirement_stock(
    requirement_id: UUID,
    payload: ReservationCreateRequest,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    http_request: Request,
    actor: InventoryReserve,
) -> dict[str, Any]:
    return _handle(
        service.reserve_stock,
        requirement_id,
        payload.model_dump(),
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/stock-reservations/{reservation_id}/release",
    response_model=StockReservationResponse,
    tags=["work-order-inventory"],
)
def release_stock_reservation(
    reservation_id: UUID,
    payload: ReservationActionRequest,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    http_request: Request,
    actor: InventoryReserve,
) -> dict[str, Any]:
    return _handle(
        service.close_reservation,
        reservation_id,
        payload.model_dump(),
        target_status=ReservationStatus.RELEASED,
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/stock-reservations/{reservation_id}/expire",
    response_model=StockReservationResponse,
    tags=["work-order-inventory"],
)
def expire_stock_reservation(
    reservation_id: UUID,
    payload: ReservationActionRequest,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    http_request: Request,
    actor: InventoryReserve,
) -> dict[str, Any]:
    return _handle(
        service.close_reservation,
        reservation_id,
        payload.model_dump(),
        target_status=ReservationStatus.EXPIRED,
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/stock-reservations/{reservation_id}/replace",
    response_model=StockReservationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["work-order-inventory"],
)
def replace_stock_reservation(
    reservation_id: UUID,
    payload: ReservationReplaceRequest,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    http_request: Request,
    actor: InventoryReserve,
) -> dict[str, Any]:
    return _handle(
        service.replace_reservation,
        reservation_id,
        payload.model_dump(),
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/work-orders/{work_order_id}/part-issues",
    response_model=PartIssueResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["work-order-inventory"],
)
def issue_work_order_part(
    work_order_id: UUID,
    payload: PartIssueCreateRequest,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    http_request: Request,
    actor: InventoryIssue,
) -> dict[str, Any]:
    return _handle(
        service.issue_stock,
        work_order_id,
        payload.model_dump(),
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/part-issues/{issue_id}/consumptions",
    response_model=PartConsumptionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["work-order-inventory"],
)
def consume_work_order_part(
    issue_id: UUID,
    payload: PartConsumptionRequest,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    http_request: Request,
    actor: InventoryConsume,
) -> dict[str, Any]:
    return _handle(
        service.consume_issue,
        issue_id,
        payload.model_dump(),
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.post(
    "/part-issues/{issue_id}/returns",
    response_model=PartReturnResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["work-order-inventory"],
)
def return_work_order_part(
    issue_id: UUID,
    payload: PartReturnCreateRequest,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    http_request: Request,
    actor: InventoryReturn,
) -> dict[str, Any]:
    return _handle(
        service.return_issue,
        issue_id,
        payload.model_dump(),
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/inventory/movements/{movement_id}/attachments",
    response_model=list[InventoryAttachmentResponse],
    tags=["inventory-evidence"],
)
def list_inventory_evidence(
    movement_id: UUID,
    service: ServiceDependency,
    actor: EvidenceRead,
) -> list[dict[str, Any]]:
    return _handle(service.list_evidence, movement_id, actor=actor)


@router.post(
    "/inventory/movements/{movement_id}/attachments",
    response_model=InventoryAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory-evidence"],
)
async def upload_inventory_evidence(
    movement_id: UUID,
    service: ServiceDependency,
    http_request: Request,
    actor: EvidenceCreate,
    category: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    content = await file.read()
    return _handle(
        service.upload_evidence,
        movement_id,
        category=category,
        filename=file.filename or "",
        claimed_media_type=file.content_type,
        content=content,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/inventory/movements/{movement_id}/attachments/{attachment_id}",
    tags=["inventory-evidence"],
)
def download_inventory_evidence(
    movement_id: UUID,
    attachment_id: UUID,
    service: ServiceDependency,
    actor: EvidenceRead,
) -> Response:
    result = _handle(
        service.download_evidence,
        movement_id,
        attachment_id,
        actor=actor,
    )
    encoded = quote(result.filename)
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{encoded}"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/inventory/movements/{movement_id}/attachments/{attachment_id}",
    response_model=InventoryAttachmentResponse,
    tags=["inventory-evidence"],
)
def delete_inventory_evidence(
    movement_id: UUID,
    attachment_id: UUID,
    service: ServiceDependency,
    http_request: Request,
    actor: EvidenceDelete,
) -> dict[str, Any]:
    return _handle(
        service.delete_evidence,
        movement_id,
        attachment_id,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


def _handle(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except InventoryAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (InventoryNotFoundError, RecordNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        InventoryConflictError,
        DuplicateIdentifierError,
        IntegrityViolationError,
        StaleRecordError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (AttachmentValidationError, InventoryDomainError, ValueError) as exc:
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
