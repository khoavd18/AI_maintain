"""Tests for database schema creation and CSV ingestion."""

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.data_generation.generate_data import generate_dataset, save_dataset
from src.database.init_db import init_database
from src.database.models import (
    Asset,
    Document,
    MaintenanceLog,
    MaintenanceTicket,
    SensorReading,
)
from src.database.session import build_engine
from src.ingestion.load_data import load_csv_dataset


def test_database_insertion_works(tmp_path: Path) -> None:
    """Generated CSV files should load into the SQLAlchemy schema."""

    dataset = generate_dataset(asset_count=12, days=3, seed=7)
    save_dataset(dataset, tmp_path)

    database_url = f"sqlite:///{tmp_path / 'maintenance.db'}"
    init_database(database_url=database_url, drop_existing=True)
    counts = load_csv_dataset(input_dir=tmp_path, database_url=database_url)

    assert counts["assets"] == 12
    assert counts["sensor_readings"] == 12 * 3 * 24
    assert counts["maintenance_tickets"] == len(dataset["maintenance_tickets"])
    assert counts["maintenance_logs"] == len(dataset["maintenance_logs"])
    assert counts["documents"] == 6

    engine = build_engine(database_url)
    with Session(engine) as session:
        asset_count = session.scalar(select(func.count()).select_from(Asset))
        reading_count = session.scalar(select(func.count()).select_from(SensorReading))
        ticket_count = session.scalar(select(func.count()).select_from(MaintenanceTicket))
        log_count = session.scalar(select(func.count()).select_from(MaintenanceLog))
        document_count = session.scalar(select(func.count()).select_from(Document))

    assert asset_count == counts["assets"]
    assert reading_count == counts["sensor_readings"]
    assert ticket_count == counts["maintenance_tickets"]
    assert log_count == counts["maintenance_logs"]
    assert document_count == counts["documents"]
