"""Explicit development seed commands for spare-parts inventory."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import get_settings
from src.database.models import (
    Asset,
    PartReorderConfiguration,
    WorkOrder,
)
from src.database.session import get_session_factory
from src.inventory_management.service import build_inventory_management_service
from src.security.audit import AuditContext
from src.security.cli_context import load_cli_actor
from src.security.permissions import Role
from src.security.service import CurrentUser

_SEED_OCCURRED_AT = datetime(2026, 7, 1, 1, 0, tzinfo=timezone.utc)

CATEGORY_SPECS = (
    ("FILTERS", "Bộ lọc", "Filters"),
    ("DRIVE", "Truyền động", "Drive components"),
    ("PUMP_COMPONENTS", "Linh kiện máy bơm", "Pump components"),
    ("ELECTRICAL", "Điện và điều khiển", "Electrical"),
    ("LUBRICANTS", "Dầu và chất bôi trơn", "Lubricants"),
    ("SEALS", "Phớt và gioăng", "Seals"),
)
UNIT_SPECS = (
    ("EA", "Cái", "Each", "cái", 0),
    ("L", "Lít", "Litre", "L", 3),
    ("M", "Mét", "Metre", "m", 2),
)
LOCATION_SPECS = (
    ("MAIN", "Kho chính", "main_store"),
    ("ENGINEERING", "Kho kỹ thuật", "engineering_store"),
    ("VAN-01", "Kho xe kỹ thuật 01", "technician_van"),
    ("MAINT-ROOM", "Phòng bảo trì", "maintenance_room"),
    ("QUARANTINE", "Khu cách ly vật tư", "quarantine"),
)
PART_SPECS = (
    (
        "HVAC-FILTER-001",
        "Lọc gió HVAC",
        "HVAC air filter",
        "FILTERS",
        "EA",
        ["hvac"],
        "4",
        "6",
        "24",
        "18",
        "180000",
    ),
    (
        "HVAC-BELT-A42",
        "Dây curoa HVAC A42",
        "HVAC A42 belt",
        "DRIVE",
        "EA",
        ["hvac"],
        "2",
        "3",
        "10",
        "6",
        "320000",
    ),
    (
        "PUMP-BEARING-6205",
        "Vòng bi máy bơm 6205",
        "Pump bearing 6205",
        "PUMP_COMPONENTS",
        "EA",
        ["pump"],
        "2",
        "3",
        "12",
        "8",
        "450000",
    ),
    (
        "PUMP-SEAL-032",
        "Phớt cơ khí máy bơm 32 mm",
        "Pump mechanical seal 32 mm",
        "SEALS",
        "EA",
        ["pump"],
        "2",
        "4",
        "15",
        "10",
        "680000",
    ),
    (
        "GEN-FILTER-FUEL",
        "Lọc nhiên liệu máy phát",
        "Generator fuel filter",
        "FILTERS",
        "EA",
        ["generator"],
        "2",
        "4",
        "12",
        "8",
        "250000",
    ),
    (
        "GEN-OIL-15W40",
        "Dầu động cơ máy phát 15W-40",
        "Generator engine oil 15W-40",
        "LUBRICANTS",
        "L",
        ["generator"],
        "20",
        "30",
        "100",
        "60",
        "145000",
    ),
    (
        "GEN-BATTERY-12V",
        "Ắc quy máy phát 12V",
        "Generator battery 12V",
        "ELECTRICAL",
        "EA",
        ["generator"],
        "1",
        "2",
        "6",
        "4",
        "2200000",
    ),
    (
        "GEN-FUSE-40A",
        "Cầu chì máy phát 40A",
        "Generator fuse 40A",
        "ELECTRICAL",
        "EA",
        ["generator"],
        "5",
        "8",
        "30",
        "20",
        "85000",
    ),
)
WORK_ORDER_PART_BY_ASSET_TYPE = {
    "hvac": "HVAC-FILTER-001",
    "pump": "PUMP-BEARING-6205",
    "generator": "GEN-FILTER-FUEL",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    seed = subparsers.add_parser("seed-development")
    seed.add_argument("--storekeeper-username", default="storekeeper.demo")
    seed.add_argument("--engineer-username", default="engineer.demo")
    args = parser.parse_args()

    settings = get_settings()
    if settings.storage_backend != "postgresql":
        raise SystemExit("Inventory seed requires STORAGE_BACKEND=postgresql.")
    if settings.app_environment not in {"development", "test"}:
        raise SystemExit("seed-development is allowed only in development/test.")

    storekeeper = load_cli_actor(args.storekeeper_username)
    engineer = load_cli_actor(args.engineer_username)
    if storekeeper.role not in {Role.STOREKEEPER, Role.ADMINISTRATOR}:
        raise SystemExit("--storekeeper-username must be Storekeeper or Administrator.")
    if engineer.role not in {Role.CHIEF_ENGINEER, Role.ADMINISTRATOR}:
        raise SystemExit("--engineer-username must be Chief Engineer or Administrator.")

    report = seed_development_inventory(
        build_inventory_management_service(),
        storekeeper=storekeeper,
        engineer=engineer,
        session_factory=get_session_factory(settings.database_url),
    )
    for label, value in report.items():
        print(f"{label}: {value}")


def seed_development_inventory(
    service,
    *,
    storekeeper: CurrentUser,
    engineer: CurrentUser,
    session_factory: sessionmaker[Session],
) -> dict[str, int]:
    """Idempotently seed a focused inventory demo through named service actions."""

    report = {
        "created_categories": 0,
        "created_units": 0,
        "created_locations": 0,
        "created_parts": 0,
        "created_reorder_configurations": 0,
        "opening_balances_reconciled": 0,
        "created_requirements": 0,
        "created_reservations": 0,
        "work_orders_skipped": 0,
    }
    store_context = _audit(storekeeper, "cli-inventory-seed-storekeeper")
    engineer_context = _audit(engineer, "cli-inventory-seed-engineer")

    categories = {
        item["code"]: item
        for item in service.list_categories(actor=storekeeper, include_inactive=True)
    }
    for code, name_vi, name_en in CATEGORY_SPECS:
        if code not in categories:
            categories[code] = service.create_category(
                {
                    "code": code,
                    "name_vi": name_vi,
                    "name_en": name_en,
                    "description": "Dữ liệu development có kiểm soát.",
                },
                actor=storekeeper,
                audit_context=store_context,
            )
            report["created_categories"] += 1

    units = {
        item["code"]: item for item in service.list_units(actor=storekeeper, include_inactive=True)
    }
    for code, name_vi, name_en, symbol, precision in UNIT_SPECS:
        if code not in units:
            units[code] = service.create_unit(
                {
                    "code": code,
                    "name_vi": name_vi,
                    "name_en": name_en,
                    "symbol": symbol,
                    "quantity_precision": precision,
                },
                actor=storekeeper,
                audit_context=store_context,
            )
            report["created_units"] += 1

    locations = {
        item["code"]: item
        for item in service.list_stock_locations(actor=storekeeper, include_archived=True)
    }
    for code, name, location_type in LOCATION_SPECS:
        if code not in locations:
            locations[code] = service.create_stock_location(
                {
                    "code": code,
                    "name": name,
                    "location_type": location_type,
                    "description": "Stock location cho development demo.",
                },
                actor=storekeeper,
                audit_context=store_context,
            )
            report["created_locations"] += 1

    part_page = service.list_parts(
        actor=storekeeper,
        filters={},
        sort_by="part_number",
        sort_direction="asc",
        page=1,
        page_size=200,
    )
    parts = {item["part_number"]: item for item in part_page["items"]}
    for spec in PART_SPECS:
        (
            number,
            name_vi,
            name_en,
            category_code,
            unit_code,
            asset_types,
            minimum,
            reorder,
            maximum,
            opening_quantity,
            unit_cost,
        ) = spec
        if number not in parts:
            parts[number] = service.create_part(
                {
                    "part_number": number,
                    "name_vi": name_vi,
                    "name_en": name_en,
                    "category_id": categories[category_code]["id"],
                    "unit_of_measure_id": units[unit_code]["id"],
                    "manufacturer_reference": f"DEMO-{number}",
                    "compatible_asset_types": asset_types,
                    "minimum_stock": Decimal(minimum),
                    "reorder_point": Decimal(reorder),
                    "maximum_stock": Decimal(maximum),
                    "unit_cost": Decimal(unit_cost),
                    "currency_code": "VND",
                },
                actor=storekeeper,
                audit_context=store_context,
            )
            report["created_parts"] += 1
        service.create_opening_balance(
            {
                "part_id": parts[number]["id"],
                "stock_location_id": locations["MAIN"]["id"],
                "quantity": Decimal(opening_quantity),
                "business_reference": f"DEMO-OPENING-{number}",
                "occurred_at": _SEED_OCCURRED_AT,
                "reason": "Số dư đầu kỳ development demo",
                "unit_cost_snapshot": Decimal(unit_cost),
            },
            idempotency_key=f"pm6-seed-opening-{number.lower()}",
            actor=storekeeper,
            audit_context=store_context,
        )
        report["opening_balances_reconciled"] += 1

    report["created_reorder_configurations"] += _seed_reorder_configurations(
        service,
        parts=parts,
        main_location=locations["MAIN"],
        storekeeper=storekeeper,
        audit_context=store_context,
        session_factory=session_factory,
    )
    requirement_report = _seed_work_order_requirements(
        service,
        parts=parts,
        main_location=locations["MAIN"],
        engineer=engineer,
        audit_context=engineer_context,
        session_factory=session_factory,
    )
    report.update(requirement_report)
    return report


def _seed_reorder_configurations(
    service,
    *,
    parts: dict[str, dict[str, Any]],
    main_location: dict[str, Any],
    storekeeper: CurrentUser,
    audit_context: AuditContext,
    session_factory: sessionmaker[Session],
) -> int:
    selected = {
        "HVAC-FILTER-001": ("4", "6", "24"),
        "PUMP-BEARING-6205": ("2", "3", "12"),
        "GEN-FILTER-FUEL": ("2", "4", "12"),
    }
    created = 0
    for number, thresholds in selected.items():
        part_id = UUID(str(parts[number]["id"]))
        location_id = UUID(str(main_location["id"]))
        with session_factory() as session:
            existing = session.scalar(
                select(PartReorderConfiguration).where(
                    PartReorderConfiguration.part_id == part_id,
                    PartReorderConfiguration.stock_location_id == location_id,
                )
            )
        if existing is not None:
            continue
        minimum, reorder, maximum = thresholds
        service.upsert_reorder_configuration(
            part_id,
            {
                "stock_location_id": location_id,
                "minimum_stock": Decimal(minimum),
                "reorder_point": Decimal(reorder),
                "maximum_stock": Decimal(maximum),
                "expected_version": None,
            },
            actor=storekeeper,
            audit_context=audit_context,
        )
        created += 1
    return created


def _seed_work_order_requirements(
    service,
    *,
    parts: dict[str, dict[str, Any]],
    main_location: dict[str, Any],
    engineer: CurrentUser,
    audit_context: AuditContext,
    session_factory: sessionmaker[Session],
) -> dict[str, int]:
    with session_factory() as session:
        rows = session.execute(
            select(WorkOrder, Asset)
            .join(Asset, Asset.asset_id == WorkOrder.asset_id)
            .where(WorkOrder.status.in_(["planned", "assigned", "in_progress", "on_hold"]))
            .order_by(WorkOrder.due_date, WorkOrder.work_order_number)
        ).all()
    created_requirements = 0
    created_reservations = 0
    skipped = 0
    seeded_types: set[str] = set()
    for work_order, asset in rows:
        if asset.asset_type in seeded_types:
            continue
        part_number = WORK_ORDER_PART_BY_ASSET_TYPE.get(asset.asset_type)
        if not part_number or part_number not in parts:
            skipped += 1
            continue
        summary = service.work_order_parts(work_order.id, actor=engineer)
        requirement = next(
            (
                item
                for item in summary["requirements"]
                if item["part_id"] == str(parts[part_number]["id"])
                and item["source_stock_location_id"] == str(main_location["id"])
            ),
            None,
        )
        if requirement is None:
            requirement = service.create_requirement(
                work_order.id,
                {
                    "part_id": parts[part_number]["id"],
                    "planned_quantity": Decimal("2"),
                    "required_by_date": work_order.due_date,
                    "source_stock_location_id": main_location["id"],
                    "notes": "Requirement development demo; không tự động issue.",
                },
                actor=engineer,
                audit_context=audit_context,
            )
            created_requirements += 1
            summary = service.work_order_parts(work_order.id, actor=engineer)
        existing_reservation = next(
            (
                item
                for item in summary["reservations"]
                if item["requirement_id"] == requirement["id"]
            ),
            None,
        )
        if existing_reservation is None:
            service.reserve_stock(
                UUID(str(requirement["id"])),
                {
                    "quantity": Decimal("2"),
                    "expires_at": None,
                    "reason": "Giữ vật tư cho work order development demo",
                    "expected_requirement_version": int(requirement["version"]),
                },
                idempotency_key=(
                    f"pm6-seed-reserve-{work_order.work_order_number.lower()}-{part_number.lower()}"
                ),
                actor=engineer,
                audit_context=audit_context,
            )
            created_reservations += 1
        seeded_types.add(asset.asset_type)
        if len(seeded_types) >= len(WORK_ORDER_PART_BY_ASSET_TYPE):
            break
    if not rows:
        skipped = 1
    return {
        "created_requirements": created_requirements,
        "created_reservations": created_reservations,
        "work_orders_skipped": skipped,
    }


def _audit(actor: CurrentUser, request_id: str) -> AuditContext:
    return AuditContext(
        actor_user_id=actor.id,
        actor_display_name=actor.display_name,
        request_id=request_id,
    )


if __name__ == "__main__":
    main()
