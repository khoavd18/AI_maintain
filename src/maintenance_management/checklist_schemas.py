"""Pydantic contracts for immutable checklist templates."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.maintenance_management.schema_types import ChecklistResponseTypeCode

class ChecklistTemplateItemRequest(BaseModel):
    sequence: Annotated[int, Field(ge=1, le=100)]
    instruction: Annotated[str, Field(min_length=2, max_length=2000)]
    response_type: ChecklistResponseTypeCode
    is_required: bool = True
    safety_critical: bool = False
    allow_not_applicable: bool = False
    expected_unit: Annotated[str | None, Field(max_length=40)] = None
    minimum_value: float | None = None
    maximum_value: float | None = None
    guidance: Annotated[str | None, Field(max_length=2000)] = None


class ChecklistTemplateItemResponse(ChecklistTemplateItemRequest):
    id: UUID
    response_type_display: str


class ChecklistTemplateCreateRequest(BaseModel):
    code: Annotated[str, Field(min_length=3, max_length=50)]
    name: Annotated[str, Field(min_length=2, max_length=200)]
    asset_type: Literal["hvac", "pump", "generator"] | None = None
    description: Annotated[str | None, Field(max_length=2000)] = None
    items: Annotated[list[ChecklistTemplateItemRequest], Field(min_length=1, max_length=100)]


class ChecklistTemplateVersionRequest(BaseModel):
    name: Annotated[str | None, Field(min_length=2, max_length=200)] = None
    asset_type: Literal["hvac", "pump", "generator"] | None = None
    description: Annotated[str | None, Field(max_length=2000)] = None
    items: Annotated[
        list[ChecklistTemplateItemRequest] | None, Field(min_length=1, max_length=100)
    ] = None

class ChecklistTemplateResponse(BaseModel):
    id: UUID
    code: str
    name: str
    asset_type: str | None
    description: str | None
    version_number: int
    status: str
    status_display: str
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    version: int
    item_count: int
    items: list[ChecklistTemplateItemResponse]


class ChecklistTemplatePage(BaseModel):
    items: list[ChecklistTemplateResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
