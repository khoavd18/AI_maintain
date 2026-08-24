"""Bounded, read-only access to approved maintenance warehouse aggregates.

This module is deliberately separate from the RAG stack.  Structured facts
remain in PostgreSQL and callers can select only one of the static aggregate
queries defined here; no SQL text is accepted from a caller or model.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from data_platform.config import DataPlatformSettings
from data_platform.database import connect


MAX_MAINTENANCE_RESULTS = 500
DEFAULT_MAINTENANCE_RESULTS = 100


class MaintenanceAggregateQuery(str, Enum):
    """Closed catalog of structured maintenance questions."""

    CRITICAL_OPEN = "critical_open"
    TECHNICIAN_WORKLOAD = "technician_workload"
    MONTHLY_COMPLETION = "monthly_completion"
    COST_VARIANCE = "cost_variance"


APPROVED_MAINTENANCE_QUERIES = frozenset(query.value for query in MaintenanceAggregateQuery)


class UnsupportedMaintenanceQueryError(ValueError):
    """Raised when a caller requests anything outside the closed catalog."""


class InvalidMaintenanceQueryError(ValueError):
    """Raised when bounded query parameters do not satisfy the contract."""


class _Cursor(Protocol):
    description: Any

    def fetchmany(self, size: int) -> list[Any]: ...


class _Connection(Protocol):
    def execute(self, statement: str, parameters: Mapping[str, object]) -> _Cursor: ...


@dataclass(frozen=True, slots=True)
class _QuerySpec:
    statement: str
    parameter_names: frozenset[str] = frozenset({"site_id", "start_date", "end_date"})


_QUERY_SPECS: Mapping[MaintenanceAggregateQuery, _QuerySpec] = {
    MaintenanceAggregateQuery.CRITICAL_OPEN: _QuerySpec(
        """
        SELECT
            fact.site_id,
            site.site_code,
            site.site_name,
            count(*)::bigint AS critical_open_work_orders,
            count(*) FILTER (
                WHERE fact.assigned_technician_id IS NULL
            )::bigint AS unassigned_work_orders,
            min(fact.due_date) AS earliest_due_date
        FROM analytics_warehouse.fact_work_order AS fact
        LEFT JOIN analytics_warehouse.dim_site AS site
            ON site.site_key = fact.site_key
        WHERE fact.priority = 'critical'
          AND fact.status IN ('planned', 'assigned', 'in_progress', 'on_hold')
          AND (%(site_id)s::uuid IS NULL OR fact.site_id = %(site_id)s::uuid)
          AND (
              %(start_date)s::date IS NULL
              OR (fact.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                 >= %(start_date)s::date
          )
          AND (
              %(end_date)s::date IS NULL
              OR (fact.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                 <= %(end_date)s::date
          )
        GROUP BY fact.site_id, site.site_code, site.site_name
        ORDER BY critical_open_work_orders DESC, fact.site_id
        LIMIT %(limit)s::integer
        """
    ),
    MaintenanceAggregateQuery.TECHNICIAN_WORKLOAD: _QuerySpec(
        """
        SELECT
            fact.assigned_technician_id AS technician_id,
            technician.employee_code,
            technician.display_name,
            count(*)::bigint AS assigned_work_orders,
            count(*) FILTER (
                WHERE fact.status IN ('planned', 'assigned', 'in_progress', 'on_hold')
            )::bigint AS open_work_orders,
            count(*) FILTER (
                WHERE fact.status IN ('completed', 'verified')
            )::bigint AS completed_work_orders,
            coalesce(sum(fact.labor_minutes), 0)::bigint AS labor_minutes
        FROM analytics_warehouse.fact_work_order AS fact
        LEFT JOIN analytics_warehouse.dim_technician AS technician
            ON technician.technician_key = fact.technician_key
        WHERE fact.assigned_technician_id IS NOT NULL
          AND (%(site_id)s::uuid IS NULL OR fact.site_id = %(site_id)s::uuid)
          AND (
              %(start_date)s::date IS NULL
              OR (fact.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                 >= %(start_date)s::date
          )
          AND (
              %(end_date)s::date IS NULL
              OR (fact.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                 <= %(end_date)s::date
          )
        GROUP BY
            fact.assigned_technician_id,
            technician.employee_code,
            technician.display_name
        ORDER BY open_work_orders DESC, assigned_work_orders DESC, technician_id
        LIMIT %(limit)s::integer
        """
    ),
    MaintenanceAggregateQuery.MONTHLY_COMPLETION: _QuerySpec(
        """
        SELECT
            mart.month_start_date,
            mart.site_id,
            mart.site_code,
            mart.site_name,
            mart.total_work_orders,
            mart.completed_work_orders,
            mart.critical_work_orders,
            mart.unassigned_work_orders,
            mart.completion_rate_percent
        FROM analytics_marts.monthly_site_work_orders AS mart
        WHERE (%(site_id)s::uuid IS NULL OR mart.site_id = %(site_id)s::uuid)
          AND (
              %(start_date)s::date IS NULL
              OR mart.month_start_date >= date_trunc('month', %(start_date)s::date)::date
          )
          AND (
              %(end_date)s::date IS NULL
              OR mart.month_start_date <= date_trunc('month', %(end_date)s::date)::date
          )
        ORDER BY mart.month_start_date DESC, mart.site_id
        LIMIT %(limit)s::integer
        """
    ),
    MaintenanceAggregateQuery.COST_VARIANCE: _QuerySpec(
        """
        SELECT
            mart.month_start_date,
            mart.site_id,
            mart.site_code,
            mart.site_name,
            mart.total_estimated_cost,
            mart.total_actual_cost,
            mart.total_cost_variance,
            (
                mart.total_estimated_cost IS NOT NULL
                AND mart.total_actual_cost IS NOT NULL
            ) AS cost_data_available
        FROM analytics_marts.monthly_site_work_orders AS mart
        WHERE (%(site_id)s::uuid IS NULL OR mart.site_id = %(site_id)s::uuid)
          AND (
              %(start_date)s::date IS NULL
              OR mart.month_start_date >= date_trunc('month', %(start_date)s::date)::date
          )
          AND (
              %(end_date)s::date IS NULL
              OR mart.month_start_date <= date_trunc('month', %(end_date)s::date)::date
          )
        ORDER BY mart.month_start_date DESC, mart.site_id
        LIMIT %(limit)s::integer
        """
    ),
}


def _default_connection_factory(
    settings: DataPlatformSettings,
    *,
    read_only: bool,
) -> AbstractContextManager[_Connection]:
    return connect(settings, read_only=read_only)


class MaintenanceAnalyticsAdapter:
    """Execute only approved aggregate queries in read-only transactions."""

    def __init__(
        self,
        settings: DataPlatformSettings,
        *,
        connection_factory: Callable[..., AbstractContextManager[_Connection]] = (
            _default_connection_factory
        ),
    ) -> None:
        if settings is None:
            raise TypeError("Maintenance analytics settings must be injected explicitly.")
        self._settings = settings.validated()
        self._connection_factory = connection_factory

    def execute(
        self,
        query: MaintenanceAggregateQuery | str,
        *,
        parameters: Mapping[str, object] | None = None,
        limit: int = DEFAULT_MAINTENANCE_RESULTS,
    ) -> list[dict[str, Any]]:
        """Return a bounded result for one exact allow-listed query name."""

        selected = _select_query(query)
        bounded_limit = _validate_limit(limit)
        bound_parameters = _validate_parameters(
            parameters,
            allowed=_QUERY_SPECS[selected].parameter_names,
        )
        bound_parameters["limit"] = bounded_limit

        with self._connection_factory(
            self._settings,
            read_only=True,
        ) as connection:
            cursor = connection.execute(
                _QUERY_SPECS[selected].statement,
                bound_parameters,
            )
            # The static SQL already applies LIMIT.  fetchmany is an additional
            # memory/result boundary if a driver or test double violates it.
            rows = list(cursor.fetchmany(bounded_limit + 1))[:bounded_limit]
            columns = _column_names(cursor.description)

        return [_row_as_dict(row, columns) for row in rows]

    def run_query(
        self,
        query: MaintenanceAggregateQuery | str,
        *,
        parameters: Mapping[str, object] | None = None,
        limit: int = DEFAULT_MAINTENANCE_RESULTS,
    ) -> list[dict[str, Any]]:
        """Compatibility spelling for tool callers that name the operation."""

        return self.execute(query, parameters=parameters, limit=limit)


def _select_query(query: MaintenanceAggregateQuery | str) -> MaintenanceAggregateQuery:
    if isinstance(query, MaintenanceAggregateQuery):
        return query
    if not isinstance(query, str):
        raise UnsupportedMaintenanceQueryError(
            "Maintenance query must be selected from the approved aggregate catalog."
        )
    try:
        return MaintenanceAggregateQuery(query)
    except ValueError:
        raise UnsupportedMaintenanceQueryError(
            f"Unsupported maintenance aggregate query: {query!r}."
        ) from None


def _validate_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise InvalidMaintenanceQueryError("Result limit must be an integer.")
    if not 1 <= limit <= MAX_MAINTENANCE_RESULTS:
        raise InvalidMaintenanceQueryError(
            f"Result limit must be between 1 and {MAX_MAINTENANCE_RESULTS}."
        )
    return limit


def _validate_parameters(
    parameters: Mapping[str, object] | None,
    *,
    allowed: frozenset[str],
) -> dict[str, object]:
    if parameters is None:
        supplied: Mapping[str, object] = {}
    elif isinstance(parameters, Mapping):
        supplied = parameters
    else:
        raise InvalidMaintenanceQueryError("Query parameters must be a mapping.")

    unexpected = sorted(set(supplied) - allowed)
    if unexpected:
        raise InvalidMaintenanceQueryError(
            "Unsupported maintenance query parameters: " + ", ".join(unexpected)
        )

    normalized: dict[str, object] = {
        "site_id": None,
        "start_date": None,
        "end_date": None,
    }
    if "site_id" in supplied:
        normalized["site_id"] = _optional_uuid(supplied["site_id"], "site_id")
    if "start_date" in supplied:
        normalized["start_date"] = _optional_date(supplied["start_date"], "start_date")
    if "end_date" in supplied:
        normalized["end_date"] = _optional_date(supplied["end_date"], "end_date")

    start_date = normalized["start_date"]
    end_date = normalized["end_date"]
    if start_date is not None and end_date is not None and start_date > end_date:
        raise InvalidMaintenanceQueryError("start_date must not be after end_date.")
    return normalized


def _optional_uuid(value: object, name: str) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        raise InvalidMaintenanceQueryError(f"{name} must be a UUID or null.")
    try:
        return UUID(value)
    except ValueError:
        raise InvalidMaintenanceQueryError(f"{name} must be a valid UUID.") from None


def _optional_date(value: object, name: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        raise InvalidMaintenanceQueryError(f"{name} must be a date, not a datetime.")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise InvalidMaintenanceQueryError(f"{name} must be an ISO date or null.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InvalidMaintenanceQueryError(f"{name} must be a valid ISO date.") from None


def _column_names(description: Any) -> tuple[str, ...]:
    if description is None:
        raise RuntimeError("Maintenance aggregate query returned no result columns.")
    names: list[str] = []
    for column in description:
        name = getattr(column, "name", None)
        if name is None and isinstance(column, (tuple, list)) and column:
            name = column[0]
        if not isinstance(name, str) or not name:
            raise RuntimeError("Maintenance aggregate query returned invalid result metadata.")
        names.append(name)
    return tuple(names)


def _row_as_dict(row: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return {column: row[column] for column in columns}
    return dict(zip(columns, row, strict=True))


__all__ = [
    "APPROVED_MAINTENANCE_QUERIES",
    "DEFAULT_MAINTENANCE_RESULTS",
    "InvalidMaintenanceQueryError",
    "MAX_MAINTENANCE_RESULTS",
    "MaintenanceAggregateQuery",
    "MaintenanceAnalyticsAdapter",
    "UnsupportedMaintenanceQueryError",
]
