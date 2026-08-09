"""Shared type aliases and small contracts for maintenance schemas."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

PriorityCode = Literal["low", "medium", "high", "critical"]
IntervalUnitCode = Literal["day", "week", "month", "year"]
PlanStatusCode = Literal["active", "paused", "archived"]
WorkOrderTypeCode = Literal["preventive", "corrective", "inspection", "emergency"]
WorkOrderStatusCode = Literal[
    "planned",
    "assigned",
    "in_progress",
    "on_hold",
    "completed",
    "verified",
    "cancelled",
]
ChecklistResponseTypeCode = Literal["checkbox", "pass_fail", "numeric", "text"]
ChecklistResultCode = Literal["completed", "pass", "fail", "not_applicable"]
MaintenanceResultCode = Literal[
    "resolved", "partially_resolved", "monitoring_required", "vendor_required"
]

class OptionRecord(BaseModel):
    code: str
    display_name: str


class TechnicianOption(BaseModel):
    id: UUID
    display_name: str
    role: str
    technician_id: str
    is_active: bool


class MaintenanceOptionsResponse(BaseModel):
    plan_statuses: list[OptionRecord]
    interval_units: list[OptionRecord]
    work_order_types: list[OptionRecord]
    work_order_statuses: list[OptionRecord]
    checklist_response_types: list[OptionRecord]
    priorities: list[OptionRecord]
    maintenance_results: list[OptionRecord]
    evidence_categories: list[OptionRecord]
    technicians: list[TechnicianOption]

class VersionRequest(BaseModel):
    expected_version: Annotated[int, Field(ge=1)]
