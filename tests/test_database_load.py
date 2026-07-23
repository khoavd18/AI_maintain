"""Tests for canonical migrations, PostgreSQL seed import, and analytics export."""

import csv
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from src.database.export_snapshot import export_analytics_snapshot
from src.database.migrations import downgrade_database, upgrade_database
from src.database.models import (
    Asset,
    AssetAttachment,
    ChecklistTemplate,
    ChecklistTemplateItem,
    InventoryAttachment,
    InventoryMovement,
    InventoryPosition,
    Location,
    MaintenanceLog,
    PartReorderConfiguration,
    PreventiveMaintenancePlan,
    SparePart,
    StockReservation,
    Ticket,
    WorkOrder,
    WorkOrderAttachment,
    WorkOrderChecklistItem,
    BusinessCalendar,
    SlaPolicy,
    TicketComment,
    TicketEscalationEvent,
    TicketSlaState,
)
from src.database.session import Base, build_engine
from src.ingestion.load_data import NonEmptyDatabaseError, import_csv_dataset
from src.database.session import get_session_factory
from src.repositories.postgres import PostgresMaintenanceRepository


def test_canonical_metadata_contains_transactional_and_security_tables() -> None:
    assert set(Base.metadata.tables) == {
        "assets",
        "maintenance_tickets",
        "maintenance_logs",
        "users",
        "refresh_sessions",
        "audit_logs",
        "locations",
        "asset_attachments",
        "checklist_templates",
        "checklist_template_items",
        "preventive_maintenance_plans",
        "work_orders",
        "work_order_checklist_items",
        "work_order_attachments",
        "ticket_categories",
        "ticket_subcategories",
        "ticket_intake_sources",
        "support_groups",
        "business_calendars",
        "business_working_periods",
        "business_calendar_holidays",
        "sla_policies",
        "sla_policy_targets",
        "ticket_sla_states",
        "ticket_sla_events",
        "ticket_comments",
        "ticket_comment_attachments",
        "ticket_escalation_events",
        "part_categories",
        "units_of_measure",
        "spare_parts",
        "stock_locations",
        "inventory_positions",
        "part_reorder_configurations",
        "inventory_operations",
        "inventory_movements",
        "work_order_part_requirements",
        "stock_reservations",
        "stock_reservation_events",
        "work_order_part_issues",
        "work_order_part_consumptions",
        "work_order_part_returns",
        "inventory_attachments",
    }
    assert "version" in Asset.__table__.columns
    assert "version" in Ticket.__table__.columns
    assert "version" not in MaintenanceLog.__table__.columns
    assert "location_id" in Asset.__table__.columns
    assert "operational_status" in Asset.__table__.columns
    assert "storage_key" in AssetAttachment.__table__.columns
    assert "work_order_id" in MaintenanceLog.__table__.columns
    assert "version" in PreventiveMaintenancePlan.__table__.columns
    assert "version" in ChecklistTemplate.__table__.columns
    assert "template_id" in ChecklistTemplateItem.__table__.columns
    assert "version" in WorkOrder.__table__.columns
    assert "result_status" in WorkOrderChecklistItem.__table__.columns
    assert "storage_key" in WorkOrderAttachment.__table__.columns
    assert "timezone" in BusinessCalendar.__table__.columns
    assert "pause_on_waiting" in SlaPolicy.__table__.columns
    assert "occurrence_number" in TicketSlaState.__table__.columns
    assert "visibility" in TicketComment.__table__.columns
    assert "rule_code" in TicketEscalationEvent.__table__.columns
    assert "version" in SparePart.__table__.columns
    assert "reserved_quantity" in InventoryPosition.__table__.columns
    assert "movement_type" in InventoryMovement.__table__.columns
    assert "version" in PartReorderConfiguration.__table__.columns
    assert "occurrence_number" in StockReservation.__table__.columns
    assert "storage_key" in InventoryAttachment.__table__.columns


@pytest.mark.postgres
def test_clean_migration_upgrade_and_downgrade(postgres_database_url: str) -> None:
    downgrade_database(postgres_database_url, "base")
    engine = build_engine(postgres_database_url)
    try:
        assert not {
            "assets",
            "maintenance_tickets",
            "maintenance_logs",
        } & set(inspect(engine).get_table_names())

        upgrade_database(postgres_database_url, "head")
        tables = set(inspect(engine).get_table_names())
        assert {
            "alembic_version",
            "assets",
            "maintenance_tickets",
            "maintenance_logs",
            "users",
            "refresh_sessions",
            "audit_logs",
            "locations",
            "asset_attachments",
            "checklist_templates",
            "checklist_template_items",
            "preventive_maintenance_plans",
            "work_orders",
            "work_order_checklist_items",
            "work_order_attachments",
            "ticket_categories",
            "ticket_subcategories",
            "ticket_intake_sources",
            "support_groups",
            "business_calendars",
            "business_working_periods",
            "business_calendar_holidays",
            "sla_policies",
            "sla_policy_targets",
            "ticket_sla_states",
            "ticket_sla_events",
            "ticket_comments",
            "ticket_comment_attachments",
            "ticket_escalation_events",
            "part_categories",
            "units_of_measure",
            "spare_parts",
            "stock_locations",
            "inventory_positions",
            "part_reorder_configurations",
            "inventory_operations",
            "inventory_movements",
            "work_order_part_requirements",
            "stock_reservations",
            "stock_reservation_events",
            "work_order_part_issues",
            "work_order_part_consumptions",
            "work_order_part_returns",
            "inventory_attachments",
        }.issubset(tables)
    finally:
        upgrade_database(postgres_database_url, "head")
        engine.dispose()


