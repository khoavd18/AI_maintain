"""FastAPI routes for processed maintenance intelligence outputs."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.csv_repository import (
    CsvRepositoryError,
    CsvWriteError,
    DuplicateRecordError,
    RecordNotFoundError,
)
from src.api.schemas import (
    AnomalyRecord,
    AssetContextResponse,
    AssetDetailsResponse,
    AssetOverviewRecord,
    AssetRecord,
    CopilotAskRequest,
    CopilotAskResponse,
    HealthResponse,
    MaintenanceKpiResponse,
    MaintenanceLogCreateRequest,
    MaintenanceLogRecord,
    PreventiveMaintenanceRecord,
    RecurringIssueRecord,
    RiskRecord,
    SummaryResponse,
    TicketCreateRequest,
    TicketRecord,
    TicketUpdateRequest,
)
from src.api.services import (
    AssetNotFoundError,
    ProcessedDataNotFoundError,
    ProcessedDataService,
    TicketNotFoundError,
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
def health(service: ServiceDependency) -> dict[str, object]:
    """Return API health."""

    return service.get_health()


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


@router.get("/assets", response_model=list[AssetOverviewRecord], tags=["assets"])
def list_assets(
    service: ServiceDependency,
    asset_type: str | None = None,
    location: str | None = None,
    criticality: str | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    """List asset master rows enriched with latest maintenance signals."""

    return _handle_service_errors(
        service.list_assets,
        asset_type=asset_type,
        location=location,
        criticality=criticality,
        status=status,
    )


@router.get(
    "/assets/{asset_id}/details",
    response_model=AssetDetailsResponse,
    tags=["assets"],
)
def asset_details(
    asset_id: str,
    service: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict[str, object]:
    """Return one consolidated manager-facing asset view."""

    return _handle_service_errors(
        service.get_asset_details,
        asset_id=asset_id,
        limit=limit,
    )


@router.get("/assets/{asset_id}", response_model=AssetRecord, tags=["assets"])
def asset_master_record(asset_id: str, service: ServiceDependency) -> dict[str, object]:
    """Return one raw asset master record."""

    return _handle_service_errors(service.get_asset, asset_id=asset_id)


@router.get(
    "/maintenance/preventive",
    response_model=list[PreventiveMaintenanceRecord],
    tags=["maintenance"],
)
def preventive_maintenance(
    service: ServiceDependency,
    maintenance_status: str | None = None,
    asset_type: str | None = None,
    criticality: str | None = None,
) -> list[dict[str, object]]:
    """List current preventive maintenance status rows."""

    return _handle_service_errors(
        service.list_preventive_maintenance,
        maintenance_status=maintenance_status,
        asset_type=asset_type,
        criticality=criticality,
    )


@router.get(
    "/maintenance/recurring-issues",
    response_model=list[RecurringIssueRecord],
    tags=["maintenance"],
)
def recurring_issues(
    service: ServiceDependency,
    asset_id: str | None = None,
    failure_category: str | None = None,
    recurrence_flag: bool | None = None,
) -> list[dict[str, object]]:
    """List deterministic recurring ticket groups."""

    return _handle_service_errors(
        service.list_recurring_issues,
        asset_id=asset_id,
        failure_category=failure_category,
        recurrence_flag=recurrence_flag,
    )


@router.get(
    "/maintenance/kpis",
    response_model=MaintenanceKpiResponse,
    tags=["maintenance"],
)
def maintenance_kpis(service: ServiceDependency) -> dict[str, object]:
    """Return the current descriptive maintenance KPI snapshot."""

    return _handle_service_errors(service.get_maintenance_kpis)


@router.get("/tickets", response_model=list[TicketRecord], tags=["maintenance"])
def tickets(
    service: ServiceDependency,
    asset_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    failure_category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[dict[str, object]]:
    """List raw ticket records with focused filters."""

    return _handle_service_errors(
        service.list_tickets,
        asset_id=asset_id,
        status=status,
        priority=priority,
        failure_category=failure_category,
        limit=limit,
    )


@router.post(
    "/tickets",
    response_model=TicketRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["maintenance"],
)
def create_ticket(
    request: TicketCreateRequest,
    service: ServiceDependency,
) -> dict[str, object]:
    """Create one local inspection ticket without recalculating analytics."""

    return _handle_write_errors(
        service.create_ticket,
        **request.model_dump(),
    )


@router.patch(
    "/tickets/{ticket_id}",
    response_model=TicketRecord,
    tags=["maintenance"],
)
def update_ticket(
    ticket_id: str,
    request: TicketUpdateRequest,
    service: ServiceDependency,
) -> dict[str, object]:
    """Assign or move a local ticket through the linear MVP workflow."""

    return _handle_write_errors(
        service.update_ticket,
        ticket_id=ticket_id,
        updates=request.model_dump(exclude_unset=True),
    )


@router.get(
    "/maintenance/logs",
    response_model=list[MaintenanceLogRecord],
    tags=["maintenance"],
)
def maintenance_logs(
    service: ServiceDependency,
    asset_id: str | None = None,
    maintenance_result: str | None = None,
    follow_up_required: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[dict[str, object]]:
    """List maintenance log records with focused filters."""

    return _handle_service_errors(
        service.list_maintenance_logs,
        asset_id=asset_id,
        maintenance_result=maintenance_result,
        follow_up_required=follow_up_required,
        limit=limit,
    )


@router.post(
    "/maintenance/logs",
    response_model=MaintenanceLogRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["maintenance"],
)
def create_maintenance_log(
    request: MaintenanceLogCreateRequest,
    service: ServiceDependency,
) -> dict[str, object]:
    """Record a technician result for the next analytics batch."""

    return _handle_write_errors(
        service.create_maintenance_log,
        **request.model_dump(),
    )


@router.post("/copilot/ask", response_model=CopilotAskResponse, tags=["copilot"])
def ask_copilot(
    request: CopilotAskRequest,
    copilot: CopilotDependency,
) -> dict[str, object]:
    """Ask the deterministic RAG Maintenance Copilot."""

    try:
        optional_filters = {
            key: value
            for key, value in {
                "document_type": request.document_type,
                "failure_category": request.failure_category,
            }.items()
            if value is not None
        }
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


def _handle_service_errors(function, **kwargs):
    try:
        return function(**kwargs)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProcessedDataNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _handle_write_errors(function, **kwargs):
    try:
        return function(**kwargs)
    except (AssetNotFoundError, TicketNotFoundError, RecordNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DuplicateRecordError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CsvWriteError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CsvRepositoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
