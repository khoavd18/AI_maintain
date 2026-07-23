"""Typed FastAPI contracts for the PM5 ticket operations API."""

from datetime import date, datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.ticket_management.domain import (
    CommentVisibility,
    Impact,
    TicketPriority,
    TicketStatus,
    Urgency,
)


class OptionRecord(BaseModel):
    code: str
    display_name: str


class ReferenceRecord(BaseModel):
    id: UUID
    code: str
    name: str
    is_active: bool
    category_id: UUID | None = None


class AssigneeRecord(BaseModel):
    id: UUID
    display_name: str
    role: str
    technician_id: str | None
    is_active: bool


class PriorityMatrixRecord(BaseModel):
    impact: Impact
    urgency: Urgency
    priority: TicketPriority
    priority_display: str


class TicketOptionsResponse(BaseModel):
    categories: list[ReferenceRecord]
    subcategories: list[ReferenceRecord]
    intake_sources: list[ReferenceRecord]
    support_groups: list[ReferenceRecord]
    assignees: list[AssigneeRecord]
    statuses: list[OptionRecord]
    impacts: list[OptionRecord]
    urgencies: list[OptionRecord]
    priorities: list[OptionRecord]
    comment_visibilities: list[OptionRecord]
    sla_statuses: list[OptionRecord]
    queues: list[OptionRecord]
    failure_categories: list[OptionRecord]
    priority_matrix: list[PriorityMatrixRecord]


class PriorityPreviewResponse(BaseModel):
    impact: Impact
    impact_display: str
    urgency: Urgency
    urgency_display: str
    priority: TicketPriority
    priority_display: str


class TicketIntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    asset_id: str = Field(min_length=1, max_length=50)
    issue_description: str = Field(min_length=5, max_length=4000)
    failure_category: Literal[
        "cooling_issue",
        "vibration_issue",
        "electrical_issue",
        "pressure_issue",
        "runtime_issue",
        "sensor_issue",
        "false_alarm",
        "no_failure",
    ] = "no_failure"
    reporter_name: str | None = Field(default=None, max_length=200)
    reporter_email: str | None = Field(default=None, max_length=254)
    reporter_phone: str | None = Field(default=None, max_length=40)
    category_id: UUID | None = None
    subcategory_id: UUID | None = None
    impact: Impact
    urgency: Urgency
    intake_source_id: UUID | None = None
    support_group_id: UUID | None = None
    assigned_user_id: UUID | None = None
    manager_note: str | None = Field(default=None, max_length=1000)


class SlaClockResponse(BaseModel):
    status: str
    status_display: str
    due_at: datetime
    completed_at: datetime | None
    remaining_business_minutes: int | None


class TicketSlaResponse(BaseModel):
    id: UUID
    policy_id: UUID
    policy_code: str
    policy_name: str
    calendar_id: UUID
    calendar_code: str
    timezone: str
    calendar_snapshot: dict[str, Any]
    pause_on_waiting: bool
    due_soon_percent: int
    first_response_target_minutes: int
    resolution_target_minutes: int
    started_at: datetime
    first_response_due_at: datetime
    resolution_due_at: datetime
    first_response_remaining_minutes: int | None
    resolution_remaining_minutes: int | None
    paused_at: datetime | None
    resolution_stopped_at: datetime | None
    occurrence_number: int
    version: int
    first_response: SlaClockResponse
    resolution: SlaClockResponse


class CommentAttachmentResponse(BaseModel):
    asset_attachment_id: UUID | None
    work_order_attachment_id: UUID | None


class TicketCommentResponse(BaseModel):
    id: UUID
    ticket_id: str
    author_user_id: UUID
    author_name: str
    visibility: CommentVisibility
    body: str
    created_at: datetime
    attachments: list[CommentAttachmentResponse]


class TicketSlaEventResponse(BaseModel):
    id: UUID
    event_type: str
    clock_type: str | None
    occurrence_number: int
    occurred_at: datetime
    details: dict[str, Any] | None


class TicketEscalationResponse(BaseModel):
    id: UUID
    ticket_id: str
    rule_code: str
    clock_type: str | None
    occurrence_number: int
    detected_at: datetime
    due_at: datetime | None
    details: dict[str, Any] | None


class LinkedWorkOrderResponse(BaseModel):
    id: UUID
    work_order_number: str
    title: str
    status: str
    priority: str
    due_date: date


