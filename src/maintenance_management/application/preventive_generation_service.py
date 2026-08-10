"""Preventive work-order generation orchestration.

The service applies the bounded recurrence and paused-backlog policy, then
delegates one idempotent occurrence-generation command per plan. Occurrence
uniqueness, plan locking, checklist snapshots, audit, and commit/rollback remain
owned by the PostgreSQL maintenance repository.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from src.maintenance_management.errors import MaintenanceDomainError
from src.maintenance_management.recurrence import (
    MAX_OCCURRENCES,
    RecurrenceSpec,
    advance_occurrence,
    first_occurrence_on_or_after,
    occurrences_between,
)
from src.repositories.contracts import MaintenancePlanningRepository
from src.security.audit_context import AuditContext
from src.security.principal import CurrentUser


MAX_CATCH_UP_DAYS = 366


class PreventiveGenerationService:
    """Own bounded generation decisions and storage-neutral generation intent."""

    def __init__(
        self,
        repository_provider: Callable[[], MaintenancePlanningRepository],
        *,
        get_plan: Callable[[UUID], dict[str, Any]],
        list_plans: Callable[..., dict[str, Any]],
        get_asset: Callable[[str], dict[str, Any]],
        recurrence_spec: Callable[[dict[str, Any]], RecurrenceSpec],
        as_optional_date: Callable[[object | None], date | None],
        today: Callable[[], date],
    ) -> None:
        self._repository_provider = repository_provider
        self._get_plan = get_plan
        self._list_plans = list_plans
        self._get_asset = get_asset
        self._recurrence_spec = recurrence_spec
        self._as_optional_date = as_optional_date
        self._today = today

    def generate(
        self,
        *,
        as_of_date: date,
        plan_id: UUID | None,
        dry_run: bool,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        today = self._today()
        if abs((as_of_date - today).days) > MAX_CATCH_UP_DAYS:
            raise MaintenanceDomainError(
                "as_of_date phải nằm trong phạm vi 366 ngày quanh ngày hiện tại."
            )
        plans = (
            [self._get_plan(plan_id)]
            if plan_id
            else self._list_plans(
                asset_id=None,
                status="active",
                search=None,
                due_from=None,
                due_to=None,
                page=1,
                page_size=1000,
            )["items"]
        )
        reports = [
            self._generation_unit(
                plan,
                as_of_date=as_of_date,
                dry_run=dry_run,
                audit_context=audit_context,
            )
            for plan in plans
        ]
        return {
            "dry_run": dry_run,
            "as_of_date": as_of_date.isoformat(),
            "requested_by_user_id": str(actor.id),
            "generated_count": sum(len(item.get("generated", [])) for item in reports),
            "would_generate_count": sum(
                len(item.get("would_generate_due_dates", [])) for item in reports
            ),
            "skipped_count": sum(len(item.get("skipped_due_dates", [])) for item in reports),
            "plans": reports,
        }

    def _generation_unit(
        self,
        plan: dict[str, Any],
        *,
        as_of_date: date,
        dry_run: bool,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        if plan["status"] != "active" or not plan["next_due_date"]:
            return {
                "plan_id": plan["id"],
                "plan_code": plan["plan_code"],
                "generated": [],
                "would_generate_due_dates": [],
                "skipped_due_dates": [],
                "reason": "Plan không active hoặc đã hết occurrence.",
            }
        asset = self._get_asset(plan["asset_id"])
        if asset["lifecycle_status"] in {"retired", "archived"}:
            return {
                "plan_id": plan["id"],
                "plan_code": plan["plan_code"],
                "generated": [],
                "would_generate_due_dates": [],
                "skipped_due_dates": [],
                "reason": "Asset retired hoặc archived.",
            }
        spec = self._recurrence_spec(plan)
        first_due = date.fromisoformat(plan["next_due_date"])
        release_horizon = as_of_date + timedelta(days=int(plan["lead_time_days"]))
        catch_up_start = as_of_date - timedelta(days=MAX_CATCH_UP_DAYS)
        skipped_backlog: list[str] = []
        if first_due < catch_up_start:
            bounded_first = first_occurrence_on_or_after(spec, catch_up_start)
            skipped_backlog.append(f"before:{catch_up_start.isoformat()}")
        else:
            bounded_first = first_due
        if bounded_first is None or bounded_first > release_horizon:
            due_dates: list[date] = []
        else:
            due_dates = occurrences_between(
                spec,
                start=bounded_first,
                end=release_horizon,
                first_due=bounded_first,
                max_occurrences=MAX_OCCURRENCES,
            )
        repository = self._repository_provider()
        existing = repository.list_generated_due_dates(UUID(plan["id"]))
        would_generate = [value for value in due_dates if value not in existing]
        skipped = sorted(value for value in due_dates if value in existing)
        next_due = advance_occurrence(due_dates[-1], spec) if due_dates else first_due
        if spec.end_date is not None and next_due > spec.end_date:
            next_due = None
        if dry_run:
            return {
                "plan_id": plan["id"],
                "plan_code": plan["plan_code"],
                "generated": [],
                "would_generate_due_dates": [value.isoformat() for value in would_generate],
                "skipped_due_dates": [value.isoformat() for value in skipped] + skipped_backlog,
                "reason": None,
            }
        result = repository.generate_plan_occurrences(
            UUID(plan["id"]),
            schedule_signature={
                "interval_value": int(plan["interval_value"]),
                "interval_unit": plan["interval_unit"],
                "start_date": date.fromisoformat(plan["start_date"]),
                "end_date": self._as_optional_date(plan["end_date"]),
                "local_timezone": plan["local_timezone"],
                "status": "active",
            },
            due_dates=due_dates,
            next_due_date=next_due,
            audit_context=audit_context,
        )
        result["would_generate_due_dates"] = []
        result["skipped_due_dates"] = result["skipped_due_dates"] + skipped_backlog
        return result
