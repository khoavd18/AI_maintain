"""Authenticated API boundary for bounded Stage 10 structured analytics."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from threading import BoundedSemaphore, RLock
import time
from typing import Any, Protocol
from uuid import UUID

from data_platform.config import DataPlatformSettings
from data_platform.database import connect


MAX_DOMAIN_RESULTS = 200
MAX_DATE_RANGE_DAYS = 366
DOMAIN_STATEMENT_TIMEOUT_MS = 30_000
MAX_CONCURRENT_DOMAIN_QUERIES_PER_PROCESS = 8

_CacheKey = tuple[str, str, str, str, str, int]


class DomainAnalyticsRuntime:
    """Own bounded per-process query concurrency, cache, and safe metrics."""

    def __init__(
        self,
        *,
        query_slots: int,
        cache_ttl_seconds: int,
        cache_max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 1 <= query_slots <= 32:
            raise ValueError("query_slots must be between 1 and 32.")
        if not 0 <= cache_ttl_seconds <= 60:
            raise ValueError("cache_ttl_seconds must be between 0 and 60.")
        if not 1 <= cache_max_entries <= 4_096:
            raise ValueError("cache_max_entries must be between 1 and 4,096.")
        self.query_slots = query_slots
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache_max_entries = cache_max_entries
        self._clock = clock
        self._slots = BoundedSemaphore(query_slots)
        self._lock = RLock()
        self._cache: OrderedDict[
            _CacheKey, tuple[float, tuple[dict[str, Any], ...]]
        ] = OrderedDict()
        self._active_queries = 0
        self._peak_active_queries = 0
        self._slot_acquisitions = 0
        self._slot_wait_ms = 0.0
        self._query_executions = 0
        self._query_time_ms = 0.0
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0

    @property
    def cache_enabled(self) -> bool:
        return self.cache_ttl_seconds > 0

    def cached(self, key: _CacheKey) -> list[dict[str, Any]] | None:
        if not self.cache_enabled:
            return None
        now = self._clock()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            expires_at, rows = entry
            if expires_at <= now:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            self._cache_hits += 1
            return [dict(row) for row in rows]

    def record_cache_miss(self) -> None:
        with self._lock:
            self._cache_misses += 1

    def store(self, key: _CacheKey, rows: list[dict[str, Any]]) -> None:
        if not self.cache_enabled:
            return
        expires_at = self._clock() + self.cache_ttl_seconds
        stored = tuple(dict(row) for row in rows)
        with self._lock:
            expired = [
                cached_key
                for cached_key, (cached_until, _) in self._cache.items()
                if cached_until <= self._clock()
            ]
            for cached_key in expired:
                del self._cache[cached_key]
            self._cache[key] = (expires_at, stored)
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_max_entries:
                self._cache.popitem(last=False)
                self._cache_evictions += 1

    @contextmanager
    def query_slot(self) -> Iterator[None]:
        waiting_at = self._clock()
        self._slots.acquire()
        waited_ms = (self._clock() - waiting_at) * 1_000
        with self._lock:
            self._slot_acquisitions += 1
            self._slot_wait_ms += waited_ms
            self._active_queries += 1
            self._peak_active_queries = max(
                self._peak_active_queries, self._active_queries
            )
        try:
            yield
        finally:
            with self._lock:
                self._active_queries -= 1
            self._slots.release()

    def record_query(self, duration_ms: float) -> None:
        with self._lock:
            self._query_executions += 1
            self._query_time_ms += duration_ms

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "query_slots": self.query_slots,
                "active_queries": self._active_queries,
                "peak_active_queries": self._peak_active_queries,
                "slot_acquisitions": self._slot_acquisitions,
                "slot_wait_ms": round(self._slot_wait_ms, 3),
                "query_executions": self._query_executions,
                "query_time_ms": round(self._query_time_ms, 3),
                "cache": {
                    "enabled": self.cache_enabled,
                    "ttl_seconds": self.cache_ttl_seconds,
                    "max_entries": self.cache_max_entries,
                    "entries": len(self._cache),
                    "hits": self._cache_hits,
                    "misses": self._cache_misses,
                    "evictions": self._cache_evictions,
                },
            }


class DomainAnalyticsQuery(StrEnum):
    MAINTENANCE_SUMMARY = "maintenance_summary"
    SITE_RELIABILITY = "site_reliability"
    TICKET_SLA = "ticket_sla"
    TECHNICIAN_WORKLOAD = "technician_workload"
    INVENTORY_CONSUMPTION = "inventory_consumption"
    MAINTENANCE_COST_VARIANCE = "maintenance_cost_variance"


APPROVED_DOMAIN_QUERIES = frozenset(query.value for query in DomainAnalyticsQuery)


class UnsupportedDomainQueryError(ValueError):
    """Raised when a caller does not select the exact closed catalog."""


class InvalidDomainQueryError(ValueError):
    """Raised when an analytics request exceeds a declared bound."""


class _Cursor(Protocol):
    description: Any

    def fetchmany(self, size: int) -> list[Any]: ...


class _Connection(Protocol):
    def execute(self, statement: str, parameters: Mapping[str, object]) -> _Cursor: ...


@dataclass(frozen=True, slots=True)
class _QuerySpec:
    statement: str


_DATE_FILTER = """
    (%(site_id)s::uuid IS NULL OR {site_expression} = %(site_id)s::uuid)
    AND ({date_expression})::date >= %(start_date)s::date
    AND ({date_expression})::date <= %(end_date)s::date
