"""Load generated maintenance CSV datasets into the structured database."""

import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy import delete
from sqlalchemy.orm import Session

from src.data_generation.generate_data import DATASET_FILENAMES
from src.database.models import (
    Asset,
    Document,
    MaintenanceLog,
    MaintenanceTicket,
    RiskScore,
    SensorReading,
)
from src.database.session import build_engine
from src.ingestion.validation import validate_csv_dataset

LOAD_ORDER = [
    ("assets", Asset),
    ("sensor_readings", SensorReading),
    ("maintenance_tickets", MaintenanceTicket),
    ("maintenance_logs", MaintenanceLog),
    ("risk_scores", RiskScore),
    ("documents", Document),
]

DATE_COLUMNS = {
    "assets": ["installation_date", "last_maintenance_date"],
    "maintenance_logs": ["maintenance_date", "next_maintenance_date"],
    "risk_scores": ["score_date"],
}

DATETIME_COLUMNS = {
    "sensor_readings": ["timestamp"],
    "maintenance_tickets": ["created_at", "resolved_at"],
    "documents": ["created_at"],
}


def load_csv_dataset(
    input_dir: Path = Path("data/raw"),
    database_url: str | None = None,
    replace: bool = False,
) -> dict[str, int]:
    """Load generated CSV files into database tables."""

    validate_csv_dataset(input_dir)
    engine = build_engine(database_url)
    counts: dict[str, int] = {}

    with Session(engine) as session:
        if replace:
            for _, model in reversed(LOAD_ORDER):
                session.execute(delete(model))
            session.commit()

        for dataset_name, model in LOAD_ORDER:
            csv_path = input_dir / DATASET_FILENAMES[dataset_name]
            if not csv_path.exists():
                raise FileNotFoundError(f"Missing generated dataset: {csv_path}")

            frame = _read_dataset_frame(csv_path=csv_path, dataset_name=dataset_name)
            records = _frame_to_records(frame)
            if records:
                session.execute(model.__table__.insert(), records)
            counts[dataset_name] = len(records)

        session.commit()

    return counts


def _read_dataset_frame(csv_path: Path, dataset_name: str) -> pd.DataFrame:
    frame = pd.read_csv(csv_path, keep_default_na=False)

    for column in DATE_COLUMNS.get(dataset_name, []):
        frame[column] = pd.to_datetime(frame[column], errors="raise").dt.date

    for column in DATETIME_COLUMNS.get(dataset_name, []):
        parsed = pd.to_datetime(frame[column], errors="coerce", utc=True)
        frame[column] = [
            value.to_pydatetime() if not pd.isna(value) else None for value in parsed
        ]

    return frame


def _frame_to_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for record in frame.to_dict(orient="records"):
        records.append({key: _clean_value(value) for key, value in record.items()})
    return records


def _clean_value(value: object) -> object:
    if pd.isna(value):
        return None
    return value


def main() -> None:
    """Run CSV ingestion from the command line."""

    parser = argparse.ArgumentParser(description="Load generated maintenance CSVs into the database.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--database-url", default=None, help="Override DATABASE_URL from the environment.")
    parser.add_argument("--replace", action="store_true", help="Delete existing table data before loading.")
    args = parser.parse_args()

    counts = load_csv_dataset(
        input_dir=args.input_dir,
        database_url=args.database_url,
        replace=args.replace,
    )
    for name, count in counts.items():
        print(f"Loaded {count:>7} rows into {name}")


if __name__ == "__main__":
    main()
