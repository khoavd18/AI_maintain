"""Typed FastAPI contracts for spare-parts inventory operations."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

Quantity = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=3)]
NonNegativeQuantity = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=3)]
Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]
PartLifecycleCode = Literal["active", "inactive", "archived"]
StockLocationStatusCode = Literal["active", "inactive", "archived"]
StockLocationTypeCode = Literal[
    "main_store",
    "engineering_store",
    "technician_van",
    "maintenance_room",
    "quarantine",
    "other",
]
RequirementStatusCode = Literal[
    "planned",
    "partially_reserved",
    "reserved",
    "partially_issued",
    "issued",
    "partially_consumed",
    "fulfilled",
    "cancelled",
]
ReservationStatusCode = Literal[
    "active", "partially_issued", "fulfilled", "released", "expired", "replaced"
]
StockStateCode = Literal[
    "healthy", "low_stock", "at_reorder_point", "out_of_stock", "overstock"
]
MovementTypeCode = Literal[
    "opening_balance",
    "receipt",
    "issue",
    "return",
    "transfer_out",
    "transfer_in",
    "adjustment_increase",
    "adjustment_decrease",
    "damaged_scrapped",
]


class OptionRecord(BaseModel):
    code: str
    display_name: str


class InventoryOptionsResponse(BaseModel):
    part_lifecycle_statuses: list[OptionRecord]
    stock_location_statuses: list[OptionRecord]
    stock_location_types: list[OptionRecord]
    movement_types: list[OptionRecord]
    requirement_statuses: list[OptionRecord]
    reservation_statuses: list[OptionRecord]
    stock_states: list[OptionRecord]
    attachment_categories: list[OptionRecord]
    compatible_asset_types: list[OptionRecord]


class PartCategoryCreateRequest(BaseModel):
    code: Annotated[str, Field(min_length=2, max_length=50)]
    name_vi: Annotated[str, Field(min_length=2, max_length=200)]
    name_en: Annotated[str | None, Field(max_length=200)] = None
    description: Annotated[str | None, Field(max_length=1000)] = None


class PartCategoryResponse(BaseModel):
    id: UUID
    code: str
    name_vi: str
    name_en: str | None
    description: str | None
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class UnitOfMeasureCreateRequest(BaseModel):
    code: Annotated[str, Field(min_length=1, max_length=20)]
    name_vi: Annotated[str, Field(min_length=1, max_length=120)]
    name_en: Annotated[str | None, Field(max_length=120)] = None
    symbol: Annotated[str, Field(min_length=1, max_length=20)]
    quantity_precision: Annotated[int, Field(ge=0, le=3)] = 0


class UnitOfMeasureResponse(BaseModel):
    id: UUID
    code: str
    name_vi: str
    name_en: str | None
    symbol: str
    quantity_precision: int
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class SparePartCreateRequest(BaseModel):
    part_number: Annotated[str, Field(min_length=2, max_length=80)]
    name_vi: Annotated[str, Field(min_length=2, max_length=200)]
    name_en: Annotated[str | None, Field(max_length=200)] = None
    category_id: UUID
    unit_of_measure_id: UUID
    manufacturer_reference: Annotated[str | None, Field(max_length=200)] = None
    compatible_asset_types: Annotated[
        list[Literal["hvac", "pump", "generator"]], Field(max_length=3)
    ] = []
    minimum_stock: NonNegativeQuantity = Decimal("0")
    reorder_point: NonNegativeQuantity = Decimal("0")
    maximum_stock: NonNegativeQuantity | None = None
    unit_cost: Money | None = None
    currency_code: Annotated[str | None, Field(min_length=3, max_length=3)] = None

    @model_validator(mode="after")
    def validate_thresholds(self) -> "SparePartCreateRequest":
        _validate_thresholds(
            self.minimum_stock, self.reorder_point, self.maximum_stock
        )
        if (self.unit_cost is None) != (self.currency_code is None):
            raise ValueError("unit_cost và currency_code phải được cung cấp cùng nhau.")
        return self


class SparePartUpdateRequest(BaseModel):
    expected_version: Annotated[int, Field(ge=1)]
    name_vi: Annotated[str | None, Field(min_length=2, max_length=200)] = None
    name_en: Annotated[str | None, Field(max_length=200)] = None
    category_id: UUID | None = None
    manufacturer_reference: Annotated[str | None, Field(max_length=200)] = None
    compatible_asset_types: Annotated[
        list[Literal["hvac", "pump", "generator"]] | None, Field(max_length=3)
    ] = None
    unit_cost: Money | None = None
    currency_code: Annotated[str | None, Field(min_length=3, max_length=3)] = None


class LifecycleRequest(BaseModel):
    expected_version: Annotated[int, Field(ge=1)]
    reason: Annotated[str | None, Field(min_length=3, max_length=1000)] = None


class SparePartResponse(BaseModel):
    id: UUID
    part_number: str
    name_vi: str
    name_en: str | None
    category_id: UUID
    category_code: str
    category_name_vi: str
    unit_of_measure_id: UUID
    unit_code: str
    unit_name_vi: str
    unit_symbol: str
    quantity_precision: int
    manufacturer_reference: str | None
    compatible_asset_types: list[str]
    lifecycle_status: PartLifecycleCode
    lifecycle_status_display: str
    minimum_stock: NonNegativeQuantity
    reorder_point: NonNegativeQuantity
    maximum_stock: NonNegativeQuantity | None
    unit_cost: Money | None
    currency_code: str | None
    total_on_hand_quantity: NonNegativeQuantity
    total_reserved_quantity: NonNegativeQuantity
    total_available_quantity: NonNegativeQuantity
    stock_state: StockStateCode
    stock_state_display: str
    archived_at: datetime | None
    archive_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class SparePartPage(BaseModel):
    items: list[SparePartResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class StockLocationCreateRequest(BaseModel):
    code: Annotated[str, Field(min_length=2, max_length=50)]
    name: Annotated[str, Field(min_length=2, max_length=200)]
    location_type: StockLocationTypeCode
    description: Annotated[str | None, Field(max_length=1000)] = None


class StockLocationUpdateRequest(BaseModel):
    expected_version: Annotated[int, Field(ge=1)]
    name: Annotated[str | None, Field(min_length=2, max_length=200)] = None
    location_type: StockLocationTypeCode | None = None
    description: Annotated[str | None, Field(max_length=1000)] = None


class StockLocationResponse(BaseModel):
    id: UUID
    code: str
    name: str
    location_type: StockLocationTypeCode
    location_type_display: str
    description: str | None
    lifecycle_status: StockLocationStatusCode
    lifecycle_status_display: str
    archived_at: datetime | None
    archive_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class ReorderConfigurationRequest(BaseModel):
    stock_location_id: UUID
    minimum_stock: NonNegativeQuantity
    reorder_point: NonNegativeQuantity
    maximum_stock: NonNegativeQuantity | None = None
    expected_version: Annotated[int | None, Field(ge=1)] = None

    @model_validator(mode="after")
    def validate_thresholds(self) -> "ReorderConfigurationRequest":
        _validate_thresholds(
            self.minimum_stock, self.reorder_point, self.maximum_stock
        )
        return self


class ReorderConfigurationResponse(BaseModel):
    id: UUID
    part_id: UUID
    stock_location_id: UUID
    stock_location_code: str
    stock_location_name: str
    minimum_stock: NonNegativeQuantity
    reorder_point: NonNegativeQuantity
    maximum_stock: NonNegativeQuantity | None
    version: int
    created_at: datetime
    updated_at: datetime


class InventoryBalanceResponse(BaseModel):
    id: UUID
    part_id: UUID
    part_number: str
    part_name_vi: str
    lifecycle_status: PartLifecycleCode
    stock_location_id: UUID
    stock_location_code: str
    stock_location_name: str
    stock_location_status: StockLocationStatusCode
    unit_of_measure_id: UUID
    unit_code: str
    unit_symbol: str
    on_hand_quantity: NonNegativeQuantity
    reserved_quantity: NonNegativeQuantity
    available_quantity: NonNegativeQuantity
    minimum_stock: NonNegativeQuantity
    reorder_point: NonNegativeQuantity
    maximum_stock: NonNegativeQuantity | None
    stock_state: StockStateCode
    stock_state_display: str
    suggested_reorder_quantity: NonNegativeQuantity
    version: int
    updated_at: datetime


class InventoryBalancePage(BaseModel):
    items: list[InventoryBalanceResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class StockOperationBase(BaseModel):
    part_id: UUID
    stock_location_id: UUID
    quantity: Quantity
    business_reference: Annotated[str, Field(min_length=2, max_length=160)]
    occurred_at: datetime | None = None
    reason: Annotated[str, Field(min_length=3, max_length=1000)]
    unit_cost_snapshot: Money | None = None


class OpeningBalanceRequest(StockOperationBase):
    pass


class ReceiptRequest(StockOperationBase):
    pass


class TransferRequest(BaseModel):
    part_id: UUID
    source_stock_location_id: UUID
    destination_stock_location_id: UUID
    quantity: Quantity
    business_reference: Annotated[str, Field(min_length=2, max_length=160)]
    occurred_at: datetime | None = None
    reason: Annotated[str, Field(min_length=3, max_length=1000)]

    @model_validator(mode="after")
    def validate_locations(self) -> "TransferRequest":
        if self.source_stock_location_id == self.destination_stock_location_id:
            raise ValueError("Kho nguồn và kho đích phải khác nhau.")
        return self


class AdjustmentRequest(StockOperationBase):
    adjustment_type: Literal["increase", "decrease", "damaged_scrapped"]
    supporting_note: Annotated[str, Field(min_length=3, max_length=2000)]


class InventoryMovementResponse(BaseModel):
    id: UUID
    movement_number: str
    part_id: UUID
    part_number: str
    part_name_vi: str
    stock_location_id: UUID
    stock_location_code: str
    stock_location_name: str
    quantity: Quantity
    unit_of_measure_id: UUID
    unit_code: str
    unit_symbol: str
    movement_type: MovementTypeCode
    movement_type_display: str
    business_reference: str
    actor_user_id: UUID
    actor_display_name: str
    occurred_at: datetime
    reason: str
    work_order_id: UUID | None
    work_order_number: str | None
    source_location_id: UUID | None
    source_location_code: str | None
    destination_location_id: UUID | None
    destination_location_code: str | None
    transfer_group_id: UUID | None
    unit_cost_snapshot: Money | None
    resulting_on_hand_quantity: NonNegativeQuantity
    resulting_reserved_quantity: NonNegativeQuantity
    resulting_available_quantity: NonNegativeQuantity
    idempotency_key: str
    created_at: datetime


class InventoryMovementPage(BaseModel):
    items: list[InventoryMovementResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class TransferResponse(BaseModel):
    transfer_group_id: UUID
    transfer_out: InventoryMovementResponse
    transfer_in: InventoryMovementResponse


class WorkOrderPartRequirementCreateRequest(BaseModel):
    part_id: UUID
    planned_quantity: Quantity
    required_by_date: date | None = None
    source_stock_location_id: UUID
    notes: Annotated[str | None, Field(max_length=1000)] = None


class WorkOrderPartRequirementResponse(BaseModel):
    id: UUID
    work_order_id: UUID
    work_order_number: str
    part_id: UUID
    part_number: str
    part_name_vi: str
    unit_code: str
    unit_symbol: str
    planned_quantity: Quantity
    required_by_date: date | None
    source_stock_location_id: UUID
    source_stock_location_code: str
    source_stock_location_name: str
    status: RequirementStatusCode
    status_display: str
    notes: str | None
    reserved_quantity: NonNegativeQuantity
    issued_quantity: NonNegativeQuantity
    returned_quantity: NonNegativeQuantity
    consumed_quantity: NonNegativeQuantity
    outstanding_issued_quantity: NonNegativeQuantity
    shortage_quantity: NonNegativeQuantity
    version: int
    created_at: datetime
    updated_at: datetime


class ReservationCreateRequest(BaseModel):
    quantity: Quantity
    expected_requirement_version: Annotated[int, Field(ge=1)]
    expires_at: datetime | None = None
    reason: Annotated[str, Field(min_length=3, max_length=1000)]


class ReservationActionRequest(BaseModel):
    expected_version: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=3, max_length=1000)]


class ReservationReplaceRequest(BaseModel):
    quantity: Quantity
    stock_location_id: UUID
    expected_version: Annotated[int, Field(ge=1)]
    expires_at: datetime | None = None
    reason: Annotated[str, Field(min_length=3, max_length=1000)]


class ReservationEventResponse(BaseModel):
    id: UUID
    event_type: Literal[
        "reserved", "released", "expired", "replaced", "issued", "fulfilled"
    ]
    quantity: Quantity
    reason: str
    actor_user_id: UUID
    actor_display_name: str
    occurred_at: datetime


class StockReservationResponse(BaseModel):
    id: UUID
    reservation_number: str
    requirement_id: UUID
    work_order_id: UUID
    work_order_number: str
    part_id: UUID
    part_number: str
    part_name_vi: str
    stock_location_id: UUID
    stock_location_code: str
    stock_location_name: str
    occurrence_number: int
    quantity: Quantity
    issued_quantity: NonNegativeQuantity
    remaining_quantity: NonNegativeQuantity
    status: ReservationStatusCode
    status_display: str
    expires_at: datetime | None
    replaced_by_reservation_id: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    events: list[ReservationEventResponse] = []


class StockReservationPage(BaseModel):
    items: list[StockReservationResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class PartIssueCreateRequest(BaseModel):
    part_id: UUID
    stock_location_id: UUID
    quantity: Quantity
    requirement_id: UUID | None = None
    reservation_id: UUID | None = None
    issued_to_user_id: UUID | None = None
    issued_at: datetime | None = None
    reason: Annotated[str, Field(min_length=3, max_length=1000)]


class PartConsumptionRequest(BaseModel):
    quantity: Quantity
    consumed_at: datetime | None = None
    note: Annotated[str | None, Field(max_length=1000)] = None


class PartReturnCreateRequest(BaseModel):
    stock_location_id: UUID
    quantity: Quantity
    returned_at: datetime | None = None
    reason: Annotated[str, Field(min_length=3, max_length=1000)]


class PartConsumptionResponse(BaseModel):
    id: UUID
    issue_id: UUID
    work_order_id: UUID
    part_id: UUID
    quantity: Quantity
    consumed_by_user_id: UUID
    consumed_by_display_name: str
    consumed_at: datetime
    note: str | None


class PartReturnResponse(BaseModel):
    id: UUID
    return_number: str
    issue_id: UUID
    work_order_id: UUID
    part_id: UUID
    part_number: str
    stock_location_id: UUID
    stock_location_code: str
    quantity: Quantity
    returned_by_user_id: UUID
    returned_by_display_name: str
    returned_at: datetime
    reason: str
    movement_id: UUID


class PartIssueResponse(BaseModel):
    id: UUID
    issue_number: str
    work_order_id: UUID
    work_order_number: str
    requirement_id: UUID | None
    reservation_id: UUID | None
    part_id: UUID
    part_number: str
    part_name_vi: str
    stock_location_id: UUID
    stock_location_code: str
    stock_location_name: str
    unit_code: str
    unit_symbol: str
    quantity: Quantity
    reserved_quantity_used: NonNegativeQuantity
    consumed_quantity: NonNegativeQuantity
    returned_quantity: NonNegativeQuantity
    outstanding_quantity: NonNegativeQuantity
    issued_to_user_id: UUID | None
    issued_to_display_name: str | None
    issued_by_user_id: UUID
    issued_by_display_name: str
    issued_at: datetime
    reason: str
    movement_id: UUID
    consumptions: list[PartConsumptionResponse] = []
    returns: list[PartReturnResponse] = []


class WorkOrderPartsSummaryResponse(BaseModel):
    work_order_id: UUID
    work_order_number: str
    work_order_status: str
    work_order_status_display: str
    assigned_to_user_id: UUID | None
    requirements: list[WorkOrderPartRequirementResponse]
    reservations: list[StockReservationResponse]
    issues: list[PartIssueResponse]
    movements: list[InventoryMovementResponse]
    total_planned_quantity: NonNegativeQuantity
    total_reserved_quantity: NonNegativeQuantity
    total_issued_quantity: NonNegativeQuantity
    total_returned_quantity: NonNegativeQuantity
    net_consumed_quantity: NonNegativeQuantity
    open_shortage_count: int
    has_unresolved_issued_stock: bool
    completion_policy: str
    completion_warning: str | None


class InventoryMetricsResponse(BaseModel):
    total_active_parts: int
    total_on_hand_units: NonNegativeQuantity
    total_reserved_units: NonNegativeQuantity
    total_available_units: NonNegativeQuantity
    low_stock_parts: int
    out_of_stock_parts: int
    open_shortages: int
    work_orders_waiting_for_parts: int
    movements_by_type: dict[str, int]
    data_notice: str


class InventoryAttachmentResponse(BaseModel):
    id: UUID
    movement_id: UUID
    category: Literal[
        "adjustment_evidence",
        "damage_evidence",
        "receipt_evidence",
        "transfer_evidence",
        "other",
    ]
    original_filename: str
    media_type: str
    size_bytes: int
    checksum: str
    uploaded_by_user_id: UUID
    created_at: datetime
    deleted_at: datetime | None


def _validate_thresholds(
    minimum_stock: Decimal,
    reorder_point: Decimal,
    maximum_stock: Decimal | None,
) -> None:
    if reorder_point < minimum_stock:
        raise ValueError("reorder_point phải lớn hơn hoặc bằng minimum_stock.")
    if maximum_stock is not None and maximum_stock < reorder_point:
        raise ValueError("maximum_stock phải lớn hơn hoặc bằng reorder_point.")
