"""Characterize read-only work-order reporting projections."""

from __future__ import annotations

from datetime import date, timedelta
from inspect import Parameter, signature
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from src.maintenance_management.application.work_order_reporting_service import (
    WorkOrderReportingService,
)
from src.maintenance_management.errors import MaintenanceDomainError
from src.maintenance_management.recurrence import MAX_OCCURRENCES
from src.maintenance_management.service import MaintenancePlanningService
from src.repositories.contracts import StoredPage, StoredRecord
from src.security.permissions import Role
from tests.auth_helpers import build_test_user


PLAN_A_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
PLAN_B_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
ASSIGNEE_ID = UUID("33333333-3333-4333-8333-333333333333")


class RecordingReportingRepository:
    backend_name = "stub"

    def __init__(self, records: list[StoredRecord] | None = None) -> None:
        self.records = records or []
        self.list_calls: list[dict[str, Any]] = []

    def list_work_orders(self, *, filters: dict[str, Any], page: int, page_size: int) -> StoredPage:
        self.list_calls.append({"filters": dict(filters), "page": page, "page_size": page_size})
        return StoredPage(
            items=self.records,
            page=page,
            page_size=page_size,
            total=len(self.records),
        )


class RecordingScheduleReads:
    def __init__(self) -> None:
        self.work_order_calls: list[dict[str, Any]] = []
        self.plan_calls: list[dict[str, Any]] = []
        self.preview_calls: list[dict[str, Any]] = []

    def list_work_orders(self, **kwargs: Any) -> dict[str, Any]:
        self.work_order_calls.append(kwargs)
        return {"items": [{"id": "work-order-a"}]}

    def list_plans(self, **kwargs: Any) -> dict[str, Any]:
        self.plan_calls.append(kwargs)
        return {
            "items": [
                {
                    "id": str(PLAN_B_ID),
                    "plan_code": "PM-B",
                    "name": "Plan B",
                    "asset_id": "GENERATOR_002",
                },
                {
                    "id": str(PLAN_A_ID),
                    "plan_code": "PM-A",
                    "name": "Plan A",
                    "asset_id": "GENERATOR_001",
                },
            ]
        }

    def preview_occurrences(self, plan_id: UUID, **kwargs: Any) -> dict[str, Any]:
        self.preview_calls.append({"plan_id": plan_id, **kwargs})
        due_date = "2027-01-01" if plan_id == PLAN_B_ID else "2026-06-01"
        return {
            "items": [
                {
                    "due_date": due_date,
                    "generated": plan_id == PLAN_A_ID,
                    "generation_release_date": due_date,
                }
            ]
        }


def _reporting_service(
    repository: RecordingReportingRepository,
    reads: RecordingScheduleReads | None = None,
) -> WorkOrderReportingService:
    schedule_reads = reads or RecordingScheduleReads()
    return WorkOrderReportingService(
        lambda: repository,  # type: ignore[return-value]
        list_work_orders=schedule_reads.list_work_orders,
        list_plans=schedule_reads.list_plans,
        preview_occurrences=schedule_reads.preview_occurrences,
    )


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [
        (date(2026, 8, 2), date(2026, 8, 1)),
        (date(2026, 1, 1), date(2027, 1, 3)),
    ],
)
def test_invalid_calendar_range_rejects_before_any_read(date_from: date, date_to: date) -> None:
    repository = RecordingReportingRepository()
    reads = RecordingScheduleReads()
    service = _reporting_service(repository, reads)

    with pytest.raises(MaintenanceDomainError, match="0–366"):
        service.schedule_view(
            actor=build_test_user(Role.CHIEF_ENGINEER),
            date_from=date_from,
            date_to=date_to,
            asset_id=None,
            assigned_to_user_id=None,
        )

    assert reads.work_order_calls == []
    assert reads.plan_calls == []
    assert reads.preview_calls == []
    assert repository.list_calls == []


def test_schedule_view_preserves_bounds_filters_and_plan_occurrence_order() -> None:
    repository = RecordingReportingRepository()
    reads = RecordingScheduleReads()
    service = _reporting_service(repository, reads)
    actor = build_test_user(Role.TECHNICIAN, technician_id="TECH-001")
    date_from = date(2026, 1, 1)
    date_to = date_from + timedelta(days=366)

    result = service.schedule_view(
        actor=actor,
        date_from=date_from,
        date_to=date_to,
        asset_id="GENERATOR_002",
        assigned_to_user_id=ASSIGNEE_ID,
    )

    assert reads.work_order_calls == [
        {
            "actor": actor,
            "filters": {
                "asset_id": "GENERATOR_002",
                "assigned_to_user_id": ASSIGNEE_ID,
                "due_from": date_from,
                "due_to": date_to,
            },
            "page": 1,
            "page_size": 1000,
        }
    ]
    assert reads.plan_calls == [
        {
            "asset_id": "GENERATOR_002",
            "status": "active",
            "search": None,
            "due_from": None,
            "due_to": None,
            "page": 1,
            "page_size": 1000,
        }
    ]
    assert reads.preview_calls == [
        {
            "plan_id": PLAN_B_ID,
            "date_from": date_from,
            "date_to": date_to,
            "limit": MAX_OCCURRENCES,
        },
        {
            "plan_id": PLAN_A_ID,
            "date_from": date_from,
            "date_to": date_to,
            "limit": MAX_OCCURRENCES,
        },
    ]
    assert result == {
        "date_from": "2026-01-01",
        "date_to": "2027-01-02",
        "work_orders": [{"id": "work-order-a"}],
        "upcoming_occurrences": [
            {
                "due_date": "2027-01-01",
                "generated": False,
                "generation_release_date": "2027-01-01",
                "plan_id": str(PLAN_B_ID),
                "plan_code": "PM-B",
                "plan_name": "Plan B",
                "asset_id": "GENERATOR_002",
            },
            {
                "due_date": "2026-06-01",
                "generated": True,
                "generation_release_date": "2026-06-01",
                "plan_id": str(PLAN_A_ID),
                "plan_code": "PM-A",
                "plan_name": "Plan A",
                "asset_id": "GENERATOR_001",
            },
        ],
    }


