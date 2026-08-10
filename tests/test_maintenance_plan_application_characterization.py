"""Characterize preventive-plan commands before application extraction."""

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


PLAN_ID = UUID("11111111-1111-4111-8111-111111111111")


@dataclass
class RecordingPlanRepository:
    plan: StoredRecord | None = None
    asset_lifecycle_status: str = "active"

    backend_name = "stub"

    def __post_init__(self) -> None:
        self.asset_reads = 0
        self.plan_reads = 0
        self.create_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []

    def get_asset_state(self, asset_id: str) -> StoredRecord:
        self.asset_reads += 1
        return StoredRecord(
            {
                "asset_id": asset_id,
                "asset_type": "generator",
                "lifecycle_status": self.asset_lifecycle_status,
            }
        )

    def get_plan(self, plan_id: UUID) -> StoredRecord | None:
        assert plan_id == PLAN_ID
        self.plan_reads += 1
        return self.plan

    def get_user_state(self, user_id: UUID) -> StoredRecord | None:
        del user_id
        return None

    def get_template(self, template_id: UUID) -> StoredRecord | None:
        del template_id
        return None

    def create_plan(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext,
    ) -> StoredRecord:
        self.create_calls.append({"values": dict(values), "audit_context": audit_context})
        self.plan = StoredRecord(
            {"id": str(PLAN_ID), **values, "version": 1},
            version=1,
        )
        return self.plan

    def update_plan(
        self,
        plan_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_actions: list[str],
        audit_context: AuditContext,
    ) -> StoredRecord:
        assert self.plan is not None
        call = {
            "plan_id": plan_id,
            "updates": dict(updates),
            "expected_version": expected_version,
            "audit_actions": list(audit_actions),
            "audit_context": audit_context,
        }
        self.update_calls.append(call)
        next_version = expected_version + 1
        self.plan = StoredRecord(
            {**self.plan.values, **updates, "version": next_version},
            version=next_version,
        )
        return self.plan


def _service(repository: RecordingPlanRepository, tmp_path: Path) -> MaintenancePlanningService:
    return MaintenancePlanningService(
        repository,  # type: ignore[arg-type]
        LocalAttachmentStorage(tmp_path / "attachments"),
        attachment_max_size_bytes=1024,
    )


def _plan_record(*, status: str = "active") -> StoredRecord:
    actor = build_test_user(Role.CHIEF_ENGINEER)
    return StoredRecord(
        {
            "id": str(PLAN_ID),
            "plan_code": "PM_GENERATOR_001",
            "name": "Generator plan",
            "description": None,
            "asset_id": "GENERATOR_001",
            "interval_value": 1,
            "interval_unit": "month",
            "start_date": "2024-01-31",
            "end_date": "2025-12-31",
            "local_timezone": "Asia/Ho_Chi_Minh",
            "lead_time_days": 7,
            "grace_period_days": 1,
            "next_due_date": "2024-03-31",
            "last_generated_due_date": "2024-02-29",
            "estimated_duration_minutes": 60,
            "default_priority": "high",
            "default_assignee_user_id": None,
            "checklist_template_id": None,
            "instructions": None,
            "recurrence_rule": None,
            "status": status,
            "is_active": status == "active",
            "paused_at": None,
            "archived_at": None,
            "archive_reason": None,
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
            "version": 4,
        },
        version=4,
    )


def _create_request() -> dict[str, Any]:
    return {
        "plan_code": " pm_generator_001 ",
        "name": "  Generator preventive plan  ",
        "description": "   ",
        "asset_id": "GENERATOR_001",
        "interval_value": 1,
        "interval_unit": "month",
        "start_date": date(2024, 1, 31),
        "end_date": date(2025, 12, 31),
        "local_timezone": "Asia/Ho_Chi_Minh",
        "lead_time_days": 7,
        "grace_period_days": 1,
        "estimated_duration_minutes": 60,
        "default_priority": "high",
        "default_assignee_user_id": None,
        "checklist_template_id": None,
        "instructions": None,
        "recurrence_rule": None,
    }


def test_create_plan_normalizes_command_and_delegates_one_atomic_create(
    tmp_path: Path,
) -> None:
    repository = RecordingPlanRepository()
    service = _service(repository, tmp_path)
    actor = build_test_user(Role.CHIEF_ENGINEER)
    audit_context = AuditContext(actor.id, actor.display_name, "plan-create")

    result = service.create_plan(_create_request(), actor=actor, audit_context=audit_context)

    assert repository.asset_reads == 1
    assert len(repository.create_calls) == 1
    command = repository.create_calls[0]
    assert command["audit_context"] is audit_context
    assert command["values"] == {
        **_create_request(),
        "plan_code": "PM_GENERATOR_001",
        "name": "Generator preventive plan",
        "description": None,
        "schedule_type": "interval",
        "recurrence_rule": None,
        "next_due_date": date(2024, 1, 31),
        "last_generated_due_date": None,
        "status": "active",
        "is_active": True,
        "paused_at": None,
        "archived_at": None,
        "archive_reason": None,
        "created_by_user_id": actor.id,
        "updated_by_user_id": actor.id,
    }
    assert result["status"] == "active"