class TicketDetailResponse(BaseModel):
    ticket_id: str
    asset_id: str
    issue_description: str
    failure_category: str
    failure_category_display: str
    reporter_name: str | None
    reporter_email: str | None
    reporter_phone: str | None
    reporter_redacted: bool
    category_id: UUID | None
    category_name: str | None
    subcategory_id: UUID | None
    subcategory_name: str | None
    impact: Impact
    impact_display: str
    urgency: Urgency
    urgency_display: str
    priority: TicketPriority
    priority_display: str
    status: TicketStatus
    status_display: str
    intake_source_id: UUID | None
    intake_source_name: str | None
    support_group_id: UUID | None
    support_group_name: str | None
    assigned_user_id: UUID | None
    assigned_user_name: str | None
    technician_id: str
    created_at: datetime
    first_response_at: datetime | None
    waiting_reason: str | None
    waiting_previous_status: str | None
    resolved_at: datetime | None
    closed_at: datetime | None
    reopened_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    reopen_count: int
    manager_note: str | None
    note: str | None
    updated_at: datetime
    version: int
    sla: TicketSlaResponse | None
    comments: list[TicketCommentResponse] = Field(default_factory=list)
    sla_events: list[TicketSlaEventResponse] = Field(default_factory=list)
    escalations: list[TicketEscalationResponse] = Field(default_factory=list)
    linked_work_orders: list[LinkedWorkOrderResponse] = Field(default_factory=list)


class TicketQueuePage(BaseModel):
    items: list[TicketDetailResponse]
    page: int
    page_size: int
    total: int
    queue: str
    queue_display: str
    as_of: datetime


class VersionedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)


class TicketAssignRequest(VersionedAction):
    assigned_user_id: UUID | None = None
    support_group_id: UUID | None = None


class TicketReasonAction(VersionedAction):
    reason: str = Field(min_length=3, max_length=1000)


class TicketResolveRequest(VersionedAction):
    resolved_at: datetime | None = None


class TicketPriorityRequest(TicketReasonAction):
    impact: Impact
    urgency: Urgency


class TicketSlaOverrideRequest(TicketReasonAction):
    policy_id: UUID


class TicketCommentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    visibility: CommentVisibility
    body: str = Field(min_length=1, max_length=4000)
    asset_attachment_ids: list[UUID] = Field(default_factory=list, max_length=10)
    work_order_attachment_ids: list[UUID] = Field(default_factory=list, max_length=10)


class WorkingPeriodRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time


class CalendarHolidayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    holiday_date: date
    name: str = Field(min_length=1, max_length=160)


class BusinessCalendarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=3, max_length=50)
    name: str = Field(min_length=1, max_length=160)
    timezone: str = Field(min_length=1, max_length=64)
    is_active: bool = True
    periods: list[WorkingPeriodRequest] = Field(min_length=1, max_length=21)
    holidays: list[CalendarHolidayRequest] = Field(default_factory=list, max_length=366)


class BusinessCalendarUpdateRequest(BusinessCalendarRequest):
    expected_version: int = Field(ge=1)


class WorkingPeriodResponse(BaseModel):
    weekday: int
    start_time: time
    end_time: time


class CalendarHolidayResponse(BaseModel):
    holiday_date: date
    name: str


class BusinessCalendarResponse(BaseModel):
    id: UUID
    code: str
    name: str
    timezone: str
    is_active: bool
    periods: list[WorkingPeriodResponse]
    holidays: list[CalendarHolidayResponse]
    version: int


class SlaPolicyTargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: TicketPriority
    first_response_minutes: int = Field(gt=0, le=525600)
    resolution_minutes: int = Field(gt=0, le=525600)


class SlaPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=3, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    calendar_id: UUID
    category_id: UUID | None = None
    timezone: str = Field(min_length=1, max_length=64)
    pause_on_waiting: bool = True
    due_soon_percent: int = Field(default=20, ge=1, le=100)
    effective_from: date
    effective_to: date | None = None
    is_active: bool = True
    targets: list[SlaPolicyTargetRequest] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_dates(self) -> "SlaPolicyRequest":
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to không được sớm hơn effective_from.")
        return self


class SlaPolicyUpdateRequest(SlaPolicyRequest):
    expected_version: int = Field(ge=1)


class SlaPolicyResponse(BaseModel):
    id: UUID
    code: str
    name: str
    calendar_id: UUID
    calendar_code: str
    calendar: BusinessCalendarResponse | None
    category_id: UUID | None
    category_name: str | None
    timezone: str
    pause_on_waiting: bool
    due_soon_percent: int
    effective_from: date
    effective_to: date | None
    is_active: bool
    targets: list[SlaPolicyTargetRequest]
    version: int


class SlaSummaryResponse(BaseModel):
    as_of: datetime
    active_count: int
    waiting_count: int
    critical_count: int
    due_soon_count: int
    breached_count: int
    without_sla_count: int


class EscalationEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    as_of: datetime | None = None


class EscalationCandidateResponse(BaseModel):
    ticket_id: str
    rule_code: str
    rule_display: str
    clock_type: str | None
    occurrence_number: int
    due_at: datetime | None


class EscalationEvaluationResponse(BaseModel):
    dry_run: bool
    as_of: datetime
    candidate_count: int
    created_count: int
    candidates: list[EscalationCandidateResponse]


class TicketingSeedResponse(BaseModel):
    categories: int
    subcategories: int
    sources: int
    groups: int
    calendars: int
    policies: int
