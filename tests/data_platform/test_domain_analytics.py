from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date
from threading import Event, Lock
from typing import Any

import pytest
from fastapi.testclient import TestClient

from data_platform.config import DataPlatformSettings
from src.analytics.domain_adapter import (
    APPROVED_DOMAIN_QUERIES,
    DomainAnalyticsAdapter,
    DomainAnalyticsRuntime,
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
    metrics = unauthenticated.get("/analytics/domain/metrics/runtime")
    assert metrics.status_code in {401, 403}

    authorize_app(app)
    authenticated = TestClient(app)
    response = authenticated.get(
        "/analytics/domain/ticket_sla",
        params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
    )
    assert response.status_code == 200
    assert response.json() == [{"site_id": "site-1", "ticket_count": 7}]

    metrics = authenticated.get("/analytics/domain/metrics/runtime")
    assert metrics.status_code == 200
    assert metrics.json()["query_slots"] == 8


def test_cache_is_bounded_by_identity_site_and_ttl() -> None:
    now = [100.0]
    runtime = DomainAnalyticsRuntime(
        query_slots=2,
        cache_ttl_seconds=5,
        cache_max_entries=3,
        clock=lambda: now[0],
    )
    factory = _Factory([("site-1", 7)])
    adapter = DomainAnalyticsAdapter(
        DataPlatformSettings(api_cache_ttl_seconds=5, api_cache_max_entries=3),
        connection_factory=factory,
        runtime=runtime,
    )
    arguments = {
        "query": "ticket_sla",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "limit": 25,
    }

    adapter.execute(
        **arguments,
        site_id="00000000-0000-0000-0000-000000000001",
        authorization_scope="user-a",
    )
    adapter.execute(
        **arguments,
        site_id="00000000-0000-0000-0000-000000000001",
        authorization_scope="user-a",
    )
    assert len(factory.read_only) == 1

    adapter.execute(
        **arguments,
        site_id="00000000-0000-0000-0000-000000000001",
        authorization_scope="user-b",
    )
    adapter.execute(
        **arguments,
        site_id="00000000-0000-0000-0000-000000000002",
        authorization_scope="user-a",
    )
    assert len(factory.read_only) == 3

    adapter.execute(
        **arguments,
        site_id="00000000-0000-0000-0000-000000000003",
        authorization_scope="user-a",
    )
    assert len(factory.read_only) == 4
    cache = adapter.runtime_snapshot()["cache"]
    assert isinstance(cache, dict)
    assert cache["entries"] == 3
    assert cache["evictions"] == 1

    now[0] += 6
    adapter.execute(
        **arguments,
        site_id="00000000-0000-0000-0000-000000000001",
        authorization_scope="user-a",
    )
    assert len(factory.read_only) == 5
    snapshot = adapter.runtime_snapshot()
    assert snapshot["cache"] == {
        "enabled": True,
        "ttl_seconds": 5,
        "max_entries": 3,
        "entries": 1,
        "hits": 1,
        "misses": 5,
        "evictions": 1,
    }


def test_cache_is_skipped_without_an_authorization_scope() -> None:
    factory = _Factory([("site-1", 7)])
    adapter = DomainAnalyticsAdapter(
        DataPlatformSettings(api_cache_ttl_seconds=5),
        connection_factory=factory,
    )

    for _ in range(2):
        adapter.execute(
            "ticket_sla",
            site_id="00000000-0000-0000-0000-000000000001",
            start_date="2026-01-01",
            end_date="2026-01-31",
        )

    assert len(factory.read_only) == 2
    cache = adapter.runtime_snapshot()["cache"]
    assert isinstance(cache, dict)
    assert cache["entries"] == 0


class _ConcurrentFactory:
    def __init__(self) -> None:
        self.lock = Lock()
        self.release = Event()
        self.two_active = Event()
        self.active = 0
        self.peak = 0

    @contextmanager
    def __call__(self, settings: DataPlatformSettings, *, read_only: bool):
        assert read_only is True
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.active == 2:
                self.two_active.set()
        try:
            assert self.release.wait(timeout=5)
            yield _Connection([("site-1", 7)])
        finally:
            with self.lock:
                self.active -= 1


def test_runtime_enforces_query_slots_under_concurrency() -> None:
    runtime = DomainAnalyticsRuntime(
        query_slots=2,
        cache_ttl_seconds=0,
        cache_max_entries=10,
    )
    factory = _ConcurrentFactory()
    adapter = DomainAnalyticsAdapter(
        DataPlatformSettings(api_query_slots=2),
        connection_factory=factory,
        runtime=runtime,
    )

    def execute() -> list[dict[str, Any]]:
        return adapter.execute(
            "ticket_sla",
            site_id=None,
            start_date="2026-01-01",
            end_date="2026-01-31",
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(execute) for _ in range(4)]
        assert factory.two_active.wait(timeout=5)
        assert runtime.snapshot()["active_queries"] == 2
        factory.release.set()
        assert all(future.result() for future in futures)

    assert factory.peak == 2
    snapshot = runtime.snapshot()
    assert snapshot["peak_active_queries"] == 2
    assert snapshot["query_executions"] == 4
