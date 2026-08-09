"""Model metadata characterization tests used before any model split."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import inspect

from src.database import models
from src.database.metadata_snapshot import metadata_fingerprint, snapshot_metadata
from src.database.session import Base


def test_metadata_snapshot_is_complete_and_deterministic() -> None:
    first = snapshot_metadata()
    second = snapshot_metadata()

    assert first == second
    assert metadata_fingerprint(first) == metadata_fingerprint(second)
    assert len(first["tables"]) >= 40
    assert all(
        table["columns"]
        and table["primary_key"]
        and "foreign_keys" in table
        and "unique_constraints" in table
        and "check_constraints" in table
        and "indexes" in table
        for table in first["tables"]
    )


def test_metadata_snapshot_contains_transactional_table_families() -> None:
    tables = {table["name"] for table in snapshot_metadata()["tables"]}

    assert {"assets", "maintenance_tickets", "work_orders"} <= tables
    assert {"inventory_positions", "inventory_movements", "stock_reservations"} <= tables
    assert {"scheduled_jobs", "outbox_events", "notifications"} <= tables


def test_metadata_matches_committed_baseline_snapshot() -> None:
    baseline_path = Path(__file__).parents[1] / "docs" / "metadata-snapshot.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    assert snapshot_metadata() == baseline


def test_model_package_reexports_every_mapped_class_without_duplicate_tables() -> None:
    mapped_names = [
        name
        for name in models.__all__
        if name not in {"Base", "MaintenanceTicket", "_asset_qr_token", "_utc_now"}
    ]

    assert len(mapped_names) == len({getattr(models, name) for name in mapped_names})
    assert len(Base.metadata.tables) == len({table.name for table in Base.metadata.tables.values()})
    for name in mapped_names:
        mapped_class = getattr(models, name)
        assert inspect(mapped_class).local_table in Base.metadata.tables.values()