def test_create_plan_rejects_ineligible_asset_and_raw_recurrence_without_mutation(
    tmp_path: Path,
) -> None:
    repository = RecordingPlanRepository(asset_lifecycle_status="retired")
    service = _service(repository, tmp_path)
    actor = build_test_user(Role.CHIEF_ENGINEER)
    audit_context = AuditContext(actor.id, actor.display_name, "plan-invalid")

    with pytest.raises(MaintenanceConflictError):
        service.create_plan(_create_request(), actor=actor, audit_context=audit_context)

    repository.asset_lifecycle_status = "active"
    request = {**_create_request(), "recurrence_rule": "FREQ=MONTHLY"}
    with pytest.raises(MaintenanceDomainError):
        service.create_plan(request, actor=actor, audit_context=audit_context)

    assert repository.asset_reads == 2
    assert repository.create_calls == []


def test_update_plan_reanchors_only_ungenerated_schedule_and_preserves_audit_order(
    tmp_path: Path,
) -> None:
    repository = RecordingPlanRepository(plan=_plan_record())
    service = _service(repository, tmp_path)
    actor = build_test_user(Role.CHIEF_ENGINEER)
    audit_context = AuditContext(actor.id, actor.display_name, "plan-update")

    result = service.update_plan(
        PLAN_ID,
        {"name": "  Revised generator plan  ", "interval_value": 2},
        expected_version=4,
        actor=actor,
        audit_context=audit_context,
    )

    assert repository.plan_reads == 1
    assert len(repository.update_calls) == 1
    command = repository.update_calls[0]
    assert command["plan_id"] == PLAN_ID
    assert command["expected_version"] == 4
    assert command["audit_actions"] == [
        "maintenance_plan.updated",
        "maintenance_plan.schedule_changed",
    ]
    assert command["audit_context"] is audit_context
    assert command["updates"] == {
        "name": "Revised generator plan",
        "interval_value": 2,
        "next_due_date": date(2024, 3, 31),
        "updated_by_user_id": actor.id,
    }
    assert result["next_due_date"] == date(2024, 3, 31)


def test_update_plan_rejects_empty_or_required_null_commands_before_mutation(
    tmp_path: Path,
) -> None:
    repository = RecordingPlanRepository(plan=_plan_record())
    service = _service(repository, tmp_path)
    actor = build_test_user(Role.CHIEF_ENGINEER)
    audit_context = AuditContext(actor.id, actor.display_name, "plan-empty")

    with pytest.raises(MaintenanceDomainError):
        service.update_plan(
            PLAN_ID,
            {},
            expected_version=4,
            actor=actor,
            audit_context=audit_context,
        )
    assert repository.plan_reads == 0

    with pytest.raises(MaintenanceDomainError):
        service.update_plan(
            PLAN_ID,
            {"interval_value": None},
            expected_version=4,
            actor=actor,
            audit_context=audit_context,
        )

    assert repository.plan_reads == 1
    assert repository.update_calls == []


def test_pause_resume_archive_keep_state_payloads_and_one_repository_call_each(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = RecordingPlanRepository(plan=_plan_record())
    fixed_now = datetime(2026, 8, 9, 4, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("src.maintenance_management.service._utc_now", lambda: fixed_now)
    service = _service(repository, tmp_path)
    actor = build_test_user(Role.CHIEF_ENGINEER)
    audit_context = AuditContext(actor.id, actor.display_name, "plan-lifecycle")

    paused = service.pause_plan(
        PLAN_ID,
        expected_version=4,
        actor=actor,
        audit_context=audit_context,
    )
    assert paused["status"] == "paused"
    assert repository.update_calls[0]["updates"] == {
        "status": "paused",
        "is_active": False,
        "paused_at": fixed_now,
        "updated_by_user_id": actor.id,
    }
    assert repository.update_calls[0]["audit_actions"] == ["maintenance_plan.paused"]

    with pytest.raises(MaintenanceConflictError):
        service.pause_plan(
            PLAN_ID,
            expected_version=5,
            actor=actor,
            audit_context=audit_context,
        )
    assert len(repository.update_calls) == 1

    resumed = service.resume_plan(
        PLAN_ID,
        expected_version=5,
        resume_date=date(2024, 4, 1),
        actor=actor,
        audit_context=audit_context,
    )
    assert resumed["status"] == "active"
    assert repository.update_calls[1]["updates"] == {
        "status": "active",
        "is_active": True,
        "paused_at": None,
        "next_due_date": date(2024, 4, 30),
        "updated_by_user_id": actor.id,
    }
    assert repository.update_calls[1]["audit_actions"] == ["maintenance_plan.resumed"]

    archived = service.archive_plan(
        PLAN_ID,
        expected_version=6,
        archive_reason="  Replaced by a newer controlled plan  ",
        actor=actor,
        audit_context=audit_context,
    )
    assert archived["status"] == "archived"
    assert repository.update_calls[2]["updates"] == {
        "status": "archived",
        "is_active": False,
        "paused_at": None,
        "archived_at": fixed_now,
        "archive_reason": "Replaced by a newer controlled plan",
        "updated_by_user_id": actor.id,
    }
    assert repository.update_calls[2]["audit_actions"] == ["maintenance_plan.archived"]


def test_preventive_plan_collaborator_is_storage_neutral_and_facade_keeps_seams() -> None:
    collaborator = Path(
        "src/maintenance_management/application/preventive_plan_service.py"
    ).read_text(encoding="utf-8")
    facade = Path("src/maintenance_management/service.py").read_text(encoding="utf-8")

    assert "sqlalchemy" not in collaborator.lower()
    assert "src.repositories.postgres" not in collaborator
    assert "src.maintenance_management.service" not in collaborator
    for method in ("create_plan", "update_plan", "pause_plan", "resume_plan", "archive_plan"):
        assert f"return self.plans.{method}(" in facade
