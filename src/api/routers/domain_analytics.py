"""Authenticated and bounded Stage 10 structured-analytics endpoints."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from data_platform.config import DataPlatformSettings
from src.analytics.domain_adapter import (
    DomainAnalyticsAdapter,
    DomainAnalyticsQuery,
    InvalidDomainQueryError,
    UnsupportedDomainQueryError,
)
from src.security.dependencies import require_permission
from src.security.permissions import Permission
from src.security.principal import CurrentUser


router = APIRouter(prefix="/analytics/domain", tags=["domain-analytics"])
AnalyticsReadDependency = Annotated[
    CurrentUser,
    Depends(require_permission(Permission.ANALYTICS_READ)),
]


@lru_cache(maxsize=1)
def get_domain_analytics_adapter() -> DomainAnalyticsAdapter:
    """Construct one process-local adapter with bounded cache and concurrency."""

    return DomainAnalyticsAdapter(DataPlatformSettings.from_env())


AdapterDependency = Annotated[DomainAnalyticsAdapter, Depends(get_domain_analytics_adapter)]


@router.get("/metrics/runtime", response_model=dict[str, object])
def domain_analytics_runtime_metrics(
    _actor: AnalyticsReadDependency,
    adapter: AdapterDependency,
) -> dict[str, object]:
    """Expose label-free cache/query pressure for authenticated diagnostics."""

    return adapter.runtime_snapshot()


@router.get("/{query_name}", response_model=list[dict[str, object]])
def query_domain_analytics(
    actor: AnalyticsReadDependency,
    adapter: AdapterDependency,
    query_name: Annotated[str, Path(min_length=1, max_length=100)],
    start_date: date,
    end_date: date,
    site_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[dict[str, object]]:
    """Run one exact allow-listed query with a maximum 366-day range."""

    try:
        selected = DomainAnalyticsQuery(query_name)
        return adapter.execute(
            selected,
            site_id=site_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            authorization_scope=actor.id,
        )
    except UnsupportedDomainQueryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (InvalidDomainQueryError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = [
    "domain_analytics_runtime_metrics",
    "get_domain_analytics_adapter",
    "query_domain_analytics",
    "router",
]
