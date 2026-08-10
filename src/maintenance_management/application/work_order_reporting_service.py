"""Read-only work-order calendar and operational-metrics projections.

The reporting service composes existing repository reads without opening a
transaction. PostgreSQL query repositories retain session and projection
ownership; this module owns only range validation and read-model aggregation.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from src.maintenance_management.domain import WorkOrderStatus
from src.maintenance_management.errors import MaintenanceDomainError
from src.maintenance_management.recurrence import MAX_OCCURRENCES
from src.repositories.contracts import MaintenancePlanningRepository
from src.security.principal import CurrentUser


class WorkOrderReportingService:
    """Build bounded calendar and work-order metric read models."""

    def __init__(
        self,
        repository_provider: Callable[[], MaintenancePlanningRepository],
        *,
        list_work_orders: Callable[..., dict[str, Any]],
        list_plans: Callable[..., dict[str, Any]],
        preview_occurrences: Callable[..., dict[str, Any]],
    ) -> None:
        self._repository_provider = repository_provider
        self._list_work_orders = list_work_orders
        self._list_plans = list_plans
        self._preview_occurrences = preview_occurrences

    def schedule_view(
        self,
        *,
        actor: CurrentUser,
        date_from: date,
        date_to: date,
        asset_id: str | None,
        assigned_to_user_id: UUID | None,
    ) -> dict[str, Any]:
        if (date_to - date_from).days > 366 or date_to < date_from:
            raise MaintenanceDomainError("Calendar range phải nằm trong 0–366 ngày.")
        work_orders = self._list_work_orders(
            actor=actor,
            filters={
                "asset_id": asset_id,
                "assigned_to_user_id": assigned_to_user_id,
                "due_from": date_from,
                "due_to": date_to,
            },
            page=1,
            page_size=1000,
        )["items"]
        plans = self._list_plans(
            asset_id=asset_id,
            status="active",
            search=None,
            due_from=None,
            due_to=None,
            page=1,
            page_size=1000,
        )["items"]
        occurrences: list[dict[str, Any]] = []
        for plan in plans:
            preview = self._preview_occurrences(
                UUID(plan["id"]),
                date_from=date_from,
                date_to=date_to,
                limit=MAX_OCCURRENCES,
            )
            occurrences.extend(
                {
                    **item,
                    "plan_id": plan["id"],
                    "plan_code": plan["plan_code"],
                    "plan_name": plan["name"],
                    "asset_id": plan["asset_id"],
                }
                for item in preview["items"]
            )
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "work_orders": work_orders,
            "upcoming_occurrences": occurrences,
        }

    def metrics(self, *, as_of_date: date) -> dict[str, Any]:
        page = self._repository_provider().list_work_orders(filters={}, page=1, page_size=1000)
        items = [record.values for record in page.items]
        statuses = {
            status.value: sum(item["status"] == status.value for item in items)
            for status in WorkOrderStatus
        }
        completed = [item for item in items if item["status"] in {"completed", "verified"}]
        completed_on_time = sum(
            bool(item["completed_at"])
            and datetime.fromisoformat(item["completed_at"]).date()
            <= date.fromisoformat(item["due_date"]) + timedelta(days=int(item["grace_period_days"]))
            for item in completed
        )
        workload: dict[str, dict[str, Any]] = {}
        for item in items:
            if not item["assigned_to_user_id"] or item["status"] in {
                "verified",
                "cancelled",
            }:
                continue
            key = item["assigned_to_user_id"]
            bucket = workload.setdefault(
                key,
                {
                    "user_id": key,
                    "display_name": item["assigned_to_name"],
                    "open_count": 0,
                },
            )
            bucket["open_count"] += 1
        return {
            "as_of_date": as_of_date.isoformat(),
            "total_work_orders": len(items),
            "by_status": statuses,
            "overdue_count": sum(
                item["status"] not in {"verified", "cancelled"}
                and date.fromisoformat(item["due_date"])
                + timedelta(days=int(item["grace_period_days"]))
                < as_of_date
                for item in items
            ),
            "upcoming_preventive_count": sum(
                item["work_order_type"] == "preventive"
                and item["status"] not in {"verified", "cancelled"}
                and as_of_date
                <= date.fromisoformat(item["due_date"])
                <= as_of_date + timedelta(days=30)
                for item in items
            ),
            "completed_count": len(completed),
            "verified_count": statuses["verified"],
            "completed_on_time_count": completed_on_time,
            "technician_workload": sorted(
                workload.values(),
                key=lambda item: (-item["open_count"], item["display_name"]),
            ),
            "data_notice": "Chỉ số vận hành trên dữ liệu synthetic/internal-pilot.",
        }