@pytest.mark.postgres
def test_seed_import_is_dry_runnable_idempotent_and_counted(
    clean_postgres_database: str,
) -> None:
    dry_run = import_csv_dataset(
        database_url=clean_postgres_database,
        dry_run=True,
    )
    assert dry_run.counts == {
        "assets": 27,
        "maintenance_tickets": 42,
        "maintenance_logs": 86,
    }
    assert dry_run.existing_counts == {
        "assets": 0,
        "maintenance_tickets": 0,
        "maintenance_logs": 0,
    }

    imported = import_csv_dataset(database_url=clean_postgres_database)
    assert imported.counts == dry_run.counts

    engine = build_engine(clean_postgres_database)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 27
        assert session.scalar(select(func.count()).select_from(Ticket)) == 42
        assert session.scalar(select(func.count()).select_from(MaintenanceLog)) == 86
        assert session.scalar(select(func.count()).select_from(Location)) == 7
        generator = session.get(Asset, "GENERATOR_002")
        assert generator is not None
        assert generator.asset_type == "generator"
        assert generator.criticality == "critical"
        assert generator.lifecycle_status == "active"
        assert generator.location_id is not None
        assert generator.qr_token is not None

    with pytest.raises(NonEmptyDatabaseError, match="not empty"):
        import_csv_dataset(database_url=clean_postgres_database)

    repository = PostgresMaintenanceRepository(
        get_session_factory(clean_postgres_database)
    )
    created = repository.create_ticket(
        {
            "asset_id": "GENERATOR_002",
            "issue_description": "Kiểm tra sequence sau CSV import.",
            "priority": "Cao",
            "status": "Mới tạo",
            "failure_category": "Lỗi điện",
            "created_at": "2026-07-18T08:00:00+00:00",
            "resolved_at": None,
            "technician_id": "TECH_001",
            "manager_note": None,
            "note": None,
        }
    )
    assert created.values["ticket_id"] == "TCK-000043"

    replaced = import_csv_dataset(
        database_url=clean_postgres_database,
        replace=True,
    )
    assert replaced.replaced is True
    assert replaced.counts == dry_run.counts
    engine.dispose()


@pytest.mark.postgres
def test_postgres_snapshot_satisfies_existing_batch_contract(
    clean_postgres_database: str,
    tmp_path: Path,
) -> None:
    import_csv_dataset(database_url=clean_postgres_database)
    output_dir = tmp_path / "analytics_input"

    counts = export_analytics_snapshot(
        output_dir=output_dir,
        database_url=clean_postgres_database,
    )

    assert counts["assets"] == 27
    assert counts["maintenance_tickets"] == 42
    assert counts["maintenance_logs"] == 86
    assert counts["sensor_readings"] == 77_760
    assert (output_dir / "documents.csv").exists()
    with (output_dir / "assets.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == [
        "asset_id",
        "asset_name",
        "asset_type",
        "location",
        "criticality",
        "status",
        "installation_date",
        "last_maintenance_date",
        "maintenance_interval_days",
        "next_maintenance_date",
    ]
    generator = next(row for row in rows if row["asset_id"] == "GENERATOR_002")
    assert generator["asset_type"] == "Máy phát điện dự phòng"
    assert generator["criticality"] == "Rất quan trọng"
    assert generator["status"] == "Cảnh báo"


@pytest.mark.postgres
def test_snapshot_projects_plan_due_date_to_legacy_interval_contract(
    clean_postgres_database: str,
    tmp_path: Path,
) -> None:
    import_csv_dataset(database_url=clean_postgres_database)
    engine = build_engine(clean_postgres_database)
    with Session(engine) as session, session.begin():
        asset = session.get(Asset, "GENERATOR_002")
        assert asset is not None
        latest_log = session.scalars(
            select(MaintenanceLog)
            .where(MaintenanceLog.asset_id == asset.asset_id)
            .order_by(
                MaintenanceLog.maintenance_date.desc(),
                MaintenanceLog.log_id.desc(),
            )
        ).first()
        assert latest_log is not None
        plan_due_date = latest_log.maintenance_date + timedelta(days=7)
        asset.next_maintenance_date = plan_due_date
        latest_log.next_maintenance_date = plan_due_date
        latest_log_id = latest_log.log_id
        last_maintenance_date = asset.last_maintenance_date
        interval_days = asset.maintenance_interval_days

    output_dir = tmp_path / "analytics_input"
    export_analytics_snapshot(
        output_dir=output_dir,
        database_url=clean_postgres_database,
    )

    with (output_dir / "assets.csv").open(encoding="utf-8", newline="") as handle:
        exported_assets = list(csv.DictReader(handle))
    with (output_dir / "maintenance_logs.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        exported_logs = list(csv.DictReader(handle))

    expected_next = (last_maintenance_date + timedelta(days=interval_days)).isoformat()
    generator = next(
        row for row in exported_assets if row["asset_id"] == "GENERATOR_002"
    )
    exported_latest_log = next(
        row for row in exported_logs if row["log_id"] == latest_log_id
    )
    assert generator["next_maintenance_date"] == expected_next
    assert exported_latest_log["next_maintenance_date"] == expected_next

    with Session(engine) as session:
        persisted_asset = session.get(Asset, "GENERATOR_002")
        assert persisted_asset is not None
        assert persisted_asset.next_maintenance_date == plan_due_date
    engine.dispose()
