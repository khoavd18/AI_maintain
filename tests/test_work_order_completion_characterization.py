"""Characterize work-order completion and verification before extraction."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from src.asset_management.storage import LocalAttachmentStorage
from src.maintenance_management.errors import (
    MaintenanceAuthorizationError,
    MaintenanceConflictError,
    MaintenanceDomainError,
)
from src.maintenance_management.service import MaintenancePlanningService
from src.repositories.contracts import StoredRecord
from src.security.audit_context import AuditContext
from src.security.permissions import Role
from tests.auth_helpers import build_test_user


WORK_ORDER_ID = UUID("99999999-9999-4999-8999-999999999999")
MANAGER_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


@dataclass
class RecordingCompletionRepository:
    status: str = "in_progress"
    maintenance_log_id: str | None = None

    backend_name = "stub"

    def __post_init__(self) -> None:
        self.work_order_reads = 0
        self.asset_reads = 0
        self.complete_calls: list[dict[str, Any]] = []
        self.verify_calls: list[dict[str, Any]] = []

    def get_work_order(self, work_order_id: UUID) -> StoredRecord:
        self.work_order_reads += 1
        actor = _technician()
        return StoredRecord(
            {
                "id": str(work_order_id),
                "status": self.status,
                "maintenance_log_id": self.maintenance_log_id,
                "assigned_to_user_id": str(actor.id),
                "asset_id": "GENERATOR_001",
                "source_ticket_id": "TCK-000001",
                "preventive_plan_id": None,
                "work_order_type": "corrective",
                "due_date": date.today().isoformat(),
                "local_timezone": "Asia/Ho_Chi_Minh",
                "checklist": [
                    {
                        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                        "sequence": 1,
                        "is_required": True,
                        "safety_critical": True,
                        "result_status": "completed",
                        "response_type": "checkbox",
                        "boolean_value": True,
                    }
                ],
            },
            version=5,
        )

    def get_asset_state(self, asset_id: str) -> StoredRecord:
        self.asset_reads += 1
        return StoredRecord(
            {
                "asset_id": asset_id,
                "lifecycle_status": "active",
                "last_maintenance_date": "2026-01-01",
                "maintenance_interval_days": 30,
            }
        )

    def complete_work_order(
        self,
        work_order_id: UUID,
        work_order_updates: dict[str, Any],
        log_values: dict[str, Any],
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord:
        self.complete_calls.append(
            {
                "work_order_id": work_order_id,
                "work_order_updates": dict(work_order_updates),
                "log_values": dict(log_values),
                "expected_version": expected_version,
                "audit_context": audit_context,
            }
        )
        return StoredRecord(
            {
                "id": str(work_order_id),
                **work_order_updates,
                "status": "completed",
                "maintenance_log_id": "log-1",
            },
            version=expected_version + 1,
        )

    def verify_work_order(
        self,
        work_order_id: UUID,
        *,
        expected_version: int,
        verified_by_user_id: UUID,
        audit_context: AuditContext,
    ) -> StoredRecord:
        self.verify_calls.append(
            {
                "work_order_id": work_order_id,
                "expected_version": expected_version,
                "verified_by_user_id": verified_by_user_id,
                "audit_context": audit_context,
            }
        )
        return StoredRecord(
            {"id": str(work_order_id), "status": "verified"},
            version=expected_version + 1,
        )


def _technician() -> Any:
    return build_test_user(Role.TECHNICIAN, technician_id="TECH-001")


def _manager() -> Any:
    return replace(build_test_user(Role.PROPERTY_MANAGER), id=MANAGER_ID)


def _audit(actor: Any) -> AuditContext:
    return AuditContext(actor.id, actor.display_name, "work-order-completion")


def _service(
    repository: RecordingCompletionRepository, tmp_path: Path
) -> MaintenancePlanningService:
    return MaintenancePlanningService(
        repository,  # type: ignore[arg-type]
        LocalAttachmentStorage(tmp_path / "attachments"),
        attachment_max_size_bytes=1024,
    )


def _completion_request(maintenance_date: date) -> dict[str, Any]:
    return {
        "maintenance_date": maintenance_date,
        "inspection_result": "Inspection completed successfully.",
        "actions_taken": "Cleaned terminals and tested the generator.",
        "parts_replaced": None,
        "technician_note": "No abnormal vibration observed.",
        "maintenance_result": "resolved",
        "follow_up_required": False,
        "completion_summary": "Checklist complete and test run stable.",
        "safety_notes": "Isolation procedure followed.",
        "labor_minutes": 75,
    }


def test_completion_builds_one_atomic_work_order_and_log_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = RecordingCompletionRepository()
    fixed_now = datetime(2026, 8, 9, 4, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("src.maintenance_management.service._utc_now", lambda: fixed_now)
    service = _service(repository, tmp_path)
    actor = _technician()
    audit_context = _audit(actor)
    maintenance_date = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()

    result = service.complete_work_order(
        WORK_ORDER_ID,
        _completion_request(maintenance_date),
        expected_version=5,
        actor=actor,
        audit_context=audit_context,
    )

    assert len(repository.complete_calls) == 1
    command = repository.complete_calls[0]
    assert command["expected_version"] == 5
    assert command["audit_context"] is audit_context
    assert command["work_order_updates"] == {
        "status": "completed",
        "completed_at": fixed_now,
        "completion_summary": "Checklist complete and test run stable.",
        "safety_notes": "Isolation procedure followed.",
        "labor_minutes": 75,
        "hold_reason": None,
    }
    assert command["log_values"] == {
        "ticket_id": "TCK-000001",
        "asset_id": "GENERATOR_001",
        "maintenance_date": maintenance_date,
        "maintenance_type": "corrective",
        "technician_id": "TECH-001",
        "inspection_result": "Inspection completed successfully.",
        "actions_taken": "Cleaned terminals and tested the generator.",
        "parts_replaced": None,
        "technician_note": "No abnormal vibration observed.",
        "maintenance_result": "resolved",
        "follow_up_required": False,
        "next_maintenance_date": maintenance_date + timedelta(days=30),
    }
    assert result["maintenance_log_id"] == "log-1"


def test_completion_is_idempotent_for_an_existing_linked_log_without_writing(
    tmp_path: Path,
) -> None:
    repository = RecordingCompletionRepository(status="completed", maintenance_log_id="log-1")
    service = _service(repository, tmp_path)
    actor = _technician()

    result = service.complete_work_order(
        WORK_ORDER_ID,
        _completion_request(date.today()),
        expected_version=5,
        actor=actor,
        audit_context=_audit(actor),
    )

    assert result["maintenance_log_id"] == "log-1"
    assert repository.complete_calls == []


def test_completion_rejects_incomplete_or_future_work_without_partial_write(
    tmp_path: Path,
) -> None:
    repository = RecordingCompletionRepository()
    service = _service(repository, tmp_path)
    actor = _technician()
    audit_context = _audit(actor)

    future = date.today().replace(year=date.today().year + 1)
    with pytest.raises(MaintenanceDomainError):
        service.complete_work_order(
            WORK_ORDER_ID,
            _completion_request(future),
            expected_version=5,
            actor=actor,
            audit_context=audit_context,
        )
    assert repository.complete_calls == []

    repository.status = "assigned"
    with pytest.raises(MaintenanceConflictError):
        service.complete_work_order(
            WORK_ORDER_ID,
            _completion_request(date.today()),
            expected_version=5,
            actor=actor,
            audit_context=audit_context,
        )
    assert repository.complete_calls == []


def test_verification_requires_independent_actor_and_delegates_once(
    tmp_path: Path,
) -> None:
    repository = RecordingCompletionRepository(status="completed", maintenance_log_id="log-1")
    service = _service(repository, tmp_path)
    technician = _technician()
    manager = _manager()

    with pytest.raises(MaintenanceAuthorizationError):
        service.verify_work_order(
            WORK_ORDER_ID,
            expected_version=5,
            actor=technician,
            audit_context=_audit(technician),
        )
    assert repository.verify_calls == []

    result = service.verify_work_order(
        WORK_ORDER_ID,
        expected_version=5,
        actor=manager,
        audit_context=_audit(manager),
    )
    assert result["status"] == "verified"
    assert repository.verify_calls == [
        {
            "work_order_id": WORK_ORDER_ID,
            "expected_version": 5,
            "verified_by_user_id": manager.id,
            "audit_context": _audit(manager),
        }
    ]


def test_completion_collaborator_boundary_is_storage_neutral() -> None:
    source = Path("src/maintenance_management/application/work_order_completion_service.py")
    assert source.exists()
    contents = source.read_text(encoding="utf-8")
    assert "sqlalchemy" not in contents.lower()
    assert "src.repositories.postgres" not in contents
    assert "src.maintenance_management.service" not in contents
