"""Inventory evidence attachment endpoints."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Form, Request, Response, UploadFile, status

from src.inventory_management.schemas import InventoryAttachmentResponse
from src.security.dependencies import audit_context

from .dependencies import EvidenceCreate, EvidenceDelete, EvidenceRead, ServiceDependency
from .error_mapping import _handle

router = APIRouter()


@router.get("/inventory/movements/{movement_id}/attachments", response_model=list[InventoryAttachmentResponse], tags=["inventory-evidence"])
def list_inventory_evidence(movement_id: UUID, service: ServiceDependency, actor: EvidenceRead) -> list[dict[str, object]]:
    return _handle(service.list_evidence, movement_id, actor=actor)


@router.post("/inventory/movements/{movement_id}/attachments", response_model=InventoryAttachmentResponse, status_code=status.HTTP_201_CREATED, tags=["inventory-evidence"])
async def upload_inventory_evidence(movement_id: UUID, service: ServiceDependency, http_request: Request, actor: EvidenceCreate, category: Annotated[str, Form()], file: Annotated[UploadFile, File()]) -> dict[str, object]:
    content = await file.read()
    return _handle(service.upload_evidence, movement_id, category=category, filename=file.filename or "", claimed_media_type=file.content_type, content=content, actor=actor, audit_context=audit_context(actor, http_request))


@router.get("/inventory/movements/{movement_id}/attachments/{attachment_id}", tags=["inventory-evidence"])
def download_inventory_evidence(movement_id: UUID, attachment_id: UUID, service: ServiceDependency, actor: EvidenceRead) -> Response:
    result = _handle(service.download_evidence, movement_id, attachment_id, actor=actor)
    encoded = quote(result.filename)
    return Response(content=result.content, media_type=result.media_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}", "X-Content-Type-Options": "nosniff"})


@router.delete("/inventory/movements/{movement_id}/attachments/{attachment_id}", response_model=InventoryAttachmentResponse, tags=["inventory-evidence"])
def delete_inventory_evidence(movement_id: UUID, attachment_id: UUID, service: ServiceDependency, http_request: Request, actor: EvidenceDelete) -> dict[str, object]:
    return _handle(service.delete_evidence, movement_id, attachment_id, actor=actor, audit_context=audit_context(actor, http_request))
