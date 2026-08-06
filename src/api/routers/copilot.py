"""Copilot endpoint and its request-level protections."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.analytics.errors import AssetNotFoundError, ProcessedDataNotFoundError
from src.api.composition import get_copilot_service
from src.api.schemas import CopilotAskRequest, CopilotAskResponse
from src.rag.copilot import MaintenanceCopilot
from src.rag.embeddings import EmbeddingDependencyError
from src.rag.vector_store import VectorStoreError
from src.security.dependencies import require_permission
from src.security.permissions import Permission
from src.security.rate_limit import RequestRateLimiter, RequestRateLimitExceededError
from src.security.principal import CurrentUser
from src.config.settings import get_settings

router = APIRouter()


def _copilot_service() -> MaintenanceCopilot:
    """Resolve the Copilot through the application composition root."""

    return get_copilot_service()


CopilotDependency = Annotated[MaintenanceCopilot, Depends(_copilot_service)]
CopilotUseDependency = Annotated[
    CurrentUser,
    Depends(require_permission(Permission.COPILOT_USE)),
]


@lru_cache(maxsize=1)
def _copilot_rate_limiter() -> RequestRateLimiter:
    settings = get_settings()
    return RequestRateLimiter(
        max_requests=settings.copilot_rate_limit_requests,
        window_seconds=settings.copilot_rate_limit_window_seconds,
    )


CopilotRateLimiterDependency = Annotated[
    RequestRateLimiter,
    Depends(_copilot_rate_limiter),
]


@router.post("/copilot/ask", response_model=CopilotAskResponse, tags=["copilot"])
def ask_copilot(
    request: CopilotAskRequest,
    copilot: CopilotDependency,
    actor: CopilotUseDependency,
    rate_limiter: CopilotRateLimiterDependency,
) -> dict[str, object]:
    """Ask the grounded RAG Maintenance Copilot with a deterministic fallback."""

    try:
        rate_limiter.consume(str(actor.id))
    except RequestRateLimitExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail="Bạn đã gửi quá nhiều câu hỏi Copilot. Vui lòng thử lại sau.",
            headers={"Retry-After": str(rate_limiter.window_seconds)},
        ) from exc

    try:
        optional_filters = {
            key: value
            for key, value in {
                "document_type": request.document_type,
                "failure_category": request.failure_category,
                "version": request.version,
                "language": request.language,
            }.items()
            if value is not None
        }
        if request.conversation_context is not None:
            optional_filters["conversation_context"] = request.conversation_context.model_dump()
        return copilot.ask(
            question=request.question,
            asset_id=request.asset_id,
            top_k=request.top_k,
            **optional_filters,
        ).to_dict()
    except AssetNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy thiết bị: {request.asset_id or 'không xác định'}.",
        ) from exc
    except ProcessedDataNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (EmbeddingDependencyError, VectorStoreError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Maintenance Copilot tạm thời không truy cập được kho tài liệu.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


__all__ = ["_copilot_rate_limiter", "_copilot_service", "ask_copilot", "router"]
