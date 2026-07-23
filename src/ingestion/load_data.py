"""Idempotent CSV seed import for canonical PostgreSQL transactional tables."""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pandas as pd
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.config.value_mappings import (
    ASSET_TYPE_VI_TO_CODE,
    ASSET_TYPE_TO_CATEGORY_CODE,
    CRITICALITY_VI_TO_CODE,
    FAILURE_TYPE_VI_TO_CODE,
    MAINTENANCE_RESULT_VI_TO_CODE,
    MAINTENANCE_TYPE_VI_TO_CODE,
    PRIORITY_VI_TO_CODE,
    LEGACY_ASSET_STATUS_TO_OPERATIONAL,
    STATUS_VI_TO_CODE,
)
from src.asset_management.qr import asset_qr_token
from src.database.models import (
    Asset,
    AssetAttachment,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Location,
    MaintenanceLog,
    PreventiveMaintenancePlan,
    Ticket,
    WorkOrder,
    WorkOrderAttachment,
    WorkOrderChecklistItem,
)
from src.database.session import build_engine
from src.ingestion.validation import validate_csv_dataset

EXPECTED_TABLES = {
    "assets",
    "locations",
    "asset_attachments",
    "maintenance_tickets",
    "maintenance_logs",
    "checklist_templates",
    "checklist_template_items",
    "preventive_maintenance_plans",
    "work_orders",
    "work_order_checklist_items",
    "work_order_attachments",
}
ID_PATTERN = re.compile(r"^[A-Z]+-(\d+)$")


class NonEmptyDatabaseError(RuntimeError):
    """Raised when a seed import would overwrite transactional data implicitly."""


@dataclass(frozen=True)
class ImportReport:
    """Auditable result for a dry run or committed seed import."""

    counts: dict[str, int]
    existing_counts: dict[str, int]
    dry_run: bool
    replaced: bool


def import_csv_dataset(
    input_dir: Path = Path("data/raw"),
    database_url: str | None = None,
    *,
    replace: bool = False,
    dry_run: bool = False,
) -> ImportReport:
    """Validate and import the three transactional CSV datasets atomically."""

    frames = validate_csv_dataset(input_dir)
    location_ids = {
        name: _location_identity(name)[0]
        for name in sorted(frames["assets"]["location"].astype(str).unique())
    }
    records = {
        "assets": _asset_records(frames["assets"], location_ids),
        "maintenance_tickets": _ticket_records(frames["maintenance_tickets"]),
        "maintenance_logs": _maintenance_log_records(frames["maintenance_logs"]),
    }
    counts = {name: len(values) for name, values in records.items()}
    engine = build_engine(database_url)
    table_names = set(inspect(engine).get_table_names())
    missing = EXPECTED_TABLES - table_names
    if missing:
        raise RuntimeError(
            "PostgreSQL schema is not at the canonical migration. "
            "Run `alembic upgrade head` before importing."
        )

    with Session(engine) as session:
        try:
            with session.begin():
                existing_counts = _database_counts(session)
                if any(existing_counts.values()) and not replace:
                    raise NonEmptyDatabaseError(
                        "PostgreSQL transactional tables are not empty. Use --replace only "
                        "for an explicit demo reset; no rows were changed."
                    )
                if dry_run:
                    return ImportReport(
                        counts=counts,
                        existing_counts=existing_counts,
                        dry_run=True,
                        replaced=replace and any(existing_counts.values()),
                    )
                persisted_location_ids = _ensure_seed_locations(
                    session,
                    sorted(frames["assets"]["location"].astype(str).unique()),
                )
                records["assets"] = _asset_records(
                    frames["assets"], persisted_location_ids
                )
                if replace:
                    session.execute(delete(WorkOrderAttachment))
                    session.execute(delete(AssetAttachment))
                    session.execute(delete(MaintenanceLog))
                    session.execute(delete(WorkOrderChecklistItem))
                    session.execute(delete(WorkOrder))
                    session.execute(delete(PreventiveMaintenancePlan))
                    session.execute(delete(ChecklistTemplateItem))
                    session.execute(delete(ChecklistTemplate))
                    session.execute(delete(Ticket))
                    session.execute(delete(Asset))
                session.execute(Asset.__table__.insert(), records["assets"])
                session.execute(
                    Ticket.__table__.insert(),
                    records["maintenance_tickets"],
                )
                session.execute(
                    MaintenanceLog.__table__.insert(),
                    records["maintenance_logs"],
                )
                _synchronize_sequence(
                    session,
                    "maintenance_ticket_id_seq",
                    [record["ticket_id"] for record in records["maintenance_tickets"]],
                )
                _synchronize_sequence(
                    session,
                    "maintenance_log_id_seq",
                    [record["log_id"] for record in records["maintenance_logs"]],
                )
        except IntegrityError as exc:
            raise RuntimeError(
                "CSV import violated a PostgreSQL uniqueness, foreign-key, or check constraint; "
                "the transaction was rolled back."
            ) from exc

    return ImportReport(
        counts=counts,
        existing_counts=existing_counts,
        dry_run=False,
        replaced=replace and any(existing_counts.values()),
    )


