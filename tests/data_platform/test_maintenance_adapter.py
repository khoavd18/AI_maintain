from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import pytest

from data_platform.config import DataPlatformSettings
from src.analytics.maintenance_adapter import (
    APPROVED_MAINTENANCE_QUERIES,
    MAX_MAINTENANCE_RESULTS,
    InvalidMaintenanceQueryError,
    MaintenanceAggregateQuery,
    MaintenanceAnalyticsAdapter,
    UnsupportedMaintenanceQueryError,
)


@dataclass(frozen=True)
class _Column:
    name: str


class _FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.description = [_Column("site_id"), _Column("row_count")]
        self.rows = rows
        self.fetch_size: int | None = None

    def fetchmany(self, size: int) -> list[tuple[Any, ...]]:
        self.fetch_size = size
        # Deliberately violate the cursor contract.  The adapter must preserve
        # its own result boundary even if a driver/test double returns too much.
        return self.rows


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self.cursor = cursor
        self.executions: list[tuple[str, dict[str, object]]] = []

    def execute(self, statement: str, parameters: dict[str, object]) -> _FakeCursor:
        self.executions.append((statement, parameters))
        return self.cursor


class _FakeConnectionFactory:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.connection = _FakeConnection(_FakeCursor(rows))
        self.calls: list[tuple[DataPlatformSettings, bool]] = []

    @contextmanager
    def __call__(self, settings: DataPlatformSettings, *, read_only: bool):
        self.calls.append((settings, read_only))
        yield self.connection


def _settings() -> DataPlatformSettings:
    return DataPlatformSettings().validated()


def test_query_catalog_is_closed_and_has_exactly_four_values() -> None:
    assert APPROVED_MAINTENANCE_QUERIES == {
        "critical_open",
        "technician_workload",
        "monthly_completion",
        "cost_variance",
    }


def test_adapter_injects_settings_uses_read_only_transaction_and_bound_values() -> None:
    site_id = UUID("10000000-0000-0000-0000-000000000001")
    factory = _FakeConnectionFactory([(site_id, 7)])
    settings = _settings()
    adapter = MaintenanceAnalyticsAdapter(settings, connection_factory=factory)

    result = adapter.execute(
        MaintenanceAggregateQuery.CRITICAL_OPEN,
        parameters={
            "site_id": str(site_id),
            "start_date": "2026-01-01",
            "end_date": date(2026, 1, 31),
        },
        limit=25,
    )

    assert result == [{"site_id": site_id, "row_count": 7}]
    assert factory.calls == [(settings, True)]
    statement, parameters = factory.connection.executions[0]
    assert str(site_id) not in statement
    assert "2026-01-01" not in statement
    assert "%(site_id)s" in statement
    assert "LIMIT %(limit)s::integer" in statement
    assert parameters == {
        "site_id": site_id,
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 31),
        "limit": 25,
    }


def test_adapter_bounds_results_even_if_cursor_returns_too_many_rows() -> None:
    rows = [(index, index) for index in range(MAX_MAINTENANCE_RESULTS + 50)]
    factory = _FakeConnectionFactory(rows)
    adapter = MaintenanceAnalyticsAdapter(_settings(), connection_factory=factory)

    result = adapter.execute("monthly_completion", limit=MAX_MAINTENANCE_RESULTS)

    assert len(result) == MAX_MAINTENANCE_RESULTS
    assert factory.connection.cursor.fetch_size == MAX_MAINTENANCE_RESULTS + 1


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM analytics_warehouse.fact_work_order",
        "critical_open ",
        "rag_search",
        object(),
    ],
)
def test_arbitrary_or_near_match_query_is_rejected_before_connecting(query: object) -> None:
    factory = _FakeConnectionFactory([])
    adapter = MaintenanceAnalyticsAdapter(_settings(), connection_factory=factory)

    with pytest.raises(UnsupportedMaintenanceQueryError):
        adapter.execute(query)  # type: ignore[arg-type]

    assert factory.calls == []


@pytest.mark.parametrize("limit", [0, 501, -1, True, 1.5, "10"])
def test_invalid_result_limits_are_rejected_before_connecting(limit: object) -> None:
    factory = _FakeConnectionFactory([])
    adapter = MaintenanceAnalyticsAdapter(_settings(), connection_factory=factory)

    with pytest.raises(InvalidMaintenanceQueryError):
        adapter.execute("critical_open", limit=limit)  # type: ignore[arg-type]

    assert factory.calls == []


@pytest.mark.parametrize(
    "parameters",
    [
        {"sql": "DROP TABLE work_orders"},
        {"site_id": "not-a-uuid"},
        {"start_date": "2026-02-01", "end_date": "2026-01-01"},
        {"start_date": "yesterday"},
    ],
)
def test_unapproved_or_invalid_parameters_are_rejected_before_connecting(
    parameters: dict[str, object],
) -> None:
    factory = _FakeConnectionFactory([])
    adapter = MaintenanceAnalyticsAdapter(_settings(), connection_factory=factory)

    with pytest.raises(InvalidMaintenanceQueryError):
        adapter.execute("critical_open", parameters=parameters)

    assert factory.calls == []


def test_cost_variance_query_reports_data_availability_explicitly() -> None:
    factory = _FakeConnectionFactory([])
    adapter = MaintenanceAnalyticsAdapter(_settings(), connection_factory=factory)

    adapter.execute(MaintenanceAggregateQuery.COST_VARIANCE)

    statement, _ = factory.connection.executions[0]
    assert "total_cost_variance" in statement
    assert "cost_data_available" in statement
