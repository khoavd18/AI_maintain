"""Inventory catalogue and lifecycle endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from src.inventory_management.schemas import (
    InventoryMovementPage,
    InventoryOptionsResponse,
    LifecycleRequest,
    PartCategoryCreateRequest,
    PartCategoryResponse,
    ReorderConfigurationRequest,
    ReorderConfigurationResponse,
    SparePartCreateRequest,
    SparePartPage,
    SparePartResponse,
    SparePartUpdateRequest,
    StockLocationCreateRequest,
    StockLocationResponse,
    StockLocationUpdateRequest,
    UnitOfMeasureCreateRequest,
    UnitOfMeasureResponse,
)
from src.inventory_management.service import InventoryManagementService
from src.security.dependencies import audit_context
from src.security.service import CurrentUser

from .dependencies import (
    InventoryRead,
    LocationsManage,
    PartsManage,
    ServiceDependency,
    get_current_user as _get_current_user,
)
from .error_mapping import _handle

router = APIRouter()


@router.get("/inventory/options", response_model=InventoryOptionsResponse, tags=["inventory"])
def inventory_options(
    service: ServiceDependency,
    actor: Annotated[CurrentUser, Depends(_get_current_user)],
) -> dict[str, object]:
    return _handle(service.options, actor=actor)


@router.get("/part-categories", response_model=list[PartCategoryResponse], tags=["inventory-master"])
def list_part_categories(
    service: ServiceDependency,
    actor: InventoryRead,
    include_inactive: bool = False,
) -> list[dict[str, object]]:
    return _handle(service.list_categories, actor=actor, include_inactive=include_inactive)


@router.post("/part-categories", response_model=PartCategoryResponse, status_code=201, tags=["inventory-master"])
def create_part_category(
    payload: PartCategoryCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PartsManage,
) -> dict[str, object]:
    return _handle(service.create_category, payload.model_dump(), actor=actor, audit_context=audit_context(actor, http_request))


@router.get("/units-of-measure", response_model=list[UnitOfMeasureResponse], tags=["inventory-master"])
def list_units_of_measure(
    service: ServiceDependency,
    actor: InventoryRead,
    include_inactive: bool = False,
) -> list[dict[str, object]]:
    return _handle(service.list_units, actor=actor, include_inactive=include_inactive)


@router.post("/units-of-measure", response_model=UnitOfMeasureResponse, status_code=201, tags=["inventory-master"])
def create_unit_of_measure(
    payload: UnitOfMeasureCreateRequest,
    service: ServiceDependency,
    http_request: Request,
    actor: PartsManage,
) -> dict[str, object]:
    return _handle(service.create_unit, payload.model_dump(), actor=actor, audit_context=audit_context(actor, http_request))


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
) -> dict[str, object]:
    return _handle(
        service.list_parts,
        actor=actor,
        filters={"category_id": category_id, "lifecycle_status": lifecycle_status, "asset_type": asset_type, "stock_state": stock_state, "search": search},
        sort_by=sort_by,
        sort_direction=sort_direction,
        page=page,
        page_size=page_size,
    )


@router.post("/parts", response_model=SparePartResponse, status_code=201, tags=["inventory-master"])
def create_spare_part(payload: SparePartCreateRequest, service: ServiceDependency, http_request: Request, actor: PartsManage) -> dict[str, object]:
    return _handle(service.create_part, payload.model_dump(), actor=actor, audit_context=audit_context(actor, http_request))


@router.get("/parts/{part_id}", response_model=SparePartResponse, tags=["inventory-master"])
def get_spare_part(part_id: UUID, service: ServiceDependency, actor: InventoryRead) -> dict[str, object]:
    return _handle(service.get_part, part_id, actor=actor)


@router.patch("/parts/{part_id}", response_model=SparePartResponse, tags=["inventory-master"])
def update_spare_part(part_id: UUID, payload: SparePartUpdateRequest, service: ServiceDependency, http_request: Request, actor: PartsManage) -> dict[str, object]:
    return _handle(service.update_part, part_id, payload.model_dump(exclude_unset=True), actor=actor, audit_context=audit_context(actor, http_request))


def _part_lifecycle_action(part_id: UUID, action: str, payload: LifecycleRequest, service: InventoryManagementService, http_request: Request, actor: CurrentUser) -> dict[str, object]:
    return _handle(service.change_part_lifecycle, part_id, action=action, expected_version=payload.expected_version, reason=payload.reason, actor=actor, audit_context=audit_context(actor, http_request))


@router.post("/parts/{part_id}/activate", response_model=SparePartResponse, tags=["inventory-master"])
def activate_spare_part(part_id: UUID, payload: LifecycleRequest, service: ServiceDependency, http_request: Request, actor: PartsManage) -> dict[str, object]:
    return _part_lifecycle_action(part_id, "activate", payload, service, http_request, actor)


@router.post("/parts/{part_id}/deactivate", response_model=SparePartResponse, tags=["inventory-master"])
def deactivate_spare_part(part_id: UUID, payload: LifecycleRequest, service: ServiceDependency, http_request: Request, actor: PartsManage) -> dict[str, object]:
    return _part_lifecycle_action(part_id, "deactivate", payload, service, http_request, actor)


@router.post("/parts/{part_id}/archive", response_model=SparePartResponse, tags=["inventory-master"])
def archive_spare_part(part_id: UUID, payload: LifecycleRequest, service: ServiceDependency, http_request: Request, actor: PartsManage) -> dict[str, object]:
    return _part_lifecycle_action(part_id, "archive", payload, service, http_request, actor)


@router.post("/parts/{part_id}/restore", response_model=SparePartResponse, tags=["inventory-master"])
def restore_spare_part(part_id: UUID, payload: LifecycleRequest, service: ServiceDependency, http_request: Request, actor: PartsManage) -> dict[str, object]:
    return _part_lifecycle_action(part_id, "restore", payload, service, http_request, actor)


@router.post("/parts/{part_id}/reorder-configurations", response_model=ReorderConfigurationResponse, tags=["inventory-master"])
def upsert_reorder_configuration(part_id: UUID, payload: ReorderConfigurationRequest, service: ServiceDependency, http_request: Request, actor: PartsManage) -> dict[str, object]:
    return _handle(service.upsert_reorder_configuration, part_id, payload.model_dump(), actor=actor, audit_context=audit_context(actor, http_request))


@router.get("/parts/{part_id}/history", response_model=InventoryMovementPage, tags=["inventory-master"])
def spare_part_history(part_id: UUID, service: ServiceDependency, actor: InventoryRead, page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=200)) -> dict[str, object]:
    _handle(service.get_part, part_id, actor=actor)
    return _handle(service.list_movements, actor=actor, filters={"part_id": part_id}, page=page, page_size=page_size)


@router.get("/stock-locations", response_model=list[StockLocationResponse], tags=["inventory-master"])
def list_stock_locations(service: ServiceDependency, actor: InventoryRead, include_archived: bool = False) -> list[dict[str, object]]:
    return _handle(service.list_stock_locations, actor=actor, include_archived=include_archived)


@router.post("/stock-locations", response_model=StockLocationResponse, status_code=201, tags=["inventory-master"])
def create_stock_location(payload: StockLocationCreateRequest, service: ServiceDependency, http_request: Request, actor: LocationsManage) -> dict[str, object]:
    return _handle(service.create_stock_location, payload.model_dump(), actor=actor, audit_context=audit_context(actor, http_request))


@router.patch("/stock-locations/{location_id}", response_model=StockLocationResponse, tags=["inventory-master"])
def update_stock_location(location_id: UUID, payload: StockLocationUpdateRequest, service: ServiceDependency, http_request: Request, actor: LocationsManage) -> dict[str, object]:
    return _handle(service.update_stock_location, location_id, payload.model_dump(exclude_unset=True), actor=actor, audit_context=audit_context(actor, http_request))


def _stock_location_lifecycle_action(location_id: UUID, action: str, payload: LifecycleRequest, service: InventoryManagementService, http_request: Request, actor: CurrentUser) -> dict[str, object]:
    return _handle(service.change_stock_location_lifecycle, location_id, action=action, expected_version=payload.expected_version, reason=payload.reason, actor=actor, audit_context=audit_context(actor, http_request))


@router.post("/stock-locations/{location_id}/activate", response_model=StockLocationResponse, tags=["inventory-master"])
def activate_stock_location(location_id: UUID, payload: LifecycleRequest, service: ServiceDependency, http_request: Request, actor: LocationsManage) -> dict[str, object]:
    return _stock_location_lifecycle_action(location_id, "activate", payload, service, http_request, actor)


@router.post("/stock-locations/{location_id}/deactivate", response_model=StockLocationResponse, tags=["inventory-master"])
def deactivate_stock_location(location_id: UUID, payload: LifecycleRequest, service: ServiceDependency, http_request: Request, actor: LocationsManage) -> dict[str, object]:
    return _stock_location_lifecycle_action(location_id, "deactivate", payload, service, http_request, actor)


@router.post("/stock-locations/{location_id}/archive", response_model=StockLocationResponse, tags=["inventory-master"])
def archive_stock_location(location_id: UUID, payload: LifecycleRequest, service: ServiceDependency, http_request: Request, actor: LocationsManage) -> dict[str, object]:
    return _stock_location_lifecycle_action(location_id, "archive", payload, service, http_request, actor)


@router.post("/stock-locations/{location_id}/restore", response_model=StockLocationResponse, tags=["inventory-master"])
def restore_stock_location(location_id: UUID, payload: LifecycleRequest, service: ServiceDependency, http_request: Request, actor: LocationsManage) -> dict[str, object]:
    return _stock_location_lifecycle_action(location_id, "restore", payload, service, http_request, actor)
