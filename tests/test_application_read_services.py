from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import UUID

from src.maintenance_management.application.catalogue_service import (
    MaintenanceCatalogueService,
)
from src.maintenance_management.service import MaintenancePlanningService
from src.ticket_management.application.catalogue_service import TicketCatalogueService
from src.ticket_management.service import TicketWorkflowService


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
