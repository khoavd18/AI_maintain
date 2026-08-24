"""Deterministic, streaming Stage 9 maintenance scale-data generator."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Iterable, Iterator
from uuid import UUID

from data_platform.object_store import checksum


LOGGER = logging.getLogger("data_platform.generator")
SCHEMA_VERSION = "stage9-scale-v1"
UTC = timezone.utc
BASELINE_END = datetime(2026, 8, 22, tzinfo=UTC)
INCREMENTAL_START = datetime(2026, 8, 23, tzinfo=UTC)
UPDATE_START = datetime(2026, 8, 24, 4, 0, tzinfo=UTC)

USER_COLUMNS = [
    "id",
    "username",
    "password_hash",
    "display_name",
    "role",
    "technician_id",
    "is_active",
    "created_at",
    "updated_at",
]
LOCATION_COLUMNS = [
    "id",
    "code",
    "name",
    "location_type",
    "description",
    "is_active",
    "created_at",
    "updated_at",
    "created_by_user_id",
    "updated_by_user_id",
    "version",
]
ASSET_COLUMNS = [
    "asset_id",
    "asset_name",
    "asset_type",
    "asset_category",
    "manufacturer",
    "model",
    "serial_number",
    "production_year",
    "location",
    "location_id",
    "criticality",
    "lifecycle_status",
    "operational_status",
    "installation_date",
    "installed_at",
    "commissioned_at",
    "ownership_type",
    "description",
    "last_maintenance_date",
    "maintenance_interval_days",
    "next_maintenance_date",
    "version",
    "created_at",
    "updated_at",
    "created_by_user_id",
    "updated_by_user_id",
    "qr_token",
]
PLAN_COLUMNS = [
    "id",
    "plan_code",
    "name",
    "description",
    "asset_id",
    "schedule_type",
    "interval_value",
    "interval_unit",
    "start_date",
    "local_timezone",
    "lead_time_days",
    "grace_period_days",
    "next_due_date",
    "estimated_duration_minutes",
    "default_priority",
    "default_assignee_user_id",
    "instructions",
    "status",
    "is_active",
    "created_by_user_id",
    "updated_by_user_id",
    "created_at",
    "updated_at",
    "version",
]
WORK_ORDER_COLUMNS = [
    "id",
    "work_order_number",
    "title",
    "description",
    "work_order_type",
    "asset_id",
    "preventive_plan_id",
    "assigned_to_user_id",
    "created_by_user_id",
    "verified_by_user_id",
    "priority",
    "scheduled_start_at",
    "scheduled_end_at",
    "due_date",
    "local_timezone",
    "grace_period_days",
    "estimated_duration_minutes",
    "started_at",
    "completed_at",
    "verified_at",
    "cancelled_at",
    "cancellation_reason",
    "completion_summary",
    "safety_notes",
    "labor_minutes",
    "status",
    "hold_reason",
    "created_at",
    "updated_at",
    "version",
]
LOG_COLUMNS = [
    "log_id",
    "work_order_id",
    "asset_id",
    "maintenance_date",
    "maintenance_type",
    "technician_id",
    "inspection_result",
    "actions_taken",
    "technician_note",
    "maintenance_result",
    "follow_up_required",
    "next_maintenance_date",
    "created_at",
    "updated_at",
]

_TYPES = ("preventive", "corrective", "inspection", "emergency")
_PRIORITIES = ("low", "medium", "high", "critical")
_ASSET_TYPES = ("hvac", "pump", "generator")
_MANUFACTURERS = ("Atlas", "Boreal", "Crest", "Delta", "Evergreen")
_MODELS = ("A100", "B220", "C360", "D480", "E600")
_DESCRIPTIONS = (
    "Inspect abnormal vibration and confirm mounting condition.",
    "Review cooling performance after a reported temperature deviation.",
    "Perform scheduled inspection and record operating condition.",
    "Investigate intermittent electrical warning on the control panel.",
    "Check pump flow stability and document observed condition.",
)
_RESOLUTIONS = (
    "Inspection completed; operating condition recorded for follow-up.",
    "Loose mounting corrected and functional check completed.",
    "Filter condition addressed and normal airflow confirmed.",
    "Electrical connection secured and observation completed.",
    "No immediate defect confirmed; monitoring evidence recorded.",
)


def _uuid(tag: int, index: int) -> UUID:
    if index < 0 or index >= 1 << 112:
        raise ValueError("Synthetic identifier index is out of range.")
    return UUID(int=(tag << 112) | index)


def _mix(seed: int, index: int, salt: int = 0) -> int:
    value = (seed ^ (index * 0x9E3779B97F4A7C15) ^ salt) & ((1 << 64) - 1)
    value ^= value >> 30
    value = (value * 0xBF58476D1CE4E5B9) & ((1 << 64) - 1)
    value ^= value >> 27
    value = (value * 0x94D049BB133111EB) & ((1 << 64) - 1)
    return value ^ (value >> 31)


def _iso(value: datetime | None) -> str:
    return "" if value is None else value.astimezone(UTC).isoformat()


def _dimension_counts(work_order_count: int) -> dict[str, int]:
    return {
        "sites": max(5, min(200, (work_order_count + 4_999) // 5_000)),
        "assets": max(100, min(20_000, (work_order_count + 49) // 50)),
        "technicians": max(20, min(500, (work_order_count + 1_999) // 2_000)),
    }


def _status(value: int) -> str:
    percentile = value % 100
    if percentile < 15:
        return "planned"
    if percentile < 27:
        return "assigned"
    if percentile < 40:
        return "in_progress"
    if percentile < 45:
        return "on_hold"
    if percentile < 80:
        return "completed"
    if percentile < 95:
        return "verified"
    return "cancelled"


def _work_order_type(value: int) -> str:
    percentile = value % 100
    if percentile < 35:
        return "preventive"
    if percentile < 75:
        return "corrective"
    if percentile < 95:
        return "inspection"
    return "emergency"


def _iter_users(count: int) -> Iterator[dict[str, object]]:
    created = datetime(2022, 1, 1, tzinfo=UTC)
    for index in range(1, count + 1):
        yield {
            "id": _uuid(1, index),
            "username": f"scale_tech_{index:06d}",
            "password_hash": "scale-fixture-login-disabled",
            "display_name": f"Synthetic Technician {index:06d}",
            "role": "technician",
            "technician_id": f"S9-TECH-{index:06d}",
            "is_active": "false",
            "created_at": _iso(created),
            "updated_at": _iso(created),
        }


def _iter_locations(count: int) -> Iterator[dict[str, object]]:
    creator = _uuid(1, 1)
    created = datetime(2022, 1, 1, tzinfo=UTC)
    for index in range(1, count + 1):
        yield {
            "id": _uuid(2, index),
            "code": f"S9-SITE-{index:04d}",
            "name": f"Synthetic Maintenance Site {index:04d}",
            "location_type": "plant" if index % 3 == 0 else "building",
            "description": "Deterministic Stage 9 scale fixture location.",
            "is_active": "true",
            "created_at": _iso(created),
            "updated_at": _iso(created),
            "created_by_user_id": creator,
            "updated_by_user_id": creator,
            "version": 1,
        }


def _iter_assets(count: int, site_count: int, seed: int) -> Iterator[dict[str, object]]:
    creator = _uuid(1, 1)
    for index in range(1, count + 1):
        mixed = _mix(seed, index, 11)
        installed_date = date(2012, 1, 1) + timedelta(days=mixed % 3_000)
        installed_at = datetime.combine(installed_date, datetime.min.time(), UTC)
        last_maintenance = date(2022, 1, 1) + timedelta(days=mixed % 1_200)
        interval = (30, 60, 90, 180)[mixed % 4]
        asset_type = _ASSET_TYPES[mixed % len(_ASSET_TYPES)]
        category = {
            "hvac": "climate_control",
            "pump": "water_system",
            "generator": "power_system",
        }[asset_type]
        site_index = (mixed % site_count) + 1
        created = installed_at
        yield {
            "asset_id": f"S9-ASSET-{index:07d}",
            "asset_name": f"Synthetic {asset_type.upper()} Asset {index:07d}",
            "asset_type": asset_type,
            "asset_category": category,
            "manufacturer": _MANUFACTURERS[(mixed >> 8) % len(_MANUFACTURERS)],
            "model": _MODELS[(mixed >> 16) % len(_MODELS)],
            "serial_number": f"S9SN{index:010d}",
            "production_year": installed_date.year - 1,
            "location": f"Synthetic Maintenance Site {site_index:04d}",
            "location_id": _uuid(2, site_index),
            "criticality": _PRIORITIES[(mixed >> 24) % len(_PRIORITIES)],
            "lifecycle_status": "active",
            "operational_status": ("running", "warning", "fault")[mixed % 3],
            "installation_date": installed_date.isoformat(),
            "installed_at": _iso(installed_at),
            "commissioned_at": _iso(installed_at + timedelta(days=1)),
            "ownership_type": ("owned", "leased", "managed")[mixed % 3],
            "description": "Deterministic synthetic asset; no real equipment data.",
            "last_maintenance_date": last_maintenance.isoformat(),
            "maintenance_interval_days": interval,
            "next_maintenance_date": (last_maintenance + timedelta(days=interval)).isoformat(),
            "version": 1,
            "created_at": _iso(created),
            "updated_at": _iso(datetime(2026, 1, 1, tzinfo=UTC)),
            "created_by_user_id": creator,
            "updated_by_user_id": creator,
            "qr_token": _uuid(6, index),
        }


def _iter_plans(count: int, technician_count: int) -> Iterator[dict[str, object]]:
    creator = _uuid(1, 1)
    created = datetime(2022, 1, 1, tzinfo=UTC)
    for index in range(1, count + 1):
        yield {
            "id": _uuid(4, index),
            "plan_code": f"S9-PM-{index:07d}",
            "name": f"Synthetic preventive plan {index:07d}",
            "description": "Bounded interval plan for isolated Stage 9 scale data.",
            "asset_id": f"S9-ASSET-{index:07d}",
            "schedule_type": "interval",
            "interval_value": (1, 2, 3, 6)[index % 4],
            "interval_unit": "month",
            "start_date": "2023-01-01",
            "local_timezone": "Asia/Ho_Chi_Minh",
            "lead_time_days": 7,
            "grace_period_days": index % 4,
            "next_due_date": "2023-01-01",
            "estimated_duration_minutes": 30 + (index % 8) * 15,
            "default_priority": _PRIORITIES[index % len(_PRIORITIES)],
            "default_assignee_user_id": _uuid(1, ((index - 1) % technician_count) + 1),
            "instructions": "Follow the approved synthetic inspection checklist.",
            "status": "active",
            "is_active": "true",
            "created_by_user_id": creator,
            "updated_by_user_id": creator,
            "created_at": _iso(created),
            "updated_at": _iso(created),
            "version": 1,
        }


def _work_order_row(
    index: int,
    *,
    seed: int,
    asset_count: int,
    technician_count: int,
    baseline_count: int,
    update: bool = False,
) -> dict[str, object]:
    mixed = _mix(seed, index, 23)
    asset_index = ((index - 1) % asset_count) + 1
    technician_index = ((mixed >> 12) % technician_count) + 1
    work_type = _work_order_type(mixed >> 5)
    status = _status(mixed >> 17)
    priority = _PRIORITIES[(mixed >> 29) % len(_PRIORITIES)]
    created = datetime(2023, 1, 1, tzinfo=UTC) + timedelta(
        days=mixed % 1_200, seconds=(mixed >> 32) % 86_400
    )
    if work_type == "preventive":
        # One plan is generated per asset.  The asset-cycle occurrence makes
        # (preventive_plan_id, due_date) deterministic and collision-free.
        occurrence = (index - 1) // asset_count
        created = datetime(2023, 1, 1, tzinfo=UTC) + timedelta(
            days=occurrence * 7,
            hours=(asset_index - 1) % 24,
        )
    scheduled = created + timedelta(days=1 + mixed % 7)
    duration_minutes = 30 + (mixed % 45) * 10
    scheduled_end = scheduled + timedelta(minutes=duration_minutes)
    started = None
    completed = None
    verified = None
    cancelled = None
    assignee: UUID | None = _uuid(1, technician_index)
    completion_summary = ""
    cancellation_reason = ""
    hold_reason = ""
    labor_minutes: int | str = ""

    if status == "planned":
        assignee = None if mixed % 3 else assignee
    elif status == "assigned":
        pass
    elif status in {"in_progress", "on_hold", "completed", "verified"}:
        started = scheduled + timedelta(minutes=mixed % 90)
        if status == "on_hold":
            hold_reason = "Awaiting bounded synthetic inspection evidence."
        if status in {"completed", "verified"}:
            completed = started + timedelta(minutes=duration_minutes)
            labor_minutes = duration_minutes
            completion_summary = _RESOLUTIONS[mixed % len(_RESOLUTIONS)]
            if status == "verified":
                verified = completed + timedelta(hours=2 + mixed % 24)
    else:
        cancelled = scheduled - timedelta(hours=1)
        cancellation_reason = "Synthetic request superseded before field execution."
        if mixed % 2:
            assignee = None

    lifecycle_times = [
        value for value in (created, started, completed, verified, cancelled) if value
    ]
    updated = max(lifecycle_times) + timedelta(minutes=1 + mixed % 180)
    if index <= baseline_count:
        updated = min(updated, BASELINE_END - timedelta(days=1))
        if index > max(0, baseline_count - 128):
            updated = BASELINE_END
    else:
        updated = INCREMENTAL_START + timedelta(seconds=index - baseline_count)
    version = 1
    description = _DESCRIPTIONS[mixed % len(_DESCRIPTIONS)]
    if update:
        # Shared-second microsecond ties exercise the tuple key without moving
        # the watermark into the future relative to this benchmark run.
        updated = UPDATE_START + timedelta(microseconds=index)
        version = 2
        description += " Late deterministic update recorded for incremental validation."
        if completion_summary:
            completion_summary += " Late review note appended."

    return {
        "id": _uuid(5, index),
        "work_order_number": f"S9-WO-{index:09d}",
        "title": f"Synthetic maintenance work order {index:09d}",
        "description": description,
        "work_order_type": work_type,
        "asset_id": f"S9-ASSET-{asset_index:07d}",
        "preventive_plan_id": _uuid(4, asset_index) if work_type == "preventive" else "",
        "assigned_to_user_id": assignee or "",
        "created_by_user_id": _uuid(1, 1),
        "verified_by_user_id": _uuid(1, ((technician_index) % technician_count) + 1)
        if status == "verified"
        else "",
        "priority": priority,
        "scheduled_start_at": _iso(scheduled),
        "scheduled_end_at": _iso(scheduled_end),
        "due_date": scheduled.date().isoformat(),
        "local_timezone": "Asia/Ho_Chi_Minh",
        "grace_period_days": mixed % 4,
        "estimated_duration_minutes": duration_minutes,
        "started_at": _iso(started),
        "completed_at": _iso(completed),
        "verified_at": _iso(verified),
        "cancelled_at": _iso(cancelled),
        "cancellation_reason": cancellation_reason,
        "completion_summary": completion_summary,
        "safety_notes": "" if mixed % 5 else "Follow the approved site safety procedure.",
        "labor_minutes": labor_minutes,
        "status": status,
        "hold_reason": hold_reason,
        "created_at": _iso(created),
        "updated_at": _iso(updated),
        "version": version,
    }


def _maintenance_log_row(row: dict[str, object], index: int) -> dict[str, object] | None:
    if row["status"] not in {"completed", "verified"}:
        return None
    completed = datetime.fromisoformat(str(row["completed_at"]))
    maintenance_date = completed.date()
    technician_uuid = str(row["assigned_to_user_id"])
    technician_index = UUID(technician_uuid).int & ((1 << 112) - 1)
    return {
        "log_id": f"S9-LOG-{index:09d}",
        "work_order_id": row["id"],
        "asset_id": row["asset_id"],
        "maintenance_date": maintenance_date.isoformat(),
        "maintenance_type": row["work_order_type"],
        "technician_id": f"S9-TECH-{technician_index:06d}",
        "inspection_result": "Deterministic inspection evidence recorded.",
        "actions_taken": str(row["completion_summary"]),
        "technician_note": "Synthetic note; no private or real-person information.",
        "maintenance_result": "resolved",
        "follow_up_required": "false",
        "next_maintenance_date": (maintenance_date + timedelta(days=90)).isoformat(),
        "created_at": row["completed_at"],
        "updated_at": row["updated_at"],
    }


def _write_csv(
    path: Path,
    columns: list[str],
    rows: Iterable[dict[str, object]],
) -> tuple[int, dict[str, object]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    row_count = 0
    with partial.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            row_count += 1
    partial.replace(path)
    return row_count, {
        "path": path.as_posix(),
        "name": path.name,
        "row_count": row_count,
        "size_bytes": path.stat().st_size,
        "sha256": checksum(path),
    }


def _manifest_is_reusable(path: Path, expected: dict[str, object]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"Existing manifest has incompatible {key!r}; choose a new run ID.")
    for entry in manifest.get("files", []):
        file_path = Path(entry["path"])
        if not file_path.exists() or checksum(file_path) != entry["sha256"]:
            raise ValueError(f"Existing generated file is missing or changed: {file_path}")
    return manifest


def generate_scale_dataset(
    *,
    work_order_count: int,
    seed: int,
    run_id: str,
    output_root: Path = Path("data/scale"),
    phase: str = "baseline",
    batch_size: int = 50_000,
    baseline_count: int = 1_000_000,
    update_count: int = 0,
) -> dict[str, Any]:
    """Generate one restartable baseline or incremental dataset manifest."""

    if phase not in {"baseline", "incremental"}:
        raise ValueError("phase must be 'baseline' or 'incremental'.")
    if work_order_count < 0 or update_count < 0:
        raise ValueError("row counts must be non-negative.")
    if not 1_000 <= batch_size <= 200_000:
        raise ValueError("batch_size must be between 1,000 and 200,000.")
    if phase == "baseline":
        baseline_count = work_order_count
        update_count = 0
    elif update_count > baseline_count:
        raise ValueError("update_count cannot exceed the baseline work-order count.")

    phase_root = output_root / run_id / phase
    manifest_path = phase_root / "manifest.json"
    expected = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "phase": phase,
        "seed": seed,
        "requested_work_orders": work_order_count,
        "baseline_count": baseline_count,
        "update_count": update_count,
        "batch_size": batch_size,
    }
    reusable = _manifest_is_reusable(manifest_path, expected)
    if reusable is not None:
        LOGGER.info("Reusing verified manifest %s", manifest_path)
        return reusable

    started = time.perf_counter()
    files: list[dict[str, object]] = []
    dimensions = _dimension_counts(baseline_count)
    if phase == "incremental":
        baseline_manifest_path = output_root / run_id / "baseline" / "manifest.json"
        if not baseline_manifest_path.exists():
            raise FileNotFoundError("Generate the matching baseline before incremental data.")
        baseline_manifest = json.loads(baseline_manifest_path.read_text(encoding="utf-8"))
        if (
            baseline_manifest["seed"] != seed
            or baseline_manifest["actual_work_orders"] != baseline_count
        ):
            raise ValueError("Incremental parameters do not match the baseline manifest.")
        dimensions = baseline_manifest["dimension_counts"]

    if phase == "baseline":
        dependency_specs = (
            ("users", USER_COLUMNS, _iter_users(dimensions["technicians"])),
            ("locations", LOCATION_COLUMNS, _iter_locations(dimensions["sites"])),
            (
                "assets",
                ASSET_COLUMNS,
                _iter_assets(dimensions["assets"], dimensions["sites"], seed),
            ),
            (
                "preventive_plans",
                PLAN_COLUMNS,
                _iter_plans(dimensions["assets"], dimensions["technicians"]),
            ),
        )
        for entity, columns, rows in dependency_specs:
            _, entry = _write_csv(phase_root / f"{entity}.csv", columns, rows)
            entry["entity"] = entity
            files.append(entry)

    start_index = 1 if phase == "baseline" else baseline_count + 1
    end_index = start_index + work_order_count - 1
    generated_work_orders = 0
    generated_logs = 0
    chunk_number = 0
    for chunk_start in range(start_index, end_index + 1, batch_size):
        chunk_number += 1
        chunk_end = min(end_index, chunk_start + batch_size - 1)

        def work_rows() -> Iterator[dict[str, object]]:
            for index in range(chunk_start, chunk_end + 1):
                yield _work_order_row(
                    index,
                    seed=seed,
                    asset_count=dimensions["assets"],
                    technician_count=dimensions["technicians"],
                    baseline_count=baseline_count,
                )

        count, entry = _write_csv(
            phase_root / f"work_orders-{chunk_number:05d}.csv",
            WORK_ORDER_COLUMNS,
            work_rows(),
        )
        entry["entity"] = "work_orders"
        files.append(entry)
        generated_work_orders += count

        def log_rows() -> Iterator[dict[str, object]]:
            for index in range(chunk_start, chunk_end + 1):
                log_row = _maintenance_log_row(
                    _work_order_row(
                        index,
                        seed=seed,
                        asset_count=dimensions["assets"],
                        technician_count=dimensions["technicians"],
                        baseline_count=baseline_count,
                    ),
                    index,
                )
                if log_row is not None:
                    yield log_row

        log_count, log_entry = _write_csv(
            phase_root / f"maintenance_logs-{chunk_number:05d}.csv",
            LOG_COLUMNS,
            log_rows(),
        )
        log_entry["entity"] = "maintenance_logs"
        files.append(log_entry)
        generated_logs += log_count
        elapsed = max(time.perf_counter() - started, 0.001)
        LOGGER.info(
            "Generated %d/%d work orders (%.0f rows/s)",
            generated_work_orders,
            work_order_count,
            generated_work_orders / elapsed,
        )

    generated_updates = 0
    if phase == "incremental" and update_count:
        update_chunk_number = 0
        for chunk_start in range(1, update_count + 1, batch_size):
            update_chunk_number += 1
            chunk_end = min(update_count, chunk_start + batch_size - 1)

            def update_rows() -> Iterator[dict[str, object]]:
                for index in range(chunk_start, chunk_end + 1):
                    yield _work_order_row(
                        index,
                        seed=seed,
                        asset_count=dimensions["assets"],
                        technician_count=dimensions["technicians"],
                        baseline_count=baseline_count,
                        update=True,
                    )

            count, entry = _write_csv(
                phase_root / f"work_order_updates-{update_chunk_number:05d}.csv",
                WORK_ORDER_COLUMNS,
                update_rows(),
            )
            entry["entity"] = "work_order_updates"
            files.append(entry)
            generated_updates += count

    duration = time.perf_counter() - started
    manifest: dict[str, Any] = {
        **expected,
        "actual_work_orders": generated_work_orders,
        "actual_updates": generated_updates,
        "maintenance_log_rows": generated_logs,
        "dimension_counts": dimensions,
        "file_count": len(files),
        "files": files,
        "generated_at": datetime.now(UTC).isoformat(),
        "duration_seconds": round(duration, 6),
        "work_order_rows_per_second": round(generated_work_orders / max(duration, 0.001), 2),
    }
    phase_root.mkdir(parents=True, exist_ok=True)
    partial_manifest = manifest_path.with_suffix(".json.partial")
    partial_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    partial_manifest.replace(manifest_path)
    LOGGER.info("Manifest written: %s", manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-order-count", type=int, required=True)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--run-id", default="stage9-1m-seed-20260823")
    parser.add_argument("--output-root", type=Path, default=Path("data/scale"))
    parser.add_argument("--phase", choices=("baseline", "incremental"), default="baseline")
    parser.add_argument("--batch-size", type=int, default=50_000)
    parser.add_argument("--baseline-count", type=int, default=1_000_000)
    parser.add_argument("--update-count", type=int, default=0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    manifest = generate_scale_dataset(
        work_order_count=args.work_order_count,
        seed=args.seed,
        run_id=args.run_id,
        output_root=args.output_root,
        phase=args.phase,
        batch_size=args.batch_size,
        baseline_count=args.baseline_count,
        update_count=args.update_count,
    )
    print(
        json.dumps(
            {
                "run_id": manifest["run_id"],
                "phase": manifest["phase"],
                "actual_work_orders": manifest["actual_work_orders"],
                "actual_updates": manifest["actual_updates"],
                "manifest": str(args.output_root / args.run_id / args.phase / "manifest.json"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()


def generate_domain_scale_dataset(**kwargs: Any) -> dict[str, Any]:
    """Lazy Stage 10 extension while preserving the Stage 9 CLI and imports."""

    from data_platform.domain_generator import generate_domain_scale_dataset as generate

    return generate(**kwargs)
