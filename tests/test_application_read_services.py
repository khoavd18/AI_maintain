from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest

from src.maintenance_management.application.catalogue_service import (
    MaintenanceCatalogueService,
)
from src.maintenance_management.application.preventive_generation_service import (
    MAX_CATCH_UP_DAYS,
)
from src.maintenance_management.domain import (
    WORK_ORDER_TRANSITIONS,
    WorkOrderStatus,
    WorkOrderType,
)
from src.maintenance_management.recurrence import (
    MAX_OCCURRENCES,
    first_occurrence_on_or_after,
    occurrences_between,
)
from src.maintenance_management import service as maintenance_service
from src.maintenance_management.errors import MaintenanceNotFoundError
from src.maintenance_management.service import MaintenancePlanningService
from src.repositories.contracts import StoredPage, StoredRecord
from src.security.permissions import Role
from src.ticket_management.application.catalogue_service import TicketCatalogueService
from src.ticket_management.service import TicketWorkflowService
from tests.auth_helpers import build_test_user


class TicketRepositoryStub:
    def reference_options(self):
        return {"assignees": [], "categories": []}


class TicketActorStub:
    def has(self, permission):
        return True


def test_ticket_facade_and_extracted_catalogue_return_the_same_read_models() -> None:
    repository = TicketRepositoryStub()
    facade = TicketWorkflowService(repository)  # type: ignore[arg-type]
    extracted = TicketCatalogueService(repository, lambda actor, permission: None)  # type: ignore[arg-type]
    actor = TicketActorStub()

    assert facade.options(actor=actor) == extracted.options(actor=actor)  # type: ignore[arg-type]
    assert facade.priority_preview(impact="high", urgency="high") == extracted.priority_preview(
        impact="high", urgency="high"
    )


class MaintenanceRepositoryStub:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def list_technicians(self):
        return [SimpleNamespace(values={"id": "tech-1", "display_name": "Kỹ thuật viên"})]

    def get_plan(self, plan_id):
        return SimpleNamespace(
            values={
                "id": str(plan_id),
                "interval_value": 1,
                "interval_unit": "month",
                "start_date": "2026-01-31",
                "end_date": None,
                "local_timezone": "Asia/Ho_Chi_Minh",
                "next_due_date": "2026-01-31",
                "lead_time_days": 3,
            }
        )

    def list_generated_due_dates(self, plan_id):
        return {date(2026, 2, 28)}

    def get_ticket_state(self, ticket_id):
        self.events.append(("get_ticket_state", ticket_id))
        if ticket_id == "TCK-MISSING":
            return None
        return StoredRecord({"ticket_id": ticket_id})

    def list_work_orders(self, *, filters, page, page_size):
        self.events.append(
            (
                "list_work_orders",
                {"filters": dict(filters), "page": page, "page_size": page_size},
            )
        )
        return StoredPage(
            items=[
                StoredRecord(
                    {
                        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                        "assigned_to_user_id": str(filters.get("assigned_to_user_id")),
                        "checklist": [],
                        "history": [],
                        "safety_notes": None,
                        "completion_summary": None,
                    }
                )
            ],
            page=page,
            page_size=page_size,
            total=1,
        )


def test_maintenance_facade_uses_extracted_read_catalogue_and_preview() -> None:
    repository = MaintenanceRepositoryStub()
    facade = MaintenancePlanningService(repository, object(), attachment_max_size_bytes=1000)  # type: ignore[arg-type]
    extracted = MaintenanceCatalogueService(facade._repository, facade.get_plan)

    assert facade.options() == extracted.options()
    plan_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    assert facade.preview_occurrences(
        plan_id, date_from=date(2026, 1, 1), date_to=date(2026, 3, 31), limit=10
    ) == extracted.preview_occurrences(
        plan_id, date_from=date(2026, 1, 1), date_to=date(2026, 3, 31), limit=10
    )


def test_maintenance_facade_preserves_historical_module_bindings() -> None:
    assert maintenance_service.MAX_CATCH_UP_DAYS == MAX_CATCH_UP_DAYS
    assert maintenance_service.MAX_OCCURRENCES == MAX_OCCURRENCES
    assert maintenance_service.WORK_ORDER_TRANSITIONS is WORK_ORDER_TRANSITIONS
    assert maintenance_service.WorkOrderStatus is WorkOrderStatus
    assert maintenance_service.WorkOrderType is WorkOrderType
    assert maintenance_service.first_occurrence_on_or_after is first_occurrence_on_or_after
    assert maintenance_service.occurrences_between is occurrences_between


def test_linked_work_orders_preserves_lookup_order_and_technician_scope() -> None:
    repository = MaintenanceRepositoryStub()
    facade = MaintenancePlanningService(
        repository,
        object(),
        attachment_max_size_bytes=1000,  # type: ignore[arg-type]
    )
    actor = build_test_user(Role.TECHNICIAN, technician_id="TECH-001")

    result = facade.linked_work_orders("TCK-001", actor=actor)

    assert result[0]["id"] == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert repository.events == [
        ("get_ticket_state", "TCK-001"),
        (
            "list_work_orders",
            {
                "filters": {
                    "source_ticket_id": "TCK-001",
                    "assigned_to_user_id": actor.id,
                },
                "page": 1,
                "page_size": 100,
            },
        ),
    ]


def test_linked_work_orders_missing_ticket_short_circuits_before_list() -> None:
    repository = MaintenanceRepositoryStub()
    facade = MaintenancePlanningService(
        repository,
        object(),
        attachment_max_size_bytes=1000,  # type: ignore[arg-type]
    )

    with pytest.raises(MaintenanceNotFoundError, match="TCK-MISSING"):
        facade.linked_work_orders("TCK-MISSING", actor=build_test_user(Role.CHIEF_ENGINEER))

    assert repository.events == [("get_ticket_state", "TCK-MISSING")]
