"""HTTP routes for work-order evidence attachments."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Form, Request, Response, UploadFile, status

from src.maintenance_management.route_support import (
    EvidenceCreate,
    EvidenceDelete,
    EvidenceRead,
    ServiceDependency,
    _handle,
)
from src.maintenance_management.schemas import WorkOrderAttachmentResponse
from src.security.dependencies import audit_context

router = APIRouter()


@router.get(
    "/work-orders/{work_order_id}/attachments",
    response_model=list[WorkOrderAttachmentResponse],
    tags=["work-orders"],
)
def list_work_order_attachments(
    work_order_id: UUID, service: ServiceDependency, actor: EvidenceRead
) -> list[dict[str, object]]:
    return _handle(service.list_evidence, work_order_id=work_order_id, actor=actor)


@router.post(
    "/work-orders/{work_order_id}/attachments",
    response_model=WorkOrderAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["work-orders"],
)
async def upload_work_order_attachment(
    work_order_id: UUID,
    service: ServiceDependency,
    http_request: Request,
    actor: EvidenceCreate,
    category: Annotated[str, Form(min_length=1, max_length=40)],
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    try:
        content = await file.read(service.attachment_max_size_bytes + 1)
    finally:
        await file.close()
    return _handle(
        service.upload_evidence,
        work_order_id=work_order_id,
        category=category,
        filename=file.filename or "",
        claimed_media_type=file.content_type,
        content=content,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )


@router.get(
    "/work-orders/{work_order_id}/attachments/{attachment_id}",
    tags=["work-orders"],
)
def download_work_order_attachment(
    work_order_id: UUID,
    attachment_id: UUID,
    service: ServiceDependency,
    actor: EvidenceRead,
) -> Response:
    download = _handle(
        service.download_evidence,
        work_order_id=work_order_id,
        attachment_id=attachment_id,
        actor=actor,
    )
    filename = quote(download.filename, safe="")
    return Response(
        content=download.content,
        media_type=download.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/work-orders/{work_order_id}/attachments/{attachment_id}",
    response_model=WorkOrderAttachmentResponse,
    tags=["work-orders"],
)
def delete_work_order_attachment(
    work_order_id: UUID,
    attachment_id: UUID,
    service: ServiceDependency,
    http_request: Request,
    actor: EvidenceDelete,
) -> dict[str, object]:
    return _handle(
        service.delete_evidence,
        work_order_id=work_order_id,
        attachment_id=attachment_id,
        actor=actor,
        audit_context=audit_context(actor, http_request),
    )
