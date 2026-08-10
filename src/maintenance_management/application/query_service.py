"""Maintenance plan and work-order query capability."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from src.maintenance_management.domain import PlanStatus
from src.repositories.contracts import MaintenancePlanningRepository, StoredPage, StoredRecord
from src.security.permissions import Role
from src.security.principal import CurrentUser


class MaintenanceQueryService:
    """Own pagination, technician scoping, and read-model shaping."""

    def __init__(
        self,
        repository_provider: Callable[[], MaintenancePlanningRepository],
        *,
        get_plan: Callable[[UUID], dict[str, Any]],
        get_ticket: Callable[[str], dict[str, Any]],
        get_work_order_record: Callable[[UUID], StoredRecord],
        require_work_order_access: Callable[[dict[str, Any], CurrentUser], None],
        scope_work_order: Callable[[dict[str, Any], CurrentUser], dict[str, Any]],
    ) -> None:
        self._repository_provider = repository_provider
        self._get_plan = get_plan
        self._get_ticket = get_ticket
        self._get_work_order_record = get_work_order_record
        self._require_work_order_access = require_work_order_access
        self._scope_work_order = scope_work_order

    def list_plans(
        self,
        *,
        asset_id: str | None,
        status: str | None,
        search: str | None,
        due_from: Any,
        due_to: Any,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        if status is not None:
            PlanStatus(status)
        page_result = self._repository_provider().list_plans(
            filters={
                "asset_id": asset_id,
                "status": status,
                "search": search,
                "due_from": due_from,
                "due_to": due_to,
            },
            page=page,
            page_size=page_size,
        )
        return _page_values(page_result)

    def get_plan(self, plan_id: UUID) -> dict[str, Any]:
        return self._get_plan(plan_id)

    def list_work_orders(
        self,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        scoped = dict(filters)
        if actor.role is Role.TECHNICIAN:
            scoped["assigned_to_user_id"] = actor.id
        page_result = self._repository_provider().list_work_orders(
            filters=scoped, page=page, page_size=page_size
        )
        return {
            **_page_values(page_result),
            "items": [self._scope_work_order(item.values, actor) for item in page_result.items],
        }

    def get_work_order(self, work_order_id: UUID, *, actor: CurrentUser) -> dict[str, Any]:
        record = self._get_work_order_record(work_order_id)
        self._require_work_order_access(record.values, actor)
        return self._scope_work_order(record.values, actor)

    def linked_work_orders(self, ticket_id: str, *, actor: CurrentUser) -> list[dict[str, Any]]:
        self._get_ticket(ticket_id)
        return self.list_work_orders(
            actor=actor,
            filters={"source_ticket_id": ticket_id},
            page=1,
            page_size=100,
        )["items"]


def _page_values(page: StoredPage) -> dict[str, Any]:
    total_pages = (page.total + page.page_size - 1) // page.page_size if page.total else 0
    return {
        "items": [dict(record.values) for record in page.items],
        "page": page.page,
        "page_size": page.page_size,
        "total": page.total,
        "total_pages": total_pages,
    }
