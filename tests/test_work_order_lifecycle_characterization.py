"""Characterize work-order execution-state commands before extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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


WORK_ORDER_ID = UUID("77777777-7777-4777-8777-777777777777")
CHECKLIST_ID = UUID("88888888-8888-4888-8888-888888888888")


@dataclass
class RecordingLifecycleRepository:
    status: str = "assigned"

    backend_name = "stub"

    def __post_init__(self) -> None:
        self.reads = 0
        self.calls: list[dict[str, Any]] = []
        self.checklist_calls: list[dict[str, Any]] = []

    def get_work_order(self, work_order_id: UUID) -> StoredRecord:
        self.reads += 1
        return StoredRecord(
            {
                "id": str(work_order_id),
                "status": self.status,
                "assigned_to_user_id": str(_actor().id),
                "started_at": None,
                "hold_reason": None,
                "checklist": [
                    {
                        "id": str(CHECKLIST_ID),
                        "response_type": "checkbox",
                        "allow_not_applicable": False,
                        "minimum_value": None,
                        "maximum_value": None,
                        "is_required": True,
                        "result_status": "pending",
                        "boolean_value": None,
                    }
                ],
            },
            version=3,
        )

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
        self.calls.append(
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

    def update_checklist(
        self,
        work_order_id: UUID,
        responses: list[dict[str, Any]],
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord:
        self.checklist_calls.append(
            {
                "work_order_id": work_order_id,
                "responses": [dict(item) for item in responses],
                "expected_version": expected_version,
                "audit_context": audit_context,
            }
        )
        return StoredRecord(
            {"id": str(work_order_id), "checklist": responses}, version=expected_version + 1
        )


def _actor() -> Any:
    return build_test_user(Role.TECHNICIAN, technician_id="TECH-001")


def _audit(actor: Any) -> AuditContext:
    return AuditContext(actor.id, actor.display_name, "work-order-lifecycle")


def _service(
    repository: RecordingLifecycleRepository, tmp_path: Path
) -> MaintenancePlanningService:
    return MaintenancePlanningService(
        repository,  # type: ignore[arg-type]
        LocalAttachmentStorage(tmp_path / "attachments"),
        attachment_max_size_bytes=1024,
    )


def test_transition_start_and_hold_preserve_state_machine_payloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = RecordingLifecycleRepository()
    fixed_now = datetime(2026, 8, 9, 4, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("src.maintenance_management.service._utc_now", lambda: fixed_now)
    service = _service(repository, tmp_path)
    actor = _actor()
    audit_context = _audit(actor)

    started = service.transition_work_order(
        WORK_ORDER_ID,
        target_status="in_progress",
        hold_reason=None,
        expected_version=3,
        actor=actor,
        audit_context=audit_context,
    )
    assert started["status"] == "in_progress"
    assert repository.calls[0]["updates"] == {
        "status": "in_progress",
        "hold_reason": None,
        "started_at": fixed_now,
    }
    assert repository.calls[0]["audit_action"] == "work_order.started"

    repository.status = "in_progress"
    held = service.transition_work_order(
        WORK_ORDER_ID,
        target_status="on_hold",
        hold_reason="  Await safety inspection  ",
        expected_version=4,
        actor=actor,
        audit_context=audit_context,
    )
    assert held["status"] == "on_hold"
    assert repository.calls[1]["updates"] == {
        "status": "on_hold",
        "hold_reason": "Await safety inspection",
    }
    assert repository.calls[1]["audit_action"] == "work_order.put_on_hold"


def test_transition_rejects_specialized_states_and_invalid_edges_without_write(
    tmp_path: Path,
) -> None:
    repository = RecordingLifecycleRepository()
    service = _service(repository, tmp_path)
    actor = _actor()
    audit_context = _audit(actor)

    with pytest.raises(MaintenanceDomainError):
        service.transition_work_order(
            WORK_ORDER_ID,
            target_status="completed",
            hold_reason=None,
            expected_version=3,
            actor=actor,
            audit_context=audit_context,
        )
    repository.status = "planned"
    with pytest.raises(MaintenanceConflictError):
        service.transition_work_order(
            WORK_ORDER_ID,
            target_status="in_progress",
            hold_reason=None,
            expected_version=3,
            actor=actor,
            audit_context=audit_context,
        )
    assert repository.calls == []


def test_checklist_update_normalizes_response_and_requires_execution_state(
    tmp_path: Path,
) -> None:
    repository = RecordingLifecycleRepository(status="in_progress")
    service = _service(repository, tmp_path)
    actor = _actor()
    audit_context = _audit(actor)

    service.update_checklist(
        WORK_ORDER_ID,
        [
            {
                "item_id": CHECKLIST_ID,
                "result_status": "completed",
                "boolean_value": True,
                "numeric_value": None,
                "text_value": None,
                "note": "  Confirmed  ",
            }
        ],
        expected_version=3,
        actor=actor,
        audit_context=audit_context,
    )
    assert len(repository.checklist_calls) == 1
    call = repository.checklist_calls[0]
    assert call["expected_version"] == 3
    assert call["responses"][0]["result_status"] == "completed"
    assert call["responses"][0]["boolean_value"] is True
    assert call["responses"][0]["note"] == "Confirmed"
    assert call["responses"][0]["completed_by_user_id"] == actor.id

    repository.status = "assigned"
    with pytest.raises(MaintenanceConflictError):
        service.update_checklist(
            WORK_ORDER_ID,
            [
                {
                    "item_id": CHECKLIST_ID,
                    "result_status": "completed",
                    "boolean_value": True,
                }
            ],
            expected_version=4,
            actor=actor,
            audit_context=audit_context,
        )
    assert len(repository.checklist_calls) == 1


def test_cancel_and_reopen_preserve_named_actions_and_reason_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = RecordingLifecycleRepository(status="assigned")
    fixed_now = datetime(2026, 8, 9, 4, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("src.maintenance_management.service._utc_now", lambda: fixed_now)
    service = _service(repository, tmp_path)
    actor = _actor()
    audit_context = _audit(actor)

    service.cancel_work_order(
        WORK_ORDER_ID,
        expected_version=3,
        cancellation_reason="  Duplicate request  ",
        audit_context=audit_context,
    )
    assert repository.calls[0]["audit_action"] == "work_order.cancelled"
    assert repository.calls[0]["updates"] == {
        "status": "cancelled",
        "cancelled_at": fixed_now,
        "cancellation_reason": "Duplicate request",
        "hold_reason": None,
    }

    repository.status = "completed"
    service.reopen_work_order(
        WORK_ORDER_ID,
        expected_version=4,
        reason="  Field recheck required  ",
        audit_context=audit_context,
    )
    assert repository.calls[1]["audit_action"] == "work_order.reopened"
    assert repository.calls[1]["updates"] == {
        "status": "in_progress",
        "completed_at": None,
        "hold_reason": None,
    }
    assert repository.calls[1]["audit_metadata"] == {"reason": "Field recheck required"}


def test_work_order_lifecycle_collaborator_boundary_is_storage_neutral() -> None:
    source = Path("src/maintenance_management/application/work_order_lifecycle_service.py")
    assert source.exists()
    contents = source.read_text(encoding="utf-8")
    assert "sqlalchemy" not in contents.lower()
    assert "src.repositories.postgres" not in contents
    assert "src.maintenance_management.service" not in contents
