"""Pydantic contracts for preventive plans and generation."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from src.maintenance_management.schema_types import (
    IntervalUnitCode,
    PriorityCode,
    VersionRequest,
)

class MaintenancePlanFields(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=200)]
    description: Annotated[str | None, Field(max_length=2000)] = None
    interval_value: Annotated[int, Field(ge=1, le=366)]
    interval_unit: IntervalUnitCode
    start_date: date
    end_date: date | None = None
    local_timezone: Annotated[str, Field(min_length=1, max_length=64)] = "Asia/Ho_Chi_Minh"
    lead_time_days: Annotated[int, Field(ge=0, le=365)] = 7
    grace_period_days: Annotated[int, Field(ge=0, le=365)] = 0
    estimated_duration_minutes: Annotated[int, Field(ge=1, le=10080)]
    default_priority: PriorityCode
    default_assignee_user_id: UUID | None = None
    checklist_template_id: UUID | None = None
    instructions: Annotated[str | None, Field(max_length=4000)] = None
    recurrence_rule: None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "MaintenancePlanFields":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date không được sớm hơn start_date")
        return self


class MaintenancePlanCreateRequest(MaintenancePlanFields):
    plan_code: Annotated[str, Field(min_length=3, max_length=50)]
    asset_id: Annotated[str, Field(min_length=1, max_length=50)]


class MaintenancePlanUpdateRequest(BaseModel):
    expected_version: Annotated[int, Field(ge=1)]
    name: Annotated[str | None, Field(min_length=2, max_length=200)] = None
    description: Annotated[str | None, Field(max_length=2000)] = None
    interval_value: Annotated[int | None, Field(ge=1, le=366)] = None
    interval_unit: IntervalUnitCode | None = None
    start_date: date | None = None
    end_date: date | None = None
    local_timezone: Annotated[str | None, Field(min_length=1, max_length=64)] = None
    lead_time_days: Annotated[int | None, Field(ge=0, le=365)] = None
    grace_period_days: Annotated[int | None, Field(ge=0, le=365)] = None
    estimated_duration_minutes: Annotated[int | None, Field(ge=1, le=10080)] = None
    default_priority: PriorityCode | None = None
    default_assignee_user_id: UUID | None = None
    checklist_template_id: UUID | None = None
    instructions: Annotated[str | None, Field(max_length=4000)] = None


class MaintenancePlanResumeRequest(VersionRequest):
    resume_date: date


class MaintenancePlanArchiveRequest(VersionRequest):
    archive_reason: Annotated[str, Field(min_length=3, max_length=1000)]


class MaintenancePlanResponse(BaseModel):
    id: UUID
    plan_code: str
    name: str
    description: str | None
    asset_id: str
    asset_name: str
    schedule_type: str
    interval_value: int
    interval_unit: str
    recurrence_summary: str
    recurrence_rule: str | None
    start_date: date
    end_date: date | None
    local_timezone: str
    lead_time_days: int
    grace_period_days: int
    next_due_date: date | None
    last_generated_due_date: date | None
    estimated_duration_minutes: int
    default_priority: str
    default_priority_display: str
    default_assignee_user_id: UUID | None
    default_assignee_name: str | None
    checklist_template_id: UUID | None
    checklist_template_name: str | None
    instructions: str | None
    status: str
    status_display: str
    is_active: bool
    paused_at: datetime | None
    archived_at: datetime | None
    archive_reason: str | None
    created_by_user_id: UUID
    updated_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    version: int


class MaintenancePlanPage(BaseModel):
    items: list[MaintenancePlanResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class OccurrenceItem(BaseModel):
    due_date: date
    generated: bool
    generation_release_date: date


class OccurrencePreviewResponse(BaseModel):
    plan_id: UUID
    timezone: str
    date_from: date
    date_to: date
    items: list[OccurrenceItem]

class GenerationRequest(BaseModel):
    as_of_date: date
    plan_id: UUID | None = None


class GenerationPlanReport(BaseModel):
    plan_id: UUID
    plan_code: str
    generated: list[str]
    would_generate_due_dates: list[str] = Field(default_factory=list)
    skipped_due_dates: list[str]
    reason: str | None


class GenerationResponse(BaseModel):
    dry_run: bool
    as_of_date: date
    requested_by_user_id: UUID
    generated_count: int
    would_generate_count: int
    skipped_count: int
    plans: list[GenerationPlanReport]
