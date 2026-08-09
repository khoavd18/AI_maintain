"""Read-only maintenance options and recurrence preview operations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from src.config.value_mappings import MAINTENANCE_RESULT_CODE_TO_VI, PRIORITY_CODE_TO_VI
from src.maintenance_management.domain import (
    CHECKLIST_RESPONSE_TYPE_LABELS,
    INTERVAL_UNIT_LABELS,
    PLAN_STATUS_LABELS,
    WORK_ORDER_ATTACHMENT_CATEGORIES,
    WORK_ORDER_STATUS_LABELS,
    WORK_ORDER_TYPE_LABELS,
    IntervalUnit,
)
from src.maintenance_management.recurrence import RecurrenceSpec, occurrences_between
from src.repositories.contracts import MaintenancePlanningRepository


class MaintenanceCatalogueService:
    """Own read-only reference data and recurrence preview calculations."""

    def __init__(
        self,
        repository_provider: Callable[[], MaintenancePlanningRepository],
        get_plan: Callable[[UUID], dict[str, Any]],
    ) -> None:
        self._repository_provider = repository_provider
        self._get_plan = get_plan

    def options(self) -> dict[str, Any]:
        repository = self._repository_provider()
        return {
            "plan_statuses": _options(PLAN_STATUS_LABELS),
            "interval_units": _options(INTERVAL_UNIT_LABELS),
            "work_order_types": _options(WORK_ORDER_TYPE_LABELS),
            "work_order_statuses": _options(WORK_ORDER_STATUS_LABELS),
            "checklist_response_types": _options(CHECKLIST_RESPONSE_TYPE_LABELS),
            "priorities": _options(PRIORITY_CODE_TO_VI),
            "maintenance_results": _options(MAINTENANCE_RESULT_CODE_TO_VI),
            "evidence_categories": _options(WORK_ORDER_ATTACHMENT_CATEGORIES),
            "technicians": [record.values for record in repository.list_technicians()],
        }

    def preview_occurrences(
        self,
        plan_id: UUID,
        *,
        date_from: date,
        date_to: date,
        limit: int,
    ) -> dict[str, Any]:
        plan = self._get_plan(plan_id)
        spec = RecurrenceSpec(
            interval_value=int(plan["interval_value"]),
            interval_unit=IntervalUnit(plan["interval_unit"]),
            start_date=_as_date(plan["start_date"]),
            end_date=_as_optional_date(plan.get("end_date")),
            local_timezone=str(plan["local_timezone"]),
        )
        due_dates = occurrences_between(
            spec,
            start=date_from,
            end=date_to,
            first_due=_as_optional_date(plan.get("next_due_date")) or spec.start_date,
            max_occurrences=limit,
        )
        generated = self._repository_provider().list_generated_due_dates(plan_id)
        return {
            "plan_id": str(plan_id),
            "timezone": spec.local_timezone,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "items": [
                {
                    "due_date": value.isoformat(),
                    "generated": value in generated,
                    "generation_release_date": (
                        value - timedelta(days=int(plan["lead_time_days"]))
                    ).isoformat(),
                }
                for value in due_dates
            ],
        }


def _as_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _as_optional_date(value: object | None) -> date | None:
    return None if value is None or not str(value).strip() else _as_date(value)


def _options(labels: dict[Any, str]) -> list[dict[str, str]]:
    return [
        {"code": str(code.value if hasattr(code, "value") else code), "display_name": label}
        for code, label in labels.items()
    ]
