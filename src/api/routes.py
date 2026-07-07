"""FastAPI routes for processed maintenance intelligence outputs."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.schemas import (
    AnomalyRecord,
    AssetContextResponse,
    CopilotAskRequest,
    CopilotAskResponse,
    HealthResponse,
    RiskRecord,
    SummaryResponse,
)
from src.api.services import (
    AssetNotFoundError,
    ProcessedDataNotFoundError,
    ProcessedDataService,
    get_processed_data_service,
)
from src.rag.copilot import MaintenanceCopilot, get_copilot_service
from src.rag.embeddings import EmbeddingDependencyError
from src.rag.vector_store import VectorStoreError

router = APIRouter()


def _service() -> ProcessedDataService:
    return get_processed_data_service()


def _copilot_service() -> MaintenanceCopilot:
    return get_copilot_service()


ServiceDependency = Annotated[ProcessedDataService, Depends(_service)]
CopilotDependency = Annotated[MaintenanceCopilot, Depends(_copilot_service)]


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Return API health."""

    return HealthResponse(status="ok")


@router.get("/summary", response_model=SummaryResponse, tags=["maintenance"])
def summary(service: ServiceDependency) -> dict[str, object]:
    """Return latest maintenance summary metrics."""

    return _handle_service_errors(service.get_summary)


@router.get("/assets/risk", response_model=list[RiskRecord], tags=["risk"])
def list_asset_risks(
    service: ServiceDependency,
    risk_level: str | None = None,
    asset_type: str | None = None,
    location: str | None = None,
    date: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> list[dict[str, object]]:
    """List risk records filtered by Vietnamese business values."""

    return _handle_service_errors(
        service.list_risks,
        risk_level=risk_level,
        asset_type=asset_type,
        location=location,
        date=date,
        limit=limit,
    )


@router.get("/assets/risk/top", response_model=list[RiskRecord], tags=["risk"])
def top_asset_risks(
    service: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=1000)] = 10,
    date: str | None = None,
) -> list[dict[str, object]]:
    """Return top risky assets for a date, defaulting to the latest date."""

    return _handle_service_errors(service.list_top_risks, limit=limit, date=date)


@router.get("/assets/risk/{asset_id}", response_model=list[RiskRecord], tags=["risk"])
def asset_risk_history(asset_id: str, service: ServiceDependency) -> list[dict[str, object]]:
    """Return risk history for one asset."""

    return _handle_service_errors(service.get_asset_risk_history, asset_id=asset_id)


@router.get("/assets/anomalies", response_model=list[AnomalyRecord], tags=["anomalies"])
def list_asset_anomalies(
    service: ServiceDependency,
    asset_type: str | None = None,
    anomaly_type: str | None = None,
    date: str | None = None,
    only_anomalies: bool = True,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[dict[str, object]]:
    """List anomaly records filtered by Vietnamese business values."""

    return _handle_service_errors(
        service.list_anomalies,
        asset_type=asset_type,
        anomaly_type=anomaly_type,
        date=date,
        only_anomalies=only_anomalies,
        limit=limit,
    )


@router.get("/assets/anomalies/{asset_id}", response_model=list[AnomalyRecord], tags=["anomalies"])
def asset_anomaly_history(asset_id: str, service: ServiceDependency) -> list[dict[str, object]]:
    """Return anomaly history for one asset."""

    return _handle_service_errors(service.get_asset_anomaly_history, asset_id=asset_id)


@router.get("/assets/{asset_id}/context", response_model=AssetContextResponse, tags=["assets"])
def asset_context(asset_id: str, service: ServiceDependency) -> dict[str, object]:
    """Return combined asset context for future dashboard and copilot use."""

    return _handle_service_errors(service.get_asset_context, asset_id=asset_id)


@router.post("/copilot/ask", response_model=CopilotAskResponse, tags=["copilot"])
def ask_copilot(
    request: CopilotAskRequest,
    copilot: CopilotDependency,
) -> dict[str, object]:
    """Ask the deterministic RAG Maintenance Copilot."""

    try:
        return copilot.ask(
            question=request.question,
            asset_id=request.asset_id,
            top_k=request.top_k,
        ).to_dict()
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProcessedDataNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (EmbeddingDependencyError, VectorStoreError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _handle_service_errors(function, **kwargs):
    try:
        return function(**kwargs)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProcessedDataNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
