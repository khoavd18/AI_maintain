"""Characterize work-order planning commands before application extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from src.asset_management.storage import LocalAttachmentStorage
from src.maintenance_management.errors import MaintenanceConflictError, MaintenanceDomainError
from src.maintenance_management.service import MaintenancePlanningService
from src.repositories.contracts import StoredRecord
from src.security.audit_context import AuditContext
from src.security.permissions import Role
from tests.auth_helpers import build_test_user


PLAN_ID = UUID("22222222-2222-4222-8222-222222222222")
TEMPLATE_ID = UUID("33333333-3333-4333-8333-333333333333")
TEMPLATE_ITEM_ID = UUID("44444444-4444-4444-8444-444444444444")
TECHNICIAN_ID = UUID("55555555-5555-4555-8555-555555555555")
WORK_ORDER_ID = UUID("66666666-6666-4666-8666-666666666666")


@dataclass
class RecordingWorkOrderRepository:
    work_order_status: str = "planned"

    backend_name = "stub"

    def __post_init__(self) -> None:
        self.asset_reads = 0
        self.ticket_reads = 0
        self.plan_reads = 0
        self.template_reads = 0
        self.user_reads = 0
        self.work_order_reads = 0
        self.create_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []

    def get_asset_state(self, asset_id: str) -> StoredRecord:
        self.asset_reads += 1
        return StoredRecord(
            {
                "asset_id": asset_id,
                "asset_type": "generator",
                "lifecycle_status": "active",
            }
        )

    def get_ticket_state(self, ticket_id: str) -> StoredRecord:
        self.ticket_reads += 1
        return StoredRecord(
            {
                "ticket_id": ticket_id,
                "asset_id": "GENERATOR_001",
                "status": "open",
                "issue_description": "Generator has an intermittent alarm.",
                "priority": "critical",
            }
        )

    def get_plan(self, plan_id: UUID) -> StoredRecord:
        self.plan_reads += 1
        return StoredRecord(
            {
                "id": str(plan_id),
                "asset_id": "GENERATOR_001",
                "status": "active",
            }
        )

    def get_template(self, template_id: UUID) -> StoredRecord:
        self.template_reads += 1
        return StoredRecord(
            {
                "id": str(template_id),
                "status": "active",
                "asset_type": "generator",
                "items": [
                    {
                        "id": str(TEMPLATE_ITEM_ID),
                        "sequence": 1,
                        "instruction": "Check the emergency stop circuit.",
                        "response_type": "checkbox",
                        "is_required": True,
                        "safety_critical": True,
                        "allow_not_applicable": False,
                        "expected_unit": None,
                        "minimum_value": None,
                        "maximum_value": None,
                        "guidance": "Isolate energy before inspection.",
                    }
                ],
            }
        )

    def get_user_state(self, user_id: UUID) -> StoredRecord:
        self.user_reads += 1
        return StoredRecord(
            {
                "id": str(user_id),
                "role": "technician",
                "is_active": True,
                "technician_id": "TECH-001",
            }
        )

    def get_work_order(self, work_order_id: UUID) -> StoredRecord:
        self.work_order_reads += 1
        return StoredRecord(
            {
                "id": str(work_order_id),
                "status": self.work_order_status,
                "assigned_to_user_id": None,
                "scheduled_start_at": None,
                "scheduled_end_at": None,
            },
            version=7,
        )

    def create_work_order(
        self,
        values: dict[str, Any],
        checklist_items: list[dict[str, Any]],
        *,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        self.create_calls.append(
            {
                "values": dict(values),
                "checklist_items": [dict(item) for item in checklist_items],
                "audit_action": audit_action,
                "audit_context": audit_context,
            }
        )
        return StoredRecord({"id": str(WORK_ORDER_ID), **values}, version=1)

    def update_work_order(
        self,
        work_order_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_action: str,
        audit_context: AuditContext,
        audit_metadata: dict[str, Any] | None = None,
    ) -> StoredRecord:
        self.update_calls.append(
            {
                "work_order_id": work_order_id,
                "updates": dict(updates),
                "expected_version": expected_version,
                "audit_action": audit_action,
                "audit_context": audit_context,
                "audit_metadata": audit_metadata,
            }
        )
        return StoredRecord({"id": str(work_order_id), **updates}, version=expected_version + 1)


def _service(
    repository: RecordingWorkOrderRepository, tmp_path: Path
) -> MaintenancePlanningService:
    return MaintenancePlanningService(
        repository,  # type: ignore[arg-type]
        LocalAttachmentStorage(tmp_path / "attachments"),
        attachment_max_size_bytes=1024,
    )


def _actor() -> Any:
    return build_test_user(Role.CHIEF_ENGINEER)


def _audit(actor: Any) -> AuditContext:
    return AuditContext(actor.id, actor.display_name, "work-order-planning")


def _create_request() -> dict[str, Any]:
    return {
        "title": "  Monthly generator inspection  ",
        "description": "  Inspect the generator before the planned test.  ",
        "work_order_type": "preventive",
        "asset_id": "GENERATOR_001",
        "preventive_plan_id": PLAN_ID,
        "source_ticket_id": None,
        "assigned_to_user_id": TECHNICIAN_ID,
        "priority": "high",
        "scheduled_start_at": datetime(2026, 8, 10, 1, tzinfo=timezone.utc),
        "scheduled_end_at": datetime(2026, 8, 10, 2, tzinfo=timezone.utc),
        "due_date": date(2026, 8, 10),
        "local_timezone": "Asia/Ho_Chi_Minh",
        "grace_period_days": 1,
        "estimated_duration_minutes": 90,
        "checklist_template_id": TEMPLATE_ID,
    }


def test_create_work_order_builds_one_normalized_command_and_template_snapshot(
    tmp_path: Path,
) -> None:
    repository = RecordingWorkOrderRepository()
    service = _service(repository, tmp_path)
    actor = _actor()
    audit_context = _audit(actor)

    result = service.create_work_order(_create_request(), actor=actor, audit_context=audit_context)

    assert len(repository.create_calls) == 1
    command = repository.create_calls[0]
    assert command["audit_context"] is audit_context
    assert command["audit_action"] == "work_order.created"
    values = command["values"]
    assert values["title"] == "Monthly generator inspection"
    assert values["description"] == "Inspect the generator before the planned test."
    assert values["status"] == "assigned"
    assert values["asset_id"] == "GENERATOR_001"
    assert values["preventive_plan_id"] == PLAN_ID
    assert values["assigned_to_user_id"] == TECHNICIAN_ID
    assert values["created_by_user_id"] == actor.id
    assert values["local_timezone"] == "Asia/Ho_Chi_Minh"
    assert len(command["checklist_items"]) == 1
    assert command["checklist_items"][0] == {
        "source_template_item_id": TEMPLATE_ITEM_ID,
        "sequence": 1,
        "instruction": "Check the emergency stop circuit.",
        "response_type": "checkbox",
        "is_required": True,
        "safety_critical": True,
        "allow_not_applicable": False,
        "expected_unit": None,
        "minimum_value": None,
        "maximum_value": None,
        "guidance": "Isolate energy before inspection.",
        "result_status": "pending",
        "boolean_value": None,
        "numeric_value": None,
        "text_value": None,
        "note": None,
        "completed_by_user_id": None,
        "completed_at": None,
    }
    assert result["id"] == str(WORK_ORDER_ID)


def test_corrective_creation_uses_ticket_defaults_without_resolving_ticket(
    tmp_path: Path,
) -> None:
    repository = RecordingWorkOrderRepository()
    service = _service(repository, tmp_path)
    actor = _actor()
    audit_context = _audit(actor)

    result = service.create_corrective_from_ticket(
        "TCK-000001",
        {
            "title": None,
            "description": None,
            "assigned_to_user_id": None,
            "priority": None,
            "scheduled_start_at": None,
            "scheduled_end_at": None,
            "due_date": date(2026, 8, 10),
            "local_timezone": "Asia/Ho_Chi_Minh",
            "grace_period_days": 0,
            "estimated_duration_minutes": 45,
            "checklist_template_id": None,
        },
        actor=actor,
        audit_context=audit_context,
    )

    assert len(repository.create_calls) == 1
    command = repository.create_calls[0]
    assert command["audit_action"] == "work_order.created_from_ticket"
    assert command["values"]["title"] == "Xử lý TCK-000001"
    assert command["values"]["description"] == "Generator has an intermittent alarm."
    assert command["values"]["priority"] == "critical"
    assert command["values"]["source_ticket_id"] == "TCK-000001"
    assert command["values"]["work_order_type"] == "corrective"
    assert result["status"] == "planned"
    assert repository.ticket_reads == 2


def test_work_order_planning_rejects_invalid_relationship_before_write(
    tmp_path: Path,
) -> None:
    repository = RecordingWorkOrderRepository()
    service = _service(repository, tmp_path)
    actor = _actor()
    audit_context = _audit(actor)

    repository.get_plan = lambda plan_id: StoredRecord(  # type: ignore[method-assign]
        {"id": str(plan_id), "asset_id": "OTHER_ASSET", "status": "active"}
    )
    with pytest.raises(MaintenanceConflictError):
        service.create_work_order(_create_request(), actor=actor, audit_context=audit_context)
    assert repository.create_calls == []

    repository.get_plan = RecordingWorkOrderRepository.get_plan.__get__(repository)  # type: ignore[method-assign]
    invalid = {**_create_request(), "priority": "urgent"}
    with pytest.raises(MaintenanceDomainError):
        service.create_work_order(invalid, actor=actor, audit_context=audit_context)
    assert repository.create_calls == []


def test_update_and_assign_preserve_state_guards_and_repository_command_shape(
    tmp_path: Path,
) -> None:
    repository = RecordingWorkOrderRepository()
    service = _service(repository, tmp_path)
    actor = _actor()
    audit_context = _audit(actor)

    updated = service.update_work_order(
        WORK_ORDER_ID,
        {
            "title": "  Revised title  ",
            "scheduled_start_at": datetime(2026, 8, 10, 1, tzinfo=timezone.utc),
            "scheduled_end_at": datetime(2026, 8, 10, 2, tzinfo=timezone.utc),
        },
        expected_version=7,
        actor=actor,
        audit_context=audit_context,
    )
    assert updated["id"] == str(WORK_ORDER_ID)
    assert repository.update_calls[0] == {
        "work_order_id": WORK_ORDER_ID,
        "updates": {
            "title": "Revised title",
            "scheduled_start_at": datetime(2026, 8, 10, 1, tzinfo=timezone.utc),
            "scheduled_end_at": datetime(2026, 8, 10, 2, tzinfo=timezone.utc),
        },
        "expected_version": 7,
        "audit_action": "work_order.updated",
        "audit_context": audit_context,
        "audit_metadata": None,
    }

    assigned = service.assign_work_order(
        WORK_ORDER_ID,
        assigned_to_user_id=TECHNICIAN_ID,
        expected_version=8,
        audit_context=audit_context,
    )
    assert assigned["id"] == str(WORK_ORDER_ID)
    assert repository.update_calls[1]["updates"] == {
        "assigned_to_user_id": TECHNICIAN_ID,
        "status": "assigned",
    }
    assert repository.update_calls[1]["audit_action"] == "work_order.assigned"

    repository.work_order_status = "in_progress"
    with pytest.raises(MaintenanceConflictError):
        service.update_work_order(
            WORK_ORDER_ID,
            {"title": "Cannot change execution"},
            expected_version=9,
            actor=actor,
            audit_context=audit_context,
        )
    assert len(repository.update_calls) == 2


def test_work_order_planning_collaborator_boundary_is_storage_neutral() -> None:
    source = Path("src/maintenance_management/application/work_order_planning_service.py")
    assert source.exists()
    contents = source.read_text(encoding="utf-8")
    assert "sqlalchemy" not in contents.lower()
    assert "src.repositories.postgres" not in contents
    assert "src.maintenance_management.service" not in contents