def test_metrics_preserve_status_date_window_and_workload_semantics() -> None:
    repository = RecordingReportingRepository(
        [
            _work_order("planned", due_date="2026-08-09"),
            _work_order(
                "assigned",
                work_order_type="preventive",
                due_date="2026-08-10",
                assignee_id="tech-b",
                assignee_name="Beta",
            ),
            _work_order(
                "in_progress",
                work_order_type="preventive",
                due_date="2026-09-09",
                assignee_id="tech-a",
                assignee_name="Alpha",
            ),
            _work_order(
                "on_hold",
                work_order_type="preventive",
                due_date="2026-08-08",
                grace_period_days=2,
                assignee_id="tech-a",
                assignee_name="Alpha",
            ),
            _work_order(
                "completed",
                due_date="2026-08-05",
                grace_period_days=1,
                completed_at="2026-08-06T23:59:00+00:00",
                assignee_id="tech-c",
                assignee_name="Charlie",
            ),
            _work_order(
                "verified",
                due_date="2026-08-01",
                completed_at="2026-08-03T00:00:00+00:00",
                assignee_id="tech-d",
                assignee_name="Delta",
            ),
            _work_order(
                "cancelled",
                work_order_type="preventive",
                due_date="2026-08-11",
                assignee_id="tech-e",
                assignee_name="Echo",
            ),
        ]
    )

    result = _reporting_service(repository).metrics(as_of_date=date(2026, 8, 10))

    assert repository.list_calls == [{"filters": {}, "page": 1, "page_size": 1000}]
    assert result == {
        "as_of_date": "2026-08-10",
        "total_work_orders": 7,
        "by_status": {
            "planned": 1,
            "assigned": 1,
            "in_progress": 1,
            "on_hold": 1,
            "completed": 1,
            "verified": 1,
            "cancelled": 1,
        },
        "overdue_count": 2,
        "upcoming_preventive_count": 2,
        "completed_count": 2,
        "verified_count": 1,
        "completed_on_time_count": 1,
        "technician_workload": [
            {"user_id": "tech-a", "display_name": "Alpha", "open_count": 2},
            {"user_id": "tech-b", "display_name": "Beta", "open_count": 1},
            {"user_id": "tech-c", "display_name": "Charlie", "open_count": 1},
        ],
        "data_notice": "Chỉ số vận hành trên dữ liệu synthetic/internal-pilot.",
    }


def test_empty_metrics_keep_all_status_buckets() -> None:
    result = _reporting_service(RecordingReportingRepository()).metrics(
        as_of_date=date(2026, 8, 10)
    )

    assert result["by_status"] == {
        "planned": 0,
        "assigned": 0,
        "in_progress": 0,
        "on_hold": 0,
        "completed": 0,
        "verified": 0,
        "cancelled": 0,
    }


def test_reporting_collaborator_is_storage_neutral_and_facade_keeps_signatures() -> None:
    root = Path(__file__).parents[1]
    collaborator = (
        root / "src" / "maintenance_management" / "application" / "work_order_reporting_service.py"
    ).read_text(encoding="utf-8")
    facade = (root / "src" / "maintenance_management" / "service.py").read_text(encoding="utf-8")

    lowered = collaborator.lower()
    assert "sqlalchemy" not in lowered
    assert "fastapi" not in lowered
    assert "src.repositories.postgres" not in collaborator
    assert "src.maintenance_management.service" not in collaborator
    assert "self.reporting = WorkOrderReportingService(" in facade
    assert "return self.reporting.schedule_view(" in facade
    assert "return self.reporting.metrics(" in facade

    schedule_parameters = signature(MaintenancePlanningService.schedule_view).parameters
    assert list(schedule_parameters) == [
        "self",
        "actor",
        "date_from",
        "date_to",
        "asset_id",
        "assigned_to_user_id",
    ]
    assert all(
        parameter.kind is Parameter.KEYWORD_ONLY
        for name, parameter in schedule_parameters.items()
        if name != "self"
    )
    metrics_parameters = signature(MaintenancePlanningService.metrics).parameters
    assert list(metrics_parameters) == ["self", "as_of_date"]
    assert metrics_parameters["as_of_date"].kind is Parameter.KEYWORD_ONLY


def _work_order(
    status: str,
    *,
    work_order_type: str = "inspection",
    due_date: str,
    grace_period_days: int = 0,
    completed_at: str | None = None,
    assignee_id: str | None = None,
    assignee_name: str | None = None,
) -> StoredRecord:
    return StoredRecord(
        {
            "status": status,
            "work_order_type": work_order_type,
            "due_date": due_date,
            "grace_period_days": grace_period_days,
            "completed_at": completed_at,
            "assigned_to_user_id": assignee_id,
            "assigned_to_name": assignee_name,
        }
    )