"""

_QUERY_SPECS: Mapping[DomainAnalyticsQuery, _QuerySpec] = {
    DomainAnalyticsQuery.MAINTENANCE_SUMMARY: _QuerySpec(
        """
        WITH work_orders AS (
            SELECT
                count(*)::bigint AS work_order_count,
                count(*) FILTER (WHERE status IN ('completed', 'verified'))::bigint
                    AS completed_work_order_count,
                count(*) FILTER (WHERE priority = 'critical')::bigint
                    AS critical_work_order_count
            FROM analytics_warehouse.fact_work_order
            WHERE """
        + _DATE_FILTER.format(
            site_expression="site_id",
            date_expression="created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'",
        )
        + """
        ), tickets AS (
            SELECT
                count(*)::bigint AS ticket_count,
                count(*) FILTER (WHERE is_resolution_breached)::bigint
                    AS resolution_breach_count
            FROM analytics_warehouse.fact_ticket_sla
            WHERE """
        + _DATE_FILTER.format(
            site_expression="site_id",
            date_expression="opened_at AT TIME ZONE 'Asia/Ho_Chi_Minh'",
        )
        + """
        ), costs AS (
            SELECT
                coalesce(sum(c.total_actual_cost), 0) AS total_actual_cost,
                coalesce(sum(c.cost_variance), 0) AS total_cost_variance,
                min(c.currency_code) AS currency_code
            FROM analytics_warehouse.fact_work_order_cost c
            JOIN analytics_warehouse.fact_work_order w USING (work_order_id)
            WHERE """
        + _DATE_FILTER.format(
            site_expression="c.site_id",
            date_expression="w.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'",
        )
        + """
        )
        SELECT * FROM work_orders CROSS JOIN tickets CROSS JOIN costs
        LIMIT %(limit)s::integer
        """
    ),
    DomainAnalyticsQuery.SITE_RELIABILITY: _QuerySpec(
        """
        SELECT
            w.site_id,
            s.site_code,
            s.site_name,
            count(*)::bigint AS work_order_count,
            count(*) FILTER (WHERE w.status IN ('completed', 'verified'))::bigint
                AS completed_work_order_count,
            round(
                100.0 * count(*) FILTER (WHERE w.status IN ('completed', 'verified'))
                / nullif(count(*), 0),
                4
            ) AS completion_rate_percent,
            round(avg(w.repair_hours) FILTER (WHERE w.repair_hours IS NOT NULL), 4)
                AS average_repair_hours
        FROM analytics_warehouse.fact_work_order w
        JOIN analytics_warehouse.dim_site s USING (site_key)
        WHERE """
        + _DATE_FILTER.format(
            site_expression="w.site_id",
            date_expression="w.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'",
        )
        + """
        GROUP BY w.site_id, s.site_code, s.site_name
        ORDER BY completion_rate_percent, w.site_id
        LIMIT %(limit)s::integer
        """
    ),
    DomainAnalyticsQuery.TICKET_SLA: _QuerySpec(
        """
        SELECT
            t.site_id,
            s.site_code,
            s.site_name,
            t.priority,
            count(*)::bigint AS ticket_count,
            count(*) FILTER (WHERE t.resolved_at IS NULL)::bigint AS unresolved_ticket_count,
            count(*) FILTER (WHERE t.is_resolution_breached)::bigint
                AS resolution_breach_count,
            count(*) FILTER (WHERE t.is_escalated)::bigint AS escalated_ticket_count
        FROM analytics_warehouse.fact_ticket_sla t
        JOIN analytics_warehouse.dim_site s USING (site_id)
        WHERE """
        + _DATE_FILTER.format(
            site_expression="t.site_id",
            date_expression="t.opened_at AT TIME ZONE 'Asia/Ho_Chi_Minh'",
        )
        + """
        GROUP BY t.site_id, s.site_code, s.site_name, t.priority
        ORDER BY resolution_breach_count DESC, ticket_count DESC, t.site_id, t.priority
        LIMIT %(limit)s::integer
        """
    ),
    DomainAnalyticsQuery.TECHNICIAN_WORKLOAD: _QuerySpec(
        """
        SELECT
            w.assigned_technician_id AS technician_id,
            t.employee_code,
            t.display_name,
            count(*)::bigint AS assigned_work_order_count,
            count(*) FILTER (
                WHERE w.status IN ('planned', 'assigned', 'in_progress', 'on_hold')
            )::bigint AS open_work_order_count,
            coalesce(sum(w.labor_minutes), 0)::bigint AS labor_minutes
        FROM analytics_warehouse.fact_work_order w
        JOIN analytics_warehouse.dim_technician t USING (technician_key)
        WHERE w.assigned_technician_id IS NOT NULL AND """
        + _DATE_FILTER.format(
            site_expression="w.site_id",
            date_expression="w.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'",
        )
        + """
        GROUP BY w.assigned_technician_id, t.employee_code, t.display_name
        ORDER BY open_work_order_count DESC, assigned_work_order_count DESC, technician_id
        LIMIT %(limit)s::integer
        """
    ),
    DomainAnalyticsQuery.INVENTORY_CONSUMPTION: _QuerySpec(
        """
        SELECT
            m.part_id,
            p.part_number,
            p.part_name,
            m.site_id,
            count(*) FILTER (WHERE m.movement_type = 'issue')::bigint
                AS issue_movement_count,
            coalesce(sum(m.quantity) FILTER (WHERE m.movement_type = 'issue'), 0)
                AS issued_quantity,
            coalesce(sum(m.quantity) FILTER (WHERE m.movement_type = 'return'), 0)
                AS returned_quantity
        FROM analytics_warehouse.fact_inventory_movement m
        JOIN analytics_warehouse.dim_spare_part p USING (part_key)
        WHERE m.site_id IS NOT NULL AND """
        + _DATE_FILTER.format(
            site_expression="m.site_id",
            date_expression="m.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'",
        )
        + """
        GROUP BY m.part_id, p.part_number, p.part_name, m.site_id
        ORDER BY issued_quantity DESC, m.part_id, m.site_id
        LIMIT %(limit)s::integer
        """
    ),
    DomainAnalyticsQuery.MAINTENANCE_COST_VARIANCE: _QuerySpec(
        """
        SELECT
            date_trunc(
                'month', w.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
            )::date AS month_start_date,
            c.site_id,
            s.site_code,
            s.site_name,
            count(*)::bigint AS work_order_count,
            sum(c.total_estimated_cost) AS total_estimated_cost,
            sum(c.total_actual_cost) AS total_actual_cost,
            sum(c.cost_variance) AS total_cost_variance,
            min(c.currency_code) AS currency_code
        FROM analytics_warehouse.fact_work_order_cost c
        JOIN analytics_warehouse.fact_work_order w USING (work_order_id)
        JOIN analytics_warehouse.dim_site s ON s.site_id = c.site_id
        WHERE """
        + _DATE_FILTER.format(
            site_expression="c.site_id",
            date_expression="w.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'",
        )
        + """
        GROUP BY month_start_date, c.site_id, s.site_code, s.site_name
        ORDER BY month_start_date DESC, abs(sum(c.cost_variance)) DESC, c.site_id
        LIMIT %(limit)s::integer
        """
    ),
}


def _connection_factory(
    settings: DataPlatformSettings,
    *,
    read_only: bool,
) -> AbstractContextManager[_Connection]:
    return connect(settings, read_only=read_only)


class DomainAnalyticsAdapter:
    """Execute only static parameterized SQL in a read-only transaction."""

    def __init__(
        self,
        settings: DataPlatformSettings,
        *,
        connection_factory: Callable[..., AbstractContextManager[_Connection]] = (
            _connection_factory
        ),
        runtime: DomainAnalyticsRuntime | None = None,
    ) -> None:
        self._settings = settings.validated()
        self._connection_factory = connection_factory
        self._runtime = runtime or DomainAnalyticsRuntime(
            query_slots=self._settings.api_query_slots,
            cache_ttl_seconds=self._settings.api_cache_ttl_seconds,
            cache_max_entries=self._settings.api_cache_max_entries,
        )

    def execute(
        self,
        query: DomainAnalyticsQuery | str,
        *,
        site_id: UUID | str | None,
        start_date: date | str,
        end_date: date | str,
        limit: int = 100,
        authorization_scope: UUID | str | None = None,
    ) -> list[dict[str, Any]]:
        selected = _select_query(query)
        parameters = {
            "site_id": _optional_uuid(site_id),
            "start_date": _required_date(start_date, "start_date"),
            "end_date": _required_date(end_date, "end_date"),
            "limit": _bounded_limit(limit),
        }
        if parameters["start_date"] > parameters["end_date"]:
            raise InvalidDomainQueryError("start_date must not be after end_date.")
        if (parameters["end_date"] - parameters["start_date"]).days > MAX_DATE_RANGE_DAYS:
            raise InvalidDomainQueryError(
                f"Date range must not exceed {MAX_DATE_RANGE_DAYS} days."
            )
        cache_key = (
            _cache_key(selected, parameters, authorization_scope)
            if self._runtime.cache_enabled
            else None
        )
        if cache_key is not None:
            cached = self._runtime.cached(cache_key)
            if cached is not None:
                return cached
        with self._runtime.query_slot():
            if cache_key is not None:
                cached = self._runtime.cached(cache_key)
                if cached is not None:
                    return cached
                self._runtime.record_cache_miss()
            query_started = time.perf_counter()
            try:
                with self._connection_factory(self._settings, read_only=True) as connection:
                    connection.execute(
                        "SELECT set_config('statement_timeout', %(timeout_ms)s, true)",
                        {"timeout_ms": str(DOMAIN_STATEMENT_TIMEOUT_MS)},
                    )
                    cursor = connection.execute(_QUERY_SPECS[selected].statement, parameters)
                    rows = list(cursor.fetchmany(parameters["limit"] + 1))[
                        : parameters["limit"]
                    ]
                    columns = _column_names(cursor.description)
            finally:
                self._runtime.record_query(
                    (time.perf_counter() - query_started) * 1_000
                )
            result = [dict(zip(columns, row, strict=True)) for row in rows]
            if cache_key is not None:
                self._runtime.store(cache_key, result)
            return result

    def runtime_snapshot(self) -> dict[str, object]:
        """Return aggregate process-local metrics without query or identity labels."""

        return self._runtime.snapshot()


def _cache_key(
    query: DomainAnalyticsQuery,
    parameters: Mapping[str, object],
    authorization_scope: UUID | str | None,
) -> _CacheKey | None:
    if authorization_scope is None:
        return None
    scope = str(authorization_scope).strip()
    if not scope or len(scope) > 200:
        raise InvalidDomainQueryError("authorization_scope must be a bounded identity.")
    site_id = parameters["site_id"]
    start_date = parameters["start_date"]
    end_date = parameters["end_date"]
    limit = parameters["limit"]
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise RuntimeError("Validated analytics cache dates are invalid.")
    if not isinstance(limit, int):
        raise RuntimeError("Validated analytics cache limit is invalid.")
    return (
        scope,
        query.value,
        str(site_id or ""),
        start_date.isoformat(),
        end_date.isoformat(),
        limit,
    )


def _select_query(query: DomainAnalyticsQuery | str) -> DomainAnalyticsQuery:
    if isinstance(query, DomainAnalyticsQuery):
        return query
    if not isinstance(query, str):
        raise UnsupportedDomainQueryError("Domain query must be selected by exact name.")
    try:
        return DomainAnalyticsQuery(query)
    except ValueError:
        raise UnsupportedDomainQueryError(f"Unsupported domain analytics query: {query!r}.") from None


def _bounded_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_DOMAIN_RESULTS:
        raise InvalidDomainQueryError(
            f"Result limit must be an integer between 1 and {MAX_DOMAIN_RESULTS}."
        )
    return limit


def _optional_uuid(value: UUID | str | None) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        raise InvalidDomainQueryError("site_id must be a UUID or null.")
    try:
        return UUID(value)
    except ValueError:
        raise InvalidDomainQueryError("site_id must be a valid UUID.") from None


def _required_date(value: date | str, name: str) -> date:
    if isinstance(value, datetime):
        raise InvalidDomainQueryError(f"{name} must be a date, not a datetime.")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise InvalidDomainQueryError(f"{name} must be an ISO date.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InvalidDomainQueryError(f"{name} must be a valid ISO date.") from None


def _column_names(description: Any) -> tuple[str, ...]:
    if description is None:
        raise RuntimeError("Domain analytics query returned no columns.")
    names: list[str] = []
    for column in description:
        name = getattr(column, "name", None)
        if name is None and isinstance(column, (tuple, list)) and column:
            name = column[0]
        if not isinstance(name, str) or not name:
            raise RuntimeError("Domain analytics returned invalid metadata.")
        names.append(name)
    return tuple(names)


__all__ = [
    "APPROVED_DOMAIN_QUERIES",
    "DomainAnalyticsAdapter",
    "DomainAnalyticsQuery",
    "DomainAnalyticsRuntime",
    "InvalidDomainQueryError",
    "MAX_CONCURRENT_DOMAIN_QUERIES_PER_PROCESS",
    "MAX_DATE_RANGE_DAYS",
    "MAX_DOMAIN_RESULTS",
    "UnsupportedDomainQueryError",
]
