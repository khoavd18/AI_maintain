from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from data_platform.config import DataPlatformSettings
from src.analytics.domain_adapter import (
    APPROVED_DOMAIN_QUERIES,
    DomainAnalyticsAdapter,
    InvalidDomainQueryError,
    UnsupportedDomainQueryError,
)
from src.api.main import create_app
from src.api.routers.domain_analytics import get_domain_analytics_adapter
from tests.auth_helpers import authorize_app


class _Column:
    def __init__(self, name: str) -> None:
        self.name = name


class _Cursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows
        self.description = [_Column("site_id"), _Column("ticket_count")]

    def fetchmany(self, size: int) -> list[tuple[Any, ...]]:
        return self.rows[:size]


class _Connection:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows
        self.executions: list[tuple[str, dict[str, object]]] = []

    def execute(self, statement: str, parameters: dict[str, object]) -> _Cursor:
        self.executions.append((statement, parameters))
        return _Cursor(self.rows)


class _Factory:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.connection = _Connection(rows)
        self.read_only: list[bool] = []

    @contextmanager
    def __call__(self, settings: DataPlatformSettings, *, read_only: bool):
        assert settings.database.endswith("_scale")
        self.read_only.append(read_only)
        yield self.connection


def _adapter(rows: list[tuple[Any, ...]] | None = None) -> tuple[DomainAnalyticsAdapter, _Factory]:
    factory = _Factory(rows or [("site-1", 7)])
    adapter = DomainAnalyticsAdapter(DataPlatformSettings(), connection_factory=factory)
    return adapter, factory


def test_domain_query_catalog_is_closed_and_complete() -> None:
    assert APPROVED_DOMAIN_QUERIES == {
        "maintenance_summary",
        "site_reliability",
        "ticket_sla",
        "technician_workload",
        "inventory_consumption",
        "maintenance_cost_variance",
    }


def test_adapter_is_read_only_parameterized_and_sets_timeout() -> None:
    adapter, factory = _adapter()
    result = adapter.execute(
        "ticket_sla",
        site_id=None,
        start_date="2026-01-01",
        end_date=date(2026, 1, 31),
        limit=25,
    )

    assert result == [{"site_id": "site-1", "ticket_count": 7}]
    assert factory.read_only == [True]
    assert factory.connection.executions[0] == (
        "SELECT set_config('statement_timeout', %(timeout_ms)s, true)",
        {"timeout_ms": "30000"},
    )
    statement, parameters = factory.connection.executions[1]
    assert "%(start_date)s" in statement
    assert "2026-01-01" not in statement
    assert parameters["limit"] == 25


@pytest.mark.parametrize("query", ["ticket_sla ", "SELECT * FROM users", object()])
def test_arbitrary_domain_query_is_rejected(query: object) -> None:
    adapter, factory = _adapter()
    with pytest.raises(UnsupportedDomainQueryError):
        adapter.execute(
            query,  # type: ignore[arg-type]
            site_id=None,
            start_date="2026-01-01",
            end_date="2026-01-02",
        )
    assert factory.read_only == []


def test_date_and_result_bounds_fail_before_connecting() -> None:
    adapter, factory = _adapter()
    with pytest.raises(InvalidDomainQueryError, match="366"):
        adapter.execute(
            "site_reliability",
            site_id=None,
            start_date="2024-01-01",
            end_date="2026-01-01",
        )
    with pytest.raises(InvalidDomainQueryError, match="between"):
        adapter.execute(
            "site_reliability",
            site_id=None,
            start_date="2026-01-01",
            end_date="2026-01-02",
            limit=201,
        )
    assert factory.read_only == []


def test_endpoint_requires_authentication_and_uses_adapter_override() -> None:
    adapter, _ = _adapter()
    app = create_app()
    app.dependency_overrides[get_domain_analytics_adapter] = lambda: adapter
    unauthenticated = TestClient(app)
    response = unauthenticated.get(
        "/analytics/domain/ticket_sla",
        params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
    )
    assert response.status_code in {401, 403}

    authorize_app(app)
    authenticated = TestClient(app)
    response = authenticated.get(
        "/analytics/domain/ticket_sla",
        params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
    )
    assert response.status_code == 200
    assert response.json() == [{"site_id": "site-1", "ticket_count": 7}]