def load_csv_dataset(
    input_dir: Path = Path("data/raw"),
    database_url: str | None = None,
    replace: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    """Compatibility wrapper returning the imported transactional row counts."""

    return import_csv_dataset(
        input_dir=input_dir,
        database_url=database_url,
        replace=replace,
        dry_run=dry_run,
    ).counts


def _database_counts(session: Session) -> dict[str, int]:
    return {
        "assets": int(session.scalar(select(func.count()).select_from(Asset)) or 0),
        "maintenance_tickets": int(
            session.scalar(select(func.count()).select_from(Ticket)) or 0
        ),
        "maintenance_logs": int(
            session.scalar(select(func.count()).select_from(MaintenanceLog)) or 0
        ),
    }


def _asset_records(
    frame: pd.DataFrame,
    location_ids: dict[str, UUID],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        asset_type = _map_value(
            str(row["asset_type"]), ASSET_TYPE_VI_TO_CODE, "asset_type"
        )
        legacy_status = _map_value(str(row["status"]), STATUS_VI_TO_CODE, "status")
        installation_date = pd.Timestamp(row["installation_date"]).date()
        records.append(
            {
                "asset_id": str(row["asset_id"]),
                "asset_name": str(row["asset_name"]),
                "asset_type": asset_type,
                "asset_category": ASSET_TYPE_TO_CATEGORY_CODE.get(asset_type, "other"),
                "location": str(row["location"]),
                "location_id": location_ids[str(row["location"])],
                "criticality": _map_value(
                    str(row["criticality"]),
                    CRITICALITY_VI_TO_CODE,
                    "criticality",
                ),
                "operational_status": LEGACY_ASSET_STATUS_TO_OPERATIONAL[legacy_status],
                "lifecycle_status": "active",
                "installation_date": installation_date,
                "installed_at": datetime.combine(
                    installation_date,
                    time.min,
                    tzinfo=timezone.utc,
                ),
                "ownership_type": "owned",
                "last_maintenance_date": pd.Timestamp(
                    row["last_maintenance_date"]
                ).date(),
                "maintenance_interval_days": int(row["maintenance_interval_days"]),
                "next_maintenance_date": pd.Timestamp(
                    row["next_maintenance_date"]
                ).date(),
                "qr_token": asset_qr_token(str(row["asset_id"])),
            }
        )
    return records


def _ticket_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        records.append(
            {
                "ticket_id": str(row["ticket_id"]),
                "asset_id": str(row["asset_id"]),
                "issue_description": str(row["issue_description"]),
                "priority": _map_value(
                    str(row["priority"]), PRIORITY_VI_TO_CODE, "priority"
                ),
                "status": _map_value(str(row["status"]), STATUS_VI_TO_CODE, "status"),
                "failure_category": _map_value(
                    str(row["failure_category"]),
                    FAILURE_TYPE_VI_TO_CODE,
                    "failure_category",
                ),
                "created_at": _timestamp(row["created_at"]),
                "resolved_at": _optional_timestamp(row.get("resolved_at")),
                "technician_id": str(row["technician_id"]),
                "manager_note": _optional_text(row.get("manager_note")),
                "note": _optional_text(row.get("note")),
            }
        )
    return records


def _maintenance_log_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        records.append(
            {
                "log_id": str(row["log_id"]),
                "ticket_id": _optional_text(row.get("ticket_id")),
                "asset_id": str(row["asset_id"]),
                "maintenance_date": pd.Timestamp(row["maintenance_date"]).date(),
                "maintenance_type": _map_value(
                    str(row["maintenance_type"]),
                    MAINTENANCE_TYPE_VI_TO_CODE,
                    "maintenance_type",
                ),
                "technician_id": str(row["technician_id"]),
                "inspection_result": str(row["inspection_result"]),
                "actions_taken": str(row["actions_taken"]),
                "parts_replaced": _optional_text(row.get("parts_replaced")),
                "technician_note": str(row["technician_note"]),
                "maintenance_result": _map_value(
                    str(row["maintenance_result"]),
                    MAINTENANCE_RESULT_VI_TO_CODE,
                    "maintenance_result",
                ),
                "follow_up_required": _as_bool(row["follow_up_required"]),
                "next_maintenance_date": pd.Timestamp(
                    row["next_maintenance_date"]
                ).date(),
            }
        )
    return records


def _synchronize_sequence(session: Session, name: str, identifiers: list[str]) -> None:
    numbers = []
    for identifier in identifiers:
        match = ID_PATTERN.fullmatch(identifier)
        if match is None:
            raise ValueError(f"Identifier không theo canonical sequence: {identifier}")
        numbers.append(int(match.group(1)))
    maximum = max(numbers, default=1)
    session.execute(
        text("SELECT setval(CAST(:sequence_name AS regclass), :value, :is_called)"),
        {
            "sequence_name": name,
            "value": maximum,
            "is_called": bool(numbers),
        },
    )


def _ensure_seed_locations(session: Session, names: list[str]) -> dict[str, UUID]:
    root_id = uuid5(NAMESPACE_URL, "ai-maintenance-copilot:location:facility-root")
    root = session.scalar(select(Location).where(Location.code == "FACILITY-ROOT"))
    if root is None:
        root = Location(
            id=root_id,
            code="FACILITY-ROOT",
            name="Cơ sở chính",
            location_type="building",
        )
        session.add(root)
        session.flush()
    result: dict[str, UUID] = {}
    for name in names:
        suggested_id, code = _location_identity(name)
        location = session.scalar(select(Location).where(Location.code == code))
        if location is None:
            location = Location(
                id=suggested_id,
                code=code,
                name=name,
                location_type="area",
                parent_id=root.id,
            )
            session.add(location)
            session.flush()
        result[name] = location.id
    return result


def _location_identity(name: str) -> tuple[UUID, str]:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:10].upper()
    location_id = uuid5(NAMESPACE_URL, f"ai-maintenance-copilot:location:{name}")
    return location_id, f"LOC-{digest}"


def _map_value(value: str, mapping: dict[str, str], field: str) -> str:
    try:
        return mapping[value]
    except KeyError as exc:
        raise ValueError(f"Giá trị {field} không được hỗ trợ: {value}") from exc


def _timestamp(value: object) -> datetime:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp phải có timezone: {value}")
    return parsed.to_pydatetime()


def _optional_timestamp(value: object) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    return _timestamp(value)


def _optional_text(value: object) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"Giá trị boolean không hợp lệ: {value!r}")
    return normalized == "true"


def main() -> None:
    """Run the explicit seed import from the command line."""

    parser = argparse.ArgumentParser(
        description="Import canonical CSV assets, tickets, and logs into PostgreSQL."
    )
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL from the environment.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Explicitly replace existing transactional rows for a demo reset.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate files and database state without writing rows.",
    )
    args = parser.parse_args()

    try:
        report = import_csv_dataset(
            input_dir=args.input_dir,
            database_url=args.database_url,
            replace=args.replace,
            dry_run=args.dry_run,
        )
    except NonEmptyDatabaseError as exc:
        parser.exit(2, f"Import refused: {exc}\n")
    mode = "Would import" if report.dry_run else "Imported"
    for name, count in report.counts.items():
        print(f"{mode} {count:>7} rows: {name}")
    print(
        "Existing rows before operation: "
        + ", ".join(f"{name}={count}" for name, count in report.existing_counts.items())
    )
    print(f"Replace requested: {str(args.replace).lower()}")


if __name__ == "__main__":
    main()
