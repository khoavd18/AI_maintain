"""Deterministic, streaming Stage 10 multi-domain scale-data generator."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import logging
from pathlib import Path
import time
from typing import Any, Iterable, Iterator

from data_platform.generator import _uuid, _work_order_row
from data_platform.object_store import checksum


LOGGER = logging.getLogger("data_platform.domain_generator")
UTC = timezone.utc
SCHEMA_VERSION = "stage10-domain-scale-v1"
DEFAULT_RUN_ID = "stage10-domain-seed-20260824"
DEFAULT_SEED = 20260824
WORK_ORDER_COUNT = 1_100_000
STATUS_HISTORY_COUNT = 3_300_000
TICKET_COUNT = 300_000
TICKET_EVENT_COUNT = 900_000
SPARE_PART_COUNT = 25_000
INVENTORY_MOVEMENT_COUNT = 1_500_000
COST_FACT_COUNT = 1_100_000
LATE_STATUS_COUNT = 33_000
LATE_TICKET_EVENT_COUNT = 9_000
BASELINE_COST_COUNT = 1_089_000
PART_UPDATE_COUNT = 250
TICKET_UPDATE_COUNT = 3_000
STAGE9_SEED = 20260823
BASELINE_AVAILABLE_AT = datetime(2026, 8, 24, 8, 0, tzinfo=UTC)
INCREMENTAL_AVAILABLE_AT = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)

STATUS_COLUMNS = [
    "event_id",
    "work_order_id",
    "sequence_number",
    "status",
    "transitioned_at",
    "source_available_at",
    "is_late_arriving",
    "created_at",
]
CALENDAR_COLUMNS = [
    "id",
    "code",
    "name",
    "timezone",
    "is_active",
    "created_by_user_id",
    "updated_by_user_id",
    "created_at",
    "updated_at",
    "version",
]
SLA_POLICY_COLUMNS = [
    "id",
    "code",
    "name",
    "calendar_id",
    "category_id",
    "timezone",
    "pause_on_waiting",
    "due_soon_percent",
    "effective_from",
    "effective_to",
    "is_active",
    "created_by_user_id",
    "updated_by_user_id",
    "created_at",
    "updated_at",
    "version",
]
SLA_TARGET_COLUMNS = [
    "id",
    "policy_id",
    "priority",
    "first_response_minutes",
    "resolution_minutes",
]
TICKET_COLUMNS = [
    "ticket_id",
    "asset_id",
    "issue_description",
    "priority",
    "status",
    "failure_category",
    "created_at",
    "resolved_at",
    "technician_id",
    "manager_note",
    "note",
    "version",
    "updated_at",
    "reporter_name",
    "reporter_email",
    "reporter_phone",
    "category_id",
    "subcategory_id",
    "impact",
    "urgency",
    "intake_source_id",
    "support_group_id",
    "assigned_user_id",
    "first_response_at",
    "waiting_reason",
    "waiting_previous_status",
    "closed_at",
    "reopened_at",
    "cancelled_at",
    "cancellation_reason",
    "reopen_count",
]
TICKET_SLA_STATE_COLUMNS = [
    "id",
    "ticket_id",
    "policy_id",
    "policy_code",
    "policy_name",
    "calendar_id",
    "calendar_code",
    "timezone",
    "calendar_snapshot",
    "pause_on_waiting",
    "due_soon_percent",
    "first_response_target_minutes",
    "resolution_target_minutes",
    "started_at",
    "first_response_due_at",
    "resolution_due_at",
    "first_response_remaining_minutes",
    "resolution_remaining_minutes",
    "paused_at",
    "resolution_stopped_at",
    "occurrence_number",
    "created_at",
    "updated_at",
    "version",
]
TICKET_SLA_EVENT_COLUMNS = [
    "id",
    "ticket_sla_id",
    "ticket_id",
    "event_type",
    "clock_type",
    "occurrence_number",
    "occurred_at",
    "details",
    "created_by_user_id",
    "created_at",
]
TICKET_ESCALATION_EVENT_COLUMNS = [
    "id",
    "ticket_id",
    "ticket_sla_id",
    "rule_code",
    "clock_type",
    "occurrence_number",
    "detected_at",
    "due_at",
    "details",
    "created_by_user_id",
    "created_at",
]
TICKET_LINK_COLUMNS = ["ticket_id", "work_order_id", "linked_at", "source_system"]
PART_CATEGORY_COLUMNS = [
    "id",
    "code",
    "name_vi",
    "name_en",
    "description",
    "is_active",
    "created_by_user_id",
    "updated_by_user_id",
    "created_at",
    "updated_at",
    "version",
]
UNIT_COLUMNS = [
    "id",
    "code",
    "name_vi",
    "name_en",
    "symbol",
    "quantity_precision",
    "is_active",
    "created_by_user_id",
    "updated_by_user_id",
    "created_at",
    "updated_at",
    "version",
]
STOCK_LOCATION_COLUMNS = [
    "id",
    "code",
    "name",
    "location_type",
    "description",
    "lifecycle_status",
    "lifecycle_status_before_archive",
    "archived_at",
    "archive_reason",
    "created_by_user_id",
    "updated_by_user_id",
    "created_at",
    "updated_at",
    "version",
]
SPARE_PART_COLUMNS = [
    "id",
    "part_number",
    "name_vi",
    "name_en",
    "category_id",
    "unit_of_measure_id",
    "manufacturer_reference",
    "compatible_asset_types",
    "lifecycle_status",
    "lifecycle_status_before_archive",
    "minimum_stock",
    "reorder_point",
    "maximum_stock",
    "unit_cost",
    "currency_code",
    "archived_at",
    "archive_reason",
    "created_by_user_id",
    "updated_by_user_id",
    "created_at",
    "updated_at",
    "version",
]
INVENTORY_MOVEMENT_COLUMNS = [
    "id",
    "movement_number",
    "operation_id",
    "part_id",
    "stock_location_id",
    "quantity",
    "unit_of_measure_id",
    "movement_type",
    "business_reference",
    "actor_user_id",
    "occurred_at",
    "reason",
    "work_order_id",
    "source_location_id",
    "destination_location_id",
    "transfer_group_id",
    "unit_cost_snapshot",
    "resulting_on_hand_quantity",
    "resulting_reserved_quantity",
    "idempotency_key",
    "created_at",
]
COST_COLUMNS = [
    "work_order_id",
    "estimated_labor_cost",
    "actual_labor_cost",
    "planned_part_cost",
    "actual_part_cost",
    "external_service_cost",
    "total_estimated_cost",
    "total_actual_cost",
    "cost_variance",
    "currency_code",
    "source_updated_at",
    "created_at",
]

_PRIORITY_TARGETS = {
    "low": (240, 2_880),
    "medium": (120, 1_440),
    "high": (60, 480),
    "critical": (15, 120),
}
_FAILURE_CATEGORIES = (
    "cooling_issue",
    "vibration_issue",
    "electrical_issue",
    "pressure_issue",
    "runtime_issue",
    "sensor_issue",
)


def _iso(value: datetime | None) -> str:
    return "" if value is None else value.astimezone(UTC).isoformat()


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _write_csv(
    path: Path,
    columns: list[str],
    rows: Iterable[dict[str, object]],
) -> tuple[int, dict[str, object]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    count = 0
    with partial.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    partial.replace(path)
    return count, {
        "name": path.name,
        "path": path.as_posix(),
        "row_count": count,
        "size_bytes": path.stat().st_size,
        "sha256": checksum(path),
    }


def _stage9_work_order(index: int) -> dict[str, object]:
    return _work_order_row(
        index,
        seed=STAGE9_SEED,
        asset_count=20_000,
        technician_count=500,
        baseline_count=1_000_000,
    )


def _status_path(index: int, expanded_completed: set[int]) -> tuple[str, ...]:
    status = str(_stage9_work_order(index)["status"])
    if status == "planned":
        return ("planned",)
    if status == "assigned":
        return ("planned", "assigned")
    if status == "in_progress":
        return ("planned", "assigned", "in_progress")
    if status == "on_hold":
        return ("planned", "assigned", "in_progress", "on_hold")
    if status == "completed":
        if index in expanded_completed:
            return ("planned", "assigned", "in_progress", "completed")
        return ("planned", "assigned", "completed")
    if status == "verified":
        return ("planned", "assigned", "completed", "verified")
    return ("planned", "cancelled")


def _status_fixture_sets() -> tuple[set[int], set[int]]:
    expanded_indices: set[int] = set()
    expanded_completed = 0
    late_indices: set[int] = set()
    total = 0
    for index in range(1, WORK_ORDER_COUNT + 1):
        if (
            str(_stage9_work_order(index)["status"]) == "completed"
            and expanded_completed < 299_096
        ):
            expanded_indices.add(index)
            expanded_completed += 1
        path = _status_path(index, expanded_indices)
        total += len(path)
        if len(path) >= 3 and len(late_indices) < LATE_STATUS_COUNT:
            late_indices.add(index)
    if total != STATUS_HISTORY_COUNT or expanded_completed != 299_096:
        raise RuntimeError(
            f"Stage 9 status distribution changed: rows={total}, expanded={expanded_completed}."
        )
    if len(late_indices) != LATE_STATUS_COUNT:
        raise RuntimeError("Could not select the exact late-arriving status fixture count.")
    return expanded_indices, late_indices


def _transition_time(row: dict[str, object], status: str, sequence: int) -> datetime:
    created = datetime.fromisoformat(str(row["created_at"]))
    if status == "planned":
        return created
    if status == "assigned":
        return created + timedelta(minutes=10)
    if status == "in_progress":
        value = str(row["started_at"])
        return datetime.fromisoformat(value) if value else created + timedelta(hours=2)
    if status == "on_hold":
        started = datetime.fromisoformat(str(row["started_at"]))
        return started + timedelta(minutes=30)
    if status == "completed":
        value = str(row["completed_at"])
        return datetime.fromisoformat(value) if value else created + timedelta(hours=4)
    if status == "verified":
        return datetime.fromisoformat(str(row["verified_at"]))
    if status == "cancelled":
        return datetime.fromisoformat(str(row["cancelled_at"]))
    raise RuntimeError(f"Unsupported status at sequence {sequence}: {status}")


def _iter_status_rows(
    expanded_completed: set[int],
    late_indices: set[int],
    *,
    phase: str,
    start: int,
    end: int,
) -> Iterator[dict[str, object]]:
    for index in range(start, end + 1):
        row = _stage9_work_order(index)
        for sequence, status in enumerate(_status_path(index, expanded_completed), start=1):
            is_late = index in late_indices and sequence == 2
            if (phase == "incremental") != is_late:
                continue
            available = INCREMENTAL_AVAILABLE_AT if is_late else BASELINE_AVAILABLE_AT
            event_index = (index - 1) * 4 + sequence
            yield {
                "event_id": _uuid(10, event_index),
                "work_order_id": row["id"],
                "sequence_number": sequence,
                "status": status,
                "transitioned_at": _iso(_transition_time(row, status, sequence)),
                "source_available_at": _iso(available + timedelta(microseconds=event_index)),
                "is_late_arriving": str(is_late).lower(),
                "created_at": _iso(available + timedelta(microseconds=event_index)),
            }


def _ticket_priority(index: int) -> tuple[str, str, str]:
    choice = index % 4
    if choice == 0:
        return "critical", "critical", "immediate"
    if choice == 1:
        return "low", "low", "low"
    if choice == 2:
        return "medium", "medium", "medium"
    return "high", "high", "high"


def _ticket_values(index: int, *, update: bool = False) -> dict[str, object]:
    work_order = _stage9_work_order(index)
    opened = datetime.fromisoformat(str(work_order["created_at"])) - timedelta(hours=2)
    priority, impact, urgency = _ticket_priority(index)
    status_mod = index % 10
    if status_mod == 0:
        status = "open"
    elif status_mod == 1:
        status = "assigned"
    elif status_mod == 2:
        status = "in_progress"
    elif status_mod == 9:
        status = "closed"
    else:
        status = "resolved"
    first_response = opened + timedelta(minutes=5 + index % 55)
    resolved = opened + timedelta(hours=2 + index % 72) if status in {"resolved", "closed"} else None
    closed = resolved + timedelta(hours=1 + index % 12) if status == "closed" else None
    resolution = (
        "Synthetic resolution evidence recorded after bounded maintenance review."
        if resolved
        else ""
    )
    note = "Synthetic technician note; contains no personal or production information."
    if update:
        note += " Late-arriving review metadata was applied deterministically."
    available = INCREMENTAL_AVAILABLE_AT if update else BASELINE_AVAILABLE_AT
    return {
        "ticket_id": f"S10-TICKET-{index:06d}",
        "asset_id": work_order["asset_id"],
        "issue_description": "Synthetic equipment condition requires bounded technician review.",
        "priority": priority,
        "status": status,
        "failure_category": _FAILURE_CATEGORIES[index % len(_FAILURE_CATEGORIES)],
        "created_at": _iso(opened),
        "resolved_at": _iso(resolved),
        "technician_id": f"S9-TECH-{((index - 1) % 500) + 1:06d}",
        "manager_note": resolution,
        "note": note,
        "version": 2 if update else 1,
        "updated_at": _iso(available + timedelta(microseconds=index)),
        "reporter_name": "",
        "reporter_email": "",
        "reporter_phone": "",
        "category_id": "",
        "subcategory_id": "",
        "impact": impact,
        "urgency": urgency,
        "intake_source_id": "",
        "support_group_id": "",
        "assigned_user_id": _uuid(1, ((index - 1) % 500) + 1),
        "first_response_at": _iso(first_response),
        "waiting_reason": "",
        "waiting_previous_status": "",
        "closed_at": _iso(closed),
        "reopened_at": "",
        "cancelled_at": "",
        "cancellation_reason": "",
        "reopen_count": 0,
    }


def _iter_tickets(*, update: bool = False) -> Iterator[dict[str, object]]:
    end = TICKET_UPDATE_COUNT if update else TICKET_COUNT
    for index in range(1, end + 1):
        yield _ticket_values(index, update=update)


def _iter_ticket_links() -> Iterator[dict[str, object]]:
    for index in range(1, TICKET_COUNT + 1):
        yield {
            "ticket_id": f"S10-TICKET-{index:06d}",
            "work_order_id": _uuid(5, index),
            "linked_at": _ticket_values(index)["created_at"],
            "source_system": "stage10_synthetic",
        }


def _calendar_snapshot() -> str:
    return json.dumps(
        {
            "code": "S10_24X7",
            "timezone": "Asia/Ho_Chi_Minh",
            "working_periods": [
                {"weekday": day, "start": "00:00", "end": "23:59"}
                for day in range(7)
            ],
            "holidays": [],
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _iter_ticket_sla_states() -> Iterator[dict[str, object]]:
    snapshot = _calendar_snapshot()
    for index in range(1, TICKET_COUNT + 1):
        ticket = _ticket_values(index)
        opened = datetime.fromisoformat(str(ticket["created_at"]))
        priority = str(ticket["priority"])
        response_minutes, resolution_minutes = _PRIORITY_TARGETS[priority]
        resolved = datetime.fromisoformat(str(ticket["resolved_at"])) if ticket["resolved_at"] else None
        yield {
            "id": _uuid(12, index),
            "ticket_id": ticket["ticket_id"],
            "policy_id": _uuid(13, 1),
            "policy_code": "S10_SYNTHETIC_SLA",
            "policy_name": "Stage 10 synthetic SLA policy",
            "calendar_id": _uuid(14, 1),
            "calendar_code": "S10_24X7",
            "timezone": "Asia/Ho_Chi_Minh",
            "calendar_snapshot": snapshot,
            "pause_on_waiting": "true",
            "due_soon_percent": 20,
            "first_response_target_minutes": response_minutes,
            "resolution_target_minutes": resolution_minutes,
            "started_at": _iso(opened),
            "first_response_due_at": _iso(opened + timedelta(minutes=response_minutes)),
            "resolution_due_at": _iso(opened + timedelta(minutes=resolution_minutes)),
            "first_response_remaining_minutes": "",
            "resolution_remaining_minutes": "",
            "paused_at": "",
            "resolution_stopped_at": _iso(resolved),
            "occurrence_number": 1,
            "created_at": _iso(BASELINE_AVAILABLE_AT + timedelta(microseconds=index)),
            "updated_at": _iso(BASELINE_AVAILABLE_AT + timedelta(microseconds=index)),
            "version": 1,
        }


def _third_ticket_event(index: int, *, available: datetime) -> tuple[str, dict[str, object]]:
    ticket = _ticket_values(index)
    occurred = datetime.fromisoformat(str(ticket["first_response_at"]))
    common = {
        "ticket_id": ticket["ticket_id"],
        "ticket_sla_id": _uuid(12, index),
        "occurrence_number": 1,
        "created_by_user_id": _uuid(1, ((index - 1) % 500) + 1),
        "created_at": _iso(available + timedelta(microseconds=index)),
    }
    if index % 4 == 0 and index <= 240_000:
        return "ticket_escalation_events", {
            "id": _uuid(17, index),
            **common,
            "rule_code": "critical_priority",
            "clock_type": "resolution",
            "detected_at": _iso(occurred),
            "due_at": _iso(occurred + timedelta(minutes=120)),
            "details": json.dumps({"synthetic": True, "severity": "critical"}),
        }
    return "ticket_sla_events", {
        "id": _uuid(16, TICKET_COUNT * 2 + index),
        "ticket_sla_id": common["ticket_sla_id"],
        "ticket_id": common["ticket_id"],
        "event_type": "first_response_recorded",
        "clock_type": "first_response",
        "occurrence_number": 1,
        "occurred_at": _iso(occurred),
        "details": json.dumps({"synthetic": True, "within_target": True}),
        "created_by_user_id": common["created_by_user_id"],
        "created_at": common["created_at"],
    }


def _iter_ticket_sla_events(*, phase: str, third_kind: str | None = None) -> Iterator[dict[str, object]]:
    for index in range(1, TICKET_COUNT + 1):
        if phase == "baseline" and third_kind is None:
            ticket = _ticket_values(index)
            opened = str(ticket["created_at"])
            available = BASELINE_AVAILABLE_AT + timedelta(microseconds=index)
            for offset, (event_type, clock) in enumerate(
                (("policy_applied", ""), ("clock_started", "resolution")),
                start=1,
            ):
                yield {
                    "id": _uuid(16, (index - 1) * 2 + offset),
                    "ticket_sla_id": _uuid(12, index),
                    "ticket_id": ticket["ticket_id"],
                    "event_type": event_type,
                    "clock_type": clock,
                    "occurrence_number": 1,
                    "occurred_at": opened,
                    "details": json.dumps({"synthetic": True}),
                    "created_by_user_id": _uuid(1, ((index - 1) % 500) + 1),
                    "created_at": _iso(available),
                }
        is_late = index <= LATE_TICKET_EVENT_COUNT
        if (phase == "incremental") != is_late:
            continue
        available = INCREMENTAL_AVAILABLE_AT if is_late else BASELINE_AVAILABLE_AT
        kind, row = _third_ticket_event(index, available=available)
        if kind == (third_kind or "ticket_sla_events"):
            yield row


def _iter_ticket_escalations(*, phase: str) -> Iterator[dict[str, object]]:
    yield from _iter_ticket_sla_events(
        phase=phase,
        third_kind="ticket_escalation_events",
    )


def _support_rows(entity: str) -> Iterable[dict[str, object]]:
    actor = _uuid(1, 1)
    created = _iso(datetime(2022, 1, 1, tzinfo=UTC))
    if entity == "business_calendars":
        return [
            {
                "id": _uuid(14, 1),
                "code": "S10_24X7",
                "name": "Stage 10 synthetic 24x7 calendar",
                "timezone": "Asia/Ho_Chi_Minh",
                "is_active": "true",
                "created_by_user_id": actor,
                "updated_by_user_id": actor,
                "created_at": created,
                "updated_at": created,
                "version": 1,
            }
        ]
    if entity == "sla_policies":
        return [
            {
                "id": _uuid(13, 1),
                "code": "S10_SYNTHETIC_SLA",
                "name": "Stage 10 synthetic SLA policy",
                "calendar_id": _uuid(14, 1),
                "category_id": "",
                "timezone": "Asia/Ho_Chi_Minh",
                "pause_on_waiting": "true",
                "due_soon_percent": 20,
                "effective_from": "2022-01-01",
                "effective_to": "",
                "is_active": "true",
                "created_by_user_id": actor,
                "updated_by_user_id": actor,
                "created_at": created,
                "updated_at": created,
                "version": 1,
            }
        ]
    if entity == "sla_policy_targets":
        return [
            {
                "id": _uuid(15, index),
                "policy_id": _uuid(13, 1),
                "priority": priority,
                "first_response_minutes": target[0],
                "resolution_minutes": target[1],
            }
            for index, (priority, target) in enumerate(_PRIORITY_TARGETS.items(), start=1)
        ]
    if entity == "part_categories":
        return [
            {
                "id": _uuid(20, index),
                "code": f"S10_CAT_{index:02d}",
                "name_vi": f"Nhóm phụ tùng tổng hợp {index:02d}",
                "name_en": f"Synthetic part category {index:02d}",
                "description": "Synthetic benchmark category; no supplier data.",
                "is_active": "true",
                "created_by_user_id": actor,
                "updated_by_user_id": actor,
                "created_at": created,
                "updated_at": created,
                "version": 1,
            }
            for index in range(1, 11)
        ]
    if entity == "units_of_measure":
        return [
            {
                "id": _uuid(21, 1),
                "code": "EA",
                "name_vi": "Cái",
                "name_en": "Each",
                "symbol": "ea",
                "quantity_precision": 0,
                "is_active": "true",
                "created_by_user_id": actor,
                "updated_by_user_id": actor,
                "created_at": created,
                "updated_at": created,
                "version": 1,
            }
        ]
    if entity == "stock_locations":
        return [
            {
                "id": _uuid(22, index),
                "code": f"S10_STORE_{index:04d}",
                "name": f"Synthetic maintenance store {index:04d}",
                "location_type": "maintenance_room",
                "description": "Synthetic isolated Stage 10 stock location.",
                "lifecycle_status": "active",
                "lifecycle_status_before_archive": "",
                "archived_at": "",
                "archive_reason": "",
                "created_by_user_id": actor,
                "updated_by_user_id": actor,
                "created_at": created,
                "updated_at": created,
                "version": 1,
            }
            for index in range(1, 201)
        ]
    raise ValueError(f"Unknown support entity: {entity}")


def _part_values(index: int, *, update: bool = False) -> dict[str, object]:
    updated = INCREMENTAL_AVAILABLE_AT if update else BASELINE_AVAILABLE_AT
    cost = Decimal(10 + index % 500) + (Decimal("0.50") if update else Decimal("0"))
    return {
        "id": _uuid(23, index),
        "part_number": f"S10-PART-{index:06d}",
        "name_vi": f"Phụ tùng tổng hợp {index:06d}",
        "name_en": f"Synthetic spare part {index:06d}",
        "category_id": _uuid(20, ((index - 1) % 10) + 1),
        "unit_of_measure_id": _uuid(21, 1),
        "manufacturer_reference": f"S10-MREF-{index:06d}",
        "compatible_asset_types": json.dumps([("hvac", "pump", "generator")[index % 3]]),
        "lifecycle_status": "active",
        "lifecycle_status_before_archive": "",
        "minimum_stock": 10,
        "reorder_point": 25,
        "maximum_stock": 250,
        "unit_cost": _money(cost),
        "currency_code": "VND",
        "archived_at": "",
        "archive_reason": "",
        "created_by_user_id": _uuid(1, 1),
        "updated_by_user_id": _uuid(1, 1),
        "created_at": _iso(datetime(2022, 1, 1, tzinfo=UTC)),
        "updated_at": _iso(updated + timedelta(microseconds=index)),
        "version": 2 if update else 1,
    }


def _iter_parts(*, update: bool = False) -> Iterator[dict[str, object]]:
    end = PART_UPDATE_COUNT if update else SPARE_PART_COUNT
    for index in range(1, end + 1):
        yield _part_values(index, update=update)


def _movement_type(sequence: int) -> tuple[str, int]:
    if sequence == 1:
        return "opening_balance", 100
    cycle = sequence % 5
    if cycle == 0:
        return "receipt", 10
    if cycle == 1:
        return "issue", 3
    if cycle == 2:
        return "return", 2
    if cycle == 3:
        return "adjustment_increase", 1
    return "issue", 4


def _resulting_stock(sequence: int) -> int:
    stock = 0
    for current in range(1, sequence + 1):
        movement_type, quantity = _movement_type(current)
        if movement_type in {"issue", "adjustment_decrease", "damaged_scrapped"}:
            stock -= quantity
        else:
            stock += quantity
        if stock < 0:
            raise RuntimeError("Synthetic movement would create negative stock.")
    return stock


def _iter_movements(*, phase: str, start_part: int, end_part: int) -> Iterator[dict[str, object]]:
    sequences = range(1, 60) if phase == "baseline" else range(60, 61)
    for part_index in range(start_part, end_part + 1):
        location_index = ((part_index - 1) % 200) + 1
        unit_cost = Decimal(10 + part_index % 500)
        for sequence in sequences:
            global_index = (part_index - 1) * 60 + sequence
            movement_type, quantity = _movement_type(sequence)
            linked = movement_type in {"issue", "return"}
            work_order_index = ((global_index - 1) % WORK_ORDER_COUNT) + 1
            occurred = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(
                days=part_index % 365,
                minutes=sequence * 10,
            )
            available = (
                BASELINE_AVAILABLE_AT if phase == "baseline" else INCREMENTAL_AVAILABLE_AT
            ) + timedelta(microseconds=global_index)
            yield {
                "id": _uuid(30, global_index),
                "movement_number": f"S10-MOVE-{global_index:09d}",
                "operation_id": _uuid(31, global_index),
                "part_id": _uuid(23, part_index),
                "stock_location_id": _uuid(22, location_index),
                "quantity": quantity,
                "unit_of_measure_id": _uuid(21, 1),
                "movement_type": movement_type,
                "business_reference": "STAGE10_SYNTHETIC_SCALE",
                "actor_user_id": _uuid(1, ((part_index - 1) % 500) + 1),
                "occurred_at": _iso(occurred),
                "reason": "Synthetic benchmark inventory evidence.",
                "work_order_id": _uuid(5, work_order_index) if linked else "",
                "source_location_id": "",
                "destination_location_id": "",
                "transfer_group_id": "",
                "unit_cost_snapshot": _money(unit_cost),
                "resulting_on_hand_quantity": _resulting_stock(sequence),
                "resulting_reserved_quantity": 0,
                "idempotency_key": f"stage10-movement-{global_index:09d}",
                "created_at": _iso(available),
            }


def _cost_values(index: int) -> dict[str, object]:
    estimated_labor = Decimal(50) + Decimal(index % 200) * Decimal("1.25")
    actual_labor = estimated_labor + Decimal((index % 21) - 10) * Decimal("0.50")
    planned_part = Decimal(index % 100) * Decimal("2.50")
    actual_part = max(Decimal(0), planned_part + Decimal((index % 11) - 5))
    external = Decimal(100 + index % 400) if index % 20 == 0 else Decimal(0)
    total_estimated = estimated_labor + planned_part
    total_actual = actual_labor + actual_part + external
    source_time = BASELINE_AVAILABLE_AT if index <= BASELINE_COST_COUNT else INCREMENTAL_AVAILABLE_AT
    return {
        "work_order_id": _uuid(5, index),
        "estimated_labor_cost": _money(estimated_labor),
        "actual_labor_cost": _money(actual_labor),
        "planned_part_cost": _money(planned_part),
        "actual_part_cost": _money(actual_part),
        "external_service_cost": _money(external),
        "total_estimated_cost": _money(total_estimated),
        "total_actual_cost": _money(total_actual),
        "cost_variance": _money(total_actual - total_estimated),
        "currency_code": "VND",
        "source_updated_at": _iso(source_time + timedelta(microseconds=index)),
        "created_at": _iso(source_time + timedelta(microseconds=index)),
    }


def _iter_costs(*, start: int, end: int) -> Iterator[dict[str, object]]:
    for index in range(start, end + 1):
        yield _cost_values(index)


def _verify_reusable(path: Path, expected: dict[str, object]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"Existing Stage 10 manifest has incompatible {key!r}.")
    for entry in manifest.get("files", []):
        file_path = Path(str(entry["path"]))
        if not file_path.exists() or checksum(file_path) != entry["sha256"]:
            raise ValueError(f"Existing Stage 10 file is missing or changed: {file_path}")
    return manifest


def _record_file(
    files: list[dict[str, object]],
    phase_root: Path,
    entity: str,
    columns: list[str],
    rows: Iterable[dict[str, object]],
    *,
    suffix: str = "",
) -> int:
    name = f"{entity}{('-' + suffix) if suffix else ''}.csv"
    count, entry = _write_csv(phase_root / name, columns, rows)
    entry["entity"] = entity
    files.append(entry)
    return count


def generate_domain_scale_dataset(
    *,
    seed: int = DEFAULT_SEED,
    run_id: str = DEFAULT_RUN_ID,
    output_root: Path = Path("data/scale"),
    phase: str = "baseline",
    batch_size: int = 50_000,
) -> dict[str, Any]:
    """Generate one restartable baseline or incremental Stage 10 manifest."""

    if phase not in {"baseline", "incremental"}:
        raise ValueError("phase must be 'baseline' or 'incremental'.")
    if not 1_000 <= batch_size <= 200_000:
        raise ValueError("batch_size must be between 1,000 and 200,000.")
    phase_root = output_root / run_id / phase
    manifest_path = phase_root / "manifest.json"
    expected = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "phase": phase,
        "seed": seed,
        "batch_size": batch_size,
    }
    reusable = _verify_reusable(manifest_path, expected)
    if reusable is not None:
        LOGGER.info("Reusing verified Stage 10 manifest %s", manifest_path)
        return reusable
    if phase == "incremental":
        baseline_manifest = output_root / run_id / "baseline" / "manifest.json"
        if not baseline_manifest.exists():
            raise FileNotFoundError("Generate the Stage 10 baseline before incremental data.")

    started = time.perf_counter()
    files: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    durations: dict[str, float] = {}

    def timed(entity: str, function) -> None:
        entity_started = time.perf_counter()
        counts[entity] = function()
        durations[entity] = round(time.perf_counter() - entity_started, 6)

    expanded_completed, late_indices = _status_fixture_sets()
    if phase == "baseline":
        support = (
            ("business_calendars", CALENDAR_COLUMNS),
            ("sla_policies", SLA_POLICY_COLUMNS),
            ("sla_policy_targets", SLA_TARGET_COLUMNS),
            ("part_categories", PART_CATEGORY_COLUMNS),
            ("units_of_measure", UNIT_COLUMNS),
            ("stock_locations", STOCK_LOCATION_COLUMNS),
        )
        for entity, columns in support:
            timed(
                entity,
                lambda entity=entity, columns=columns: _record_file(
                    files, phase_root, entity, columns, _support_rows(entity)
                ),
            )
        timed(
            "tickets",
            lambda: _record_file(files, phase_root, "tickets", TICKET_COLUMNS, _iter_tickets()),
        )
        timed(
            "ticket_links",
            lambda: _record_file(
                files,
                phase_root,
                "ticket_links",
                TICKET_LINK_COLUMNS,
                _iter_ticket_links(),
            ),
        )
        timed(
            "ticket_sla_states",
            lambda: _record_file(
                files,
                phase_root,
                "ticket_sla_states",
                TICKET_SLA_STATE_COLUMNS,
                _iter_ticket_sla_states(),
            ),
        )
        timed(
            "spare_parts",
            lambda: _record_file(
                files, phase_root, "spare_parts", SPARE_PART_COLUMNS, _iter_parts()
            ),
        )
    else:
        timed(
            "ticket_updates",
            lambda: _record_file(
                files,
                phase_root,
                "ticket_updates",
                TICKET_COLUMNS,
                _iter_tickets(update=True),
            ),
        )
        timed(
            "spare_part_updates",
            lambda: _record_file(
                files,
                phase_root,
                "spare_part_updates",
                SPARE_PART_COLUMNS,
                _iter_parts(update=True),
            ),
        )

    status_total = 0
    status_started = time.perf_counter()
    for chunk_start in range(1, WORK_ORDER_COUNT + 1, batch_size):
        chunk_end = min(WORK_ORDER_COUNT, chunk_start + batch_size - 1)
        count = _record_file(
            files,
            phase_root,
            "work_order_status_history",
            STATUS_COLUMNS,
            _iter_status_rows(
                expanded_completed,
                late_indices,
                phase=phase,
                start=chunk_start,
                end=chunk_end,
            ),
            suffix=f"{(chunk_start - 1) // batch_size + 1:05d}",
        )
        status_total += count
    counts["work_order_status_history"] = status_total
    durations["work_order_status_history"] = round(time.perf_counter() - status_started, 6)

    timed(
        "ticket_sla_events",
        lambda: _record_file(
            files,
            phase_root,
            "ticket_sla_events",
            TICKET_SLA_EVENT_COLUMNS,
            _iter_ticket_sla_events(phase=phase),
        ),
    )
    timed(
        "ticket_escalation_events",
        lambda: _record_file(
            files,
            phase_root,
            "ticket_escalation_events",
            TICKET_ESCALATION_EVENT_COLUMNS,
            _iter_ticket_escalations(phase=phase),
        ),
    )

    movement_started = time.perf_counter()
    movement_total = 0
    for start_part in range(1, SPARE_PART_COUNT + 1, max(1, batch_size // 60)):
        end_part = min(SPARE_PART_COUNT, start_part + max(1, batch_size // 60) - 1)
        movement_total += _record_file(
            files,
            phase_root,
            "inventory_movements",
            INVENTORY_MOVEMENT_COLUMNS,
            _iter_movements(phase=phase, start_part=start_part, end_part=end_part),
            suffix=f"{(start_part - 1) // max(1, batch_size // 60) + 1:05d}",
        )
    counts["inventory_movements"] = movement_total
    durations["inventory_movements"] = round(time.perf_counter() - movement_started, 6)

    cost_start = 1 if phase == "baseline" else BASELINE_COST_COUNT + 1
    cost_end = BASELINE_COST_COUNT if phase == "baseline" else COST_FACT_COUNT
    cost_started = time.perf_counter()
    cost_total = 0
    for chunk_start in range(cost_start, cost_end + 1, batch_size):
        chunk_end = min(cost_end, chunk_start + batch_size - 1)
        cost_total += _record_file(
            files,
            phase_root,
            "work_order_costs",
            COST_COLUMNS,
            _iter_costs(start=chunk_start, end=chunk_end),
            suffix=f"{(chunk_start - cost_start) // batch_size + 1:05d}",
        )
    counts["work_order_costs"] = cost_total
    durations["work_order_costs"] = round(time.perf_counter() - cost_started, 6)

    expected_phase_counts = {
        "baseline": {
            "work_order_status_history": STATUS_HISTORY_COUNT - LATE_STATUS_COUNT,
            "tickets": TICKET_COUNT,
            "ticket_sla_states": TICKET_COUNT,
            "ticket_events": TICKET_EVENT_COUNT - LATE_TICKET_EVENT_COUNT,
            "spare_parts": SPARE_PART_COUNT,
            "inventory_movements": INVENTORY_MOVEMENT_COUNT - SPARE_PART_COUNT,
            "work_order_costs": BASELINE_COST_COUNT,
        },
        "incremental": {
            "work_order_status_history": LATE_STATUS_COUNT,
            "ticket_updates": TICKET_UPDATE_COUNT,
            "ticket_events": LATE_TICKET_EVENT_COUNT,
            "spare_part_updates": PART_UPDATE_COUNT,
            "inventory_movements": SPARE_PART_COUNT,
            "work_order_costs": COST_FACT_COUNT - BASELINE_COST_COUNT,
        },
    }[phase]
    actual_ticket_events = counts["ticket_sla_events"] + counts["ticket_escalation_events"]
    validation_counts = {**counts, "ticket_events": actual_ticket_events}
    for entity, expected_count in expected_phase_counts.items():
        if validation_counts.get(entity) != expected_count:
            raise RuntimeError(
                f"Stage 10 {phase} count mismatch for {entity}: "
                f"{validation_counts.get(entity)} != {expected_count}"
            )

    duration = time.perf_counter() - started
    manifest: dict[str, Any] = {
        **expected,
        "target_counts": {
            "work_orders": WORK_ORDER_COUNT,
            "work_order_status_history": STATUS_HISTORY_COUNT,
            "tickets": TICKET_COUNT,
            "ticket_events": TICKET_EVENT_COUNT,
            "spare_parts": SPARE_PART_COUNT,
            "inventory_movements": INVENTORY_MOVEMENT_COUNT,
            "work_order_costs": COST_FACT_COUNT,
        },
        "phase_counts": validation_counts,
        "domain_duration_seconds": durations,
        "file_count": len(files),
        "files": files,
        "duration_seconds": round(duration, 6),
        "rows_per_second": round(sum(int(entry["row_count"]) for entry in files) / max(duration, 0.001), 2),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    phase_root.mkdir(parents=True, exist_ok=True)
    partial = manifest_path.with_suffix(".json.partial")
    partial.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--output-root", type=Path, default=Path("data/scale"))
    parser.add_argument("--phase", choices=("baseline", "incremental"), default="baseline")
    parser.add_argument("--batch-size", type=int, default=50_000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    manifest = generate_domain_scale_dataset(
        seed=args.seed,
        run_id=args.run_id,
        output_root=args.output_root,
        phase=args.phase,
        batch_size=args.batch_size,
    )
    print(
        json.dumps(
            {
                "run_id": manifest["run_id"],
                "phase": manifest["phase"],
                "manifest": str(args.output_root / args.run_id / args.phase / "manifest.json"),
                "phase_counts": manifest["phase_counts"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
