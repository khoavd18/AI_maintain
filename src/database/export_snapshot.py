"""Export a validated PostgreSQL snapshot for the existing batch analytics contract."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from src.database.session import get_session_factory
from src.ingestion.validation import validate_csv_dataset
from src.repositories.postgres import PostgresMaintenanceRepository

TRANSACTIONAL_FILES = {
    "assets": "assets.csv",
    "maintenance_tickets": "maintenance_tickets.csv",
    "maintenance_logs": "maintenance_logs.csv",
}
PASS_THROUGH_FILES = ("sensor_readings.csv", "documents.csv")


def export_analytics_snapshot(
    *,
    output_dir: Path = Path("data/analytics_input"),
    source_dir: Path = Path("data/raw"),
    database_url: str | None = None,
    replace: bool = False,
) -> dict[str, int]:
    """Export DB transactions plus immutable batch files as one validated directory."""

    repository = PostgresMaintenanceRepository(get_session_factory(database_url))
    repository.check_health()
    snapshot = repository.snapshot()

    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists() and not replace:
        raise FileExistsError(
            f"Snapshot directory already exists: {output_dir}. Use --replace explicitly."
        )
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    try:
        transactional_frames = {
            dataset_name: pd.DataFrame(
                [record.values for record in snapshot[dataset_name]]
            )
            for dataset_name in TRANSACTIONAL_FILES
        }
        _project_legacy_maintenance_dates(transactional_frames)
        for dataset_name, filename in TRANSACTIONAL_FILES.items():
            transactional_frames[dataset_name].to_csv(staging / filename, index=False)
        for filename in PASS_THROUGH_FILES:
            source = source_dir / filename
            if not source.exists():
                raise FileNotFoundError(f"Missing batch source required for snapshot: {source}")
            shutil.copy2(source, staging / filename)
        validated = validate_csv_dataset(staging)
        _replace_directory(staging, output_dir, replace=replace)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise                  

    return {name: len(frame) for name, frame in validated.items()}


def _project_legacy_maintenance_dates(frames: dict[str, pd.DataFrame]) -> None:
    """Keep plan dates in PostgreSQL while satisfying the unchanged batch contract."""

    assets = frames["assets"]
    logs = frames["maintenance_logs"]
    intervals = assets.set_index("asset_id")["maintenance_interval_days"].astype(int)

    asset_last_dates = pd.to_datetime(assets["last_maintenance_date"], errors="raise")
    assets["next_maintenance_date"] = (
        asset_last_dates
        + pd.to_timedelta(assets["maintenance_interval_days"].astype(int), unit="D")
    ).dt.strftime("%Y-%m-%d")

    log_dates = pd.to_datetime(logs["maintenance_date"], errors="raise")
    log_intervals = logs["asset_id"].map(intervals)
    if log_intervals.isna().any():
        unknown_asset = logs.loc[log_intervals.isna(), "asset_id"].iloc[0]
        raise ValueError(f"Maintenance log references unknown asset: {unknown_asset}")
    logs["next_maintenance_date"] = (
        log_dates + pd.to_timedelta(log_intervals.astype(int), unit="D")
    ).dt.strftime("%Y-%m-%d")


def _replace_directory(staging: Path, target: Path, *, replace: bool) -> None:
    backup: Path | None = None
    if target.exists():
        if not replace:
            raise FileExistsError(f"Snapshot directory already exists: {target}")
        backup = target.with_name(f".{target.name}.backup")
        if backup.exists():
            shutil.rmtree(backup)
        os.replace(target, backup)
    try:
        os.replace(staging, target)
    except Exception:
        if backup is not None and backup.exists():
            os.replace(backup, target)
        raise
    else:
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export PostgreSQL transactional data for the CSV batch pipeline."
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/analytics_input"))
    parser.add_argument("--source-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    counts = export_analytics_snapshot(
        output_dir=args.output_dir,
        source_dir=args.source_dir,
        database_url=args.database_url,
        replace=args.replace,
    )
    for name, count in counts.items():
        print(f"Snapshot {count:>7} rows: {name}")


if __name__ == "__main__":
    main()
