"""Authenticated API boundary for bounded Stage 10 structured analytics."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from threading import BoundedSemaphore
from typing import Any, Protocol
from uuid import UUID

from data_platform.config import DataPlatformSettings
from data_platform.database import connect


MAX_DOMAIN_RESULTS = 200
MAX_DATE_RANGE_DAYS = 366
DOMAIN_STATEMENT_TIMEOUT_MS = 30_000
MAX_CONCURRENT_DOMAIN_QUERIES_PER_PROCESS = 8
_DOMAIN_QUERY_SLOTS = BoundedSemaphore(MAX_CONCURRENT_DOMAIN_QUERIES_PER_PROCESS)


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
    ) -> None:
        self._settings = settings.validated()
        self._connection_factory = connection_factory

    def execute(
        self,
        query: DomainAnalyticsQuery | str,
        *,
        site_id: UUID | str | None,
        start_date: date | str,
        end_date: date | str,
        limit: int = 100,
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
        with _DOMAIN_QUERY_SLOTS:
            with self._connection_factory(self._settings, read_only=True) as connection:
                connection.execute(
                    "SELECT set_config('statement_timeout', %(timeout_ms)s, true)",
                    {"timeout_ms": str(DOMAIN_STATEMENT_TIMEOUT_MS)},
                )
                cursor = connection.execute(_QUERY_SPECS[selected].statement, parameters)
                rows = list(cursor.fetchmany(parameters["limit"] + 1))[: parameters["limit"]]
                columns = _column_names(cursor.description)
        return [dict(zip(columns, row, strict=True)) for row in rows]


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
    "InvalidDomainQueryError",
    "MAX_DATE_RANGE_DAYS",
    "MAX_DOMAIN_RESULTS",
    "UnsupportedDomainQueryError",
]
