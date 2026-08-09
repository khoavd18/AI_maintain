"""Pydantic contracts for work-order evidence metadata."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

class WorkOrderAttachmentResponse(BaseModel):
    id: UUID
    work_order_id: UUID
    asset_id: str
    category: str
    category_display: str
    original_filename: str
    media_type: str
    size_bytes: int
    checksum: str
    uploaded_by_user_id: UUID
    created_at: datetime
    deleted_at: datetime | None
    deleted_by_user_id: UUID | None
