"""Pydantic contracts for executable work orders."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.maintenance_management.schema_types import (
    ChecklistResultCode,
    MaintenanceResultCode,
    PriorityCode,
    VersionRequest,
    WorkOrderTypeCode,
)

class WorkOrderCreateRequest(BaseModel):
    title: Annotated[str, Field(min_length=2, max_length=200)]
    description: Annotated[str | None, Field(max_length=4000)] = None
    work_order_type: WorkOrderTypeCode
    asset_id: Annotated[str, Field(min_length=1, max_length=50)]
    preventive_plan_id: UUID | None = None
    source_ticket_id: Annotated[str | None, Field(max_length=50)] = None
    assigned_to_user_id: UUID | None = None
    priority: PriorityCode
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    due_date: date
    local_timezone: Annotated[str, Field(min_length=1, max_length=64)] = "Asia/Ho_Chi_Minh"
    grace_period_days: Annotated[int, Field(ge=0, le=365)] = 0
    estimated_duration_minutes: Annotated[int, Field(ge=1, le=10080)]
    checklist_template_id: UUID | None = None


class CorrectiveWorkOrderCreateRequest(BaseModel):
    title: Annotated[str | None, Field(min_length=2, max_length=200)] = None
    description: Annotated[str | None, Field(max_length=4000)] = None
    assigned_to_user_id: UUID | None = None
    priority: PriorityCode | None = None
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    due_date: date
    local_timezone: Annotated[str, Field(min_length=1, max_length=64)] = "Asia/Ho_Chi_Minh"
    grace_period_days: Annotated[int, Field(ge=0, le=365)] = 0
    estimated_duration_minutes: Annotated[int, Field(ge=1, le=10080)]
    checklist_template_id: UUID | None = None


class WorkOrderUpdateRequest(BaseModel):
    expected_version: Annotated[int, Field(ge=1)]
    title: Annotated[str | None, Field(min_length=2, max_length=200)] = None
    description: Annotated[str | None, Field(max_length=4000)] = None
    priority: PriorityCode | None = None
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    due_date: date | None = None
    estimated_duration_minutes: Annotated[int | None, Field(ge=1, le=10080)] = None


class WorkOrderAssignRequest(VersionRequest):
    assigned_to_user_id: UUID


class WorkOrderTransitionRequest(VersionRequest):
    target_status: Literal["assigned", "in_progress", "on_hold"]
    hold_reason: Annotated[str | None, Field(max_length=1000)] = None


class WorkOrderChecklistResponseRequest(BaseModel):
    item_id: UUID
    result_status: ChecklistResultCode
    boolean_value: bool | None = None
    numeric_value: float | None = None
    text_value: Annotated[str | None, Field(max_length=2000)] = None
    note: Annotated[str | None, Field(max_length=1000)] = None


class WorkOrderChecklistUpdateRequest(VersionRequest):
    responses: Annotated[
        list[WorkOrderChecklistResponseRequest], Field(min_length=1, max_length=100)
    ]


class WorkOrderCompleteRequest(VersionRequest):
    maintenance_date: date
    inspection_result: Annotated[str, Field(min_length=2, max_length=4000)]
    actions_taken: Annotated[str, Field(min_length=2, max_length=4000)]
    parts_replaced: Annotated[str | None, Field(max_length=2000)] = None
    technician_note: Annotated[str, Field(min_length=2, max_length=4000)]
    maintenance_result: MaintenanceResultCode
    follow_up_required: bool
    completion_summary: Annotated[str, Field(min_length=2, max_length=4000)]
    safety_notes: Annotated[str | None, Field(max_length=4000)] = None
    labor_minutes: Annotated[int, Field(ge=0, le=10080)]


class WorkOrderCancelRequest(VersionRequest):
    cancellation_reason: Annotated[str, Field(min_length=3, max_length=1000)]


class WorkOrderReopenRequest(VersionRequest):
    reason: Annotated[str, Field(min_length=3, max_length=1000)]


class WorkOrderChecklistItemResponse(BaseModel):
    id: UUID
    source_template_item_id: UUID | None
    sequence: int
    instruction: str
    response_type: str
    response_type_display: str
    is_required: bool
    safety_critical: bool
    allow_not_applicable: bool
    expected_unit: str | None
    minimum_value: float | None
    maximum_value: float | None
    guidance: str | None
    result_status: str
    result_status_display: str
    boolean_value: bool | None
    numeric_value: float | None
    text_value: str | None
    note: str | None
    completed_by_user_id: UUID | None
    completed_at: datetime | None


class WorkOrderHistoryItem(BaseModel):
    id: UUID
    occurred_at: datetime
    actor_display_name: str | None
    action: str
    resource_type: str
    resource_id: str | None


class WorkOrderResponse(BaseModel):
    id: UUID
    work_order_number: str
    title: str
    description: str | None
    work_order_type: str
    work_order_type_display: str
    asset_id: str
    asset_name: str
    location: str | None
    preventive_plan_id: UUID | None
    preventive_plan_code: str | None
    source_ticket_id: str | None
    assigned_to_user_id: UUID | None
    assigned_to_name: str | None
    created_by_user_id: UUID
    verified_by_user_id: UUID | None
    verified_by_name: str | None
    maintenance_log_id: str | None
    priority: str
    priority_display: str
    scheduled_start_at: datetime | None
    scheduled_end_at: datetime | None
    due_date: date
    local_timezone: str
    grace_period_days: int
    is_overdue: bool
    estimated_duration_minutes: int
    started_at: datetime | None
    completed_at: datetime | None
    verified_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    completion_summary: str | None
    safety_notes: str | None
    labor_minutes: int | None
    status: str
    status_display: str
    hold_reason: str | None
    created_at: datetime
    updated_at: datetime
    version: int
    checklist: list[WorkOrderChecklistItemResponse]
    history: list[WorkOrderHistoryItem]


class WorkOrderPage(BaseModel):
    items: list[WorkOrderResponse]
    page: int
    page_size: int
    total: int
    total_pages: int

class CalendarOccurrence(BaseModel):
    due_date: date
    generated: bool
    generation_release_date: date
    plan_id: UUID
    plan_code: str
    plan_name: str
    asset_id: str


class ScheduleViewResponse(BaseModel):
    date_from: date
    date_to: date
    work_orders: list[WorkOrderResponse]
    upcoming_occurrences: list[CalendarOccurrence]

class WorkOrderMetricsResponse(BaseModel):
    as_of_date: date
    total_work_orders: int
    by_status: dict[str, int]
    overdue_count: int
    upcoming_preventive_count: int
    completed_count: int
    verified_count: int
    completed_on_time_count: int
    technician_workload: list[dict[str, object]]
    data_notice: str
