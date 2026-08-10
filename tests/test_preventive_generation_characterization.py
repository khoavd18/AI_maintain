"""Characterize preventive-generation orchestration before extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from src.asset_management.storage import LocalAttachmentStorage
from src.maintenance_management.errors import MaintenanceDomainError
from src.maintenance_management.service import MaintenancePlanningService
from src.repositories.contracts import StoredPage, StoredRecord
from src.security.audit_context import AuditContext
from src.security.permissions import Role
from tests.auth_helpers import build_test_user


PLAN_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


@dataclass
class RecordingGenerationRepository:
    plan_status: str = "active"
    asset_lifecycle_status: str = "active"

    backend_name = "stub"

    def __post_init__(self) -> None:
        self.generated_dates: set[date] = set()
        self.generated_calls: list[dict[str, Any]] = []

    def get_plan(self, plan_id: UUID) -> StoredRecord:
        today = date.today()
        return StoredRecord(
            {
                "id": str(plan_id),
                "plan_code": "PM-GENERATOR-001",
                "status": self.plan_status,
                "next_due_date": today.isoformat(),
                "lead_time_days": 7,
                "interval_value": 1,
                "interval_unit": "day",
                "start_date": today.isoformat(),
                "end_date": None,
                "local_timezone": "Asia/Ho_Chi_Minh",
                "asset_id": "GENERATOR_001",
            }
        )

    def list_plans(self, *, filters: dict[str, Any], page: int, page_size: int) -> StoredPage:
        del filters, page, page_size
        return StoredPage([self.get_plan(PLAN_ID)], page=1, page_size=1000, total=1)

    def get_asset_state(self, asset_id: str) -> StoredRecord:
        return StoredRecord({"asset_id": asset_id, "lifecycle_status": self.asset_lifecycle_status})

    def list_generated_due_dates(self, plan_id: UUID) -> set[date]:
        del plan_id
        return set(self.generated_dates)

    def generate_plan_occurrences(
        self,
        plan_id: UUID,
        *,
        schedule_signature: dict[str, Any],
        due_dates: list[date],
        next_due_date: date | None,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        new_dates = [value for value in due_dates if value not in self.generated_dates]
        self.generated_calls.append(
            {
                "plan_id": plan_id,
                "schedule_signature": dict(schedule_signature),
                "due_dates": list(due_dates),
                "next_due_date": next_due_date,
                "audit_context": audit_context,
            }
        )
        self.generated_dates.update(due_dates)
        return {
            "plan_id": str(plan_id),
            "plan_code": "PM-GENERATOR-001",
            "generated": [f"WO-{index:06d}" for index, _ in enumerate(new_dates, 1)],
            "skipped_due_dates": [],
            "next_due_date": next_due_date.isoformat() if next_due_date else None,
        }


def _service(
    repository: RecordingGenerationRepository, tmp_path: Path
) -> MaintenancePlanningService:
    return MaintenancePlanningService(
        repository,  # type: ignore[arg-type]
        LocalAttachmentStorage(tmp_path / "attachments"),
        attachment_max_size_bytes=1024,
    )


def test_generation_dry_run_and_execution_preserve_due_dates_and_signature(
    tmp_path: Path,
) -> None:
    repository = RecordingGenerationRepository()
    service = _service(repository, tmp_path)
    actor = build_test_user(Role.CHIEF_ENGINEER)
    audit_context = AuditContext(actor.id, actor.display_name, "generation")
    today = date.today()

    dry_run = service.generate(
        as_of_date=today,
        plan_id=PLAN_ID,
        dry_run=True,
        actor=actor,
        audit_context=audit_context,
    )
    assert dry_run["would_generate_count"] == 8
    assert dry_run["generated_count"] == 0
    assert repository.generated_calls == []

    generated = service.generate(
        as_of_date=today,
        plan_id=PLAN_ID,
        dry_run=False,
        actor=actor,
        audit_context=audit_context,
    )
    assert generated["generated_count"] == 8
    assert len(repository.generated_calls) == 1
    command = repository.generated_calls[0]
    assert command["plan_id"] == PLAN_ID
    assert command["due_dates"] == [today + timedelta(days=i) for i in range(8)]
    assert command["next_due_date"] == today + timedelta(days=8)
    assert command["schedule_signature"] == {
        "interval_value": 1,
        "interval_unit": "day",
        "start_date": today,
        "end_date": None,
        "local_timezone": "Asia/Ho_Chi_Minh",
        "status": "active",
    }

    repeated = service.generate(
        as_of_date=today,
        plan_id=PLAN_ID,
        dry_run=False,
        actor=actor,
        audit_context=audit_context,
    )
    assert repeated["generated_count"] == 0
    assert len(repository.generated_calls) == 2


def test_generation_skips_paused_plans_and_retired_assets_without_writes(
    tmp_path: Path,
) -> None:
    repository = RecordingGenerationRepository(plan_status="paused")
    service = _service(repository, tmp_path)
    actor = build_test_user(Role.CHIEF_ENGINEER)
    audit_context = AuditContext(actor.id, actor.display_name, "generation-skip")

    paused = service.generate(
        as_of_date=date.today(),
        plan_id=PLAN_ID,
        dry_run=False,
        actor=actor,
        audit_context=audit_context,
    )
    assert paused["skipped_count"] == 0
    assert paused["plans"][0]["reason"]
    assert repository.generated_calls == []

    repository.plan_status = "active"
    repository.asset_lifecycle_status = "retired"
    retired = service.generate(
        as_of_date=date.today(),
        plan_id=PLAN_ID,
        dry_run=False,
        actor=actor,
        audit_context=audit_context,
    )
    assert retired["plans"][0]["reason"]
    assert repository.generated_calls == []


def test_generation_enforces_the_documented_366_day_as_of_bound(
    tmp_path: Path,
) -> None:
    repository = RecordingGenerationRepository()
    service = _service(repository, tmp_path)
    actor = build_test_user(Role.CHIEF_ENGINEER)
    audit_context = AuditContext(actor.id, actor.display_name, "generation-bound")

    with pytest.raises(MaintenanceDomainError):
        service.generate(
            as_of_date=date.today() + timedelta(days=367),
            plan_id=PLAN_ID,
            dry_run=True,
            actor=actor,
            audit_context=audit_context,
        )
    assert repository.generated_calls == []


def test_generation_collaborator_boundary_is_storage_neutral() -> None:
    source = Path("src/maintenance_management/application/preventive_generation_service.py")
    assert source.exists()
    contents = source.read_text(encoding="utf-8")
    assert "sqlalchemy" not in contents.lower()
    assert "src.repositories.postgres" not in contents
    assert "src.maintenance_management.service" not in contents
