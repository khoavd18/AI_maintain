"""Read-only analytics and maintenance snapshot endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.routers.dependencies import get_service
from src.api.routers.error_mapping import handle_service_errors
from src.api.schemas import (
    AnomalyRecord,
    MaintenanceKpiResponse,
    PreventiveMaintenanceRecord,
    RecurringIssueRecord,
    RiskRecord,
    SummaryResponse,
)
from src.api.services import ProcessedDataService
from src.security.dependencies import require_permission
from src.security.permissions import Permission
from src.security.principal import CurrentUser

router = APIRouter()
ServiceDependency = Annotated[ProcessedDataService, Depends(get_service)]
AnalyticsReadDependency = Annotated[
    CurrentUser,
    Depends(require_permission(Permission.ANALYTICS_READ)),
]


@router.get("/summary", response_model=SummaryResponse, tags=["maintenance"])
def summary(
    service: ServiceDependency,
    _actor: AnalyticsReadDependency,
) -> dict[str, object]:
    return handle_service_errors(service.get_summary)


@router.get("/assets/risk", response_model=list[RiskRecord], tags=["risk"])
def list_asset_risks(
    service: ServiceDependency,
    _actor: AnalyticsReadDependency,
    risk_level: str | None = None,
    asset_type: str | None = None,
    location: str | None = None,
    date: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> list[dict[str, object]]:
    return handle_service_errors(
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
    _actor: AnalyticsReadDependency,
    limit: Annotated[int, Query(ge=1, le=1000)] = 10,
    date: str | None = None,
) -> list[dict[str, object]]:
    return handle_service_errors(service.list_top_risks, limit=limit, date=date)


@router.get("/assets/risk/{asset_id}", response_model=list[RiskRecord], tags=["risk"])
def asset_risk_history(
    asset_id: str,
    service: ServiceDependency,
    _actor: AnalyticsReadDependency,
) -> list[dict[str, object]]:
    return handle_service_errors(service.get_asset_risk_history, asset_id=asset_id)


@router.get("/assets/anomalies", response_model=list[AnomalyRecord], tags=["anomalies"])
def list_asset_anomalies(
    service: ServiceDependency,
    _actor: AnalyticsReadDependency,
    asset_type: str | None = None,
    anomaly_type: str | None = None,
    date: str | None = None,
    only_anomalies: bool = True,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[dict[str, object]]:
    return handle_service_errors(
        service.list_anomalies,
        asset_type=asset_type,
        anomaly_type=anomaly_type,
        date=date,
        only_anomalies=only_anomalies,
        limit=limit,
    )


@router.get("/assets/anomalies/{asset_id}", response_model=list[AnomalyRecord], tags=["anomalies"])
def asset_anomaly_history(
    asset_id: str,
    service: ServiceDependency,
    _actor: AnalyticsReadDependency,
) -> list[dict[str, object]]:
    return handle_service_errors(service.get_asset_anomaly_history, asset_id=asset_id)


@router.get(
    "/maintenance/preventive",
    response_model=list[PreventiveMaintenanceRecord],
    tags=["maintenance"],
)
def preventive_maintenance(
    service: ServiceDependency,
    _actor: AnalyticsReadDependency,
    maintenance_status: str | None = None,
    asset_type: str | None = None,
    criticality: str | None = None,
) -> list[dict[str, object]]:
    return handle_service_errors(
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
    _actor: AnalyticsReadDependency,
    asset_id: str | None = None,
    failure_category: str | None = None,
    recurrence_flag: bool | None = None,
) -> list[dict[str, object]]:
    return handle_service_errors(
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
def maintenance_kpis(
    service: ServiceDependency,
    _actor: AnalyticsReadDependency,
) -> dict[str, object]:
    return handle_service_errors(service.get_maintenance_kpis)


__all__ = [
    "asset_anomaly_history",
    "asset_risk_history",
    "list_asset_anomalies",
    "list_asset_risks",
    "maintenance_kpis",
    "preventive_maintenance",
    "recurring_issues",
    "router",
    "summary",
    "top_asset_risks",
]
