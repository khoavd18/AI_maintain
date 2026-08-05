"""System and readiness endpoints for the compatibility API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from src.api.schemas import HealthResponse, RagHealthResponse
from src.api.routers.dependencies import get_service
from src.api.services import ProcessedDataService
from src.config.settings import get_settings
from src.rag.vector_store import QdrantVectorStore, VectorStoreError

router = APIRouter()
ServiceDependency = Annotated[ProcessedDataService, Depends(get_service)]


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(service: ServiceDependency) -> dict[str, object]:
    """Return API health."""

    return service.get_health()


@router.get("/health/rag", response_model=RagHealthResponse, tags=["system"])
def rag_readiness(response: Response) -> dict[str, object]:
    """Report Qdrant collection readiness without loading embedding models."""

    settings = get_settings()
    ready = True
    try:
        _qdrant_store(
            url=settings.qdrant_url,
            collection_name=settings.qdrant_collection,
        ).check_health(expected_vector_size=settings.embedding_dimensions)
    except VectorStoreError:
        ready = False
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "degraded",
        "qdrant_ready": ready,
        "collection": settings.qdrant_collection,
        "expected_vector_dimensions": settings.embedding_dimensions,
    }


def _qdrant_store(**kwargs: object) -> QdrantVectorStore:
    """Resolve the store while honoring the historical route-module seam.

    Tests and a few internal operators historically patched
    ``src.api.routes.QdrantVectorStore``.  The lookup remains lazy so the
    production dependency still lives in this focused router while the public
    compatibility façade remains observable.
    """

    from src.api import routes as compatibility_routes

    store_type = getattr(compatibility_routes, "QdrantVectorStore", QdrantVectorStore)
    return store_type(**kwargs)
