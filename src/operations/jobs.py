"""Adapters from the closed PM7 job catalog to existing domain services."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from src.config.settings import Settings
from src.database.export_snapshot import export_analytics_snapshot
from src.features.build_features import (
    build_features_from_csv,
    build_maintenance_analytics_from_csv,
)
from src.inventory_management.service import build_inventory_management_service
from src.maintenance_management.service import build_maintenance_planning_service
from src.models.anomaly_detection import run_anomaly_detection
from src.operations.domain import JobType
from src.repositories.contracts import OperationsRepository
from src.risk.risk_scoring import run_risk_scoring
from src.security.audit import AuditContext
from src.security.principal import CurrentUser
from src.ticket_management.service import build_ticket_workflow_service

PROCESSED_FILENAMES = (
    "asset_daily_features.csv",
    "anomaly_results.csv",
    "risk_scores.csv",
    "preventive_maintenance_status.csv",
    "recurring_issues.csv",
    "maintenance_kpis.csv",
)


class JobRunner:
    """Execute only supported jobs through their canonical service boundaries."""

    def __init__(
        self,
        *,
        settings: Settings,
        operations_repository: OperationsRepository,
    ) -> None:
        self.settings = settings
        self.operations_repository = operations_repository

    def run(
        self,
        execution: dict[str, Any],
        *,
        actor: CurrentUser,
    ) -> dict[str, Any]:
        job_type = JobType(str(execution["job_type"]))
        context = AuditContext(
            actor_user_id=actor.id,
            actor_display_name=actor.display_name,
            request_id=str(execution["correlation_id"]),
        )
        if job_type is JobType.PREVENTIVE_GENERATION:
            return self._preventive_generation(actor=actor, audit_context=context)
        if job_type is JobType.SLA_ESCALATION:
            return self._sla_escalation(actor=actor, audit_context=context)
        if job_type is JobType.ANALYTICS_REFRESH:
            return self._analytics_refresh()
        if job_type is JobType.INVENTORY_REORDER_DETECTION:
            return self._inventory_reorder_detection(
                execution_id=UUID(str(execution["id"])),
                actor=actor,
            )
        raise ValueError(f"Unsupported background job: {job_type}")

    @staticmethod
    def _preventive_generation(
        *, actor: CurrentUser, audit_context: AuditContext
    ) -> dict[str, Any]:
        as_of = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        report = build_maintenance_planning_service().generate(
            as_of_date=as_of,
            plan_id=None,
            dry_run=False,
            actor=actor,
            audit_context=audit_context,
        )
        return {
            "as_of_date": report["as_of_date"],
            "generated_count": int(report["generated_count"]),
            "skipped_count": int(report["skipped_count"]),
            "plan_count": len(report["plans"]),
        }

    @staticmethod
    def _sla_escalation(
        *, actor: CurrentUser, audit_context: AuditContext
    ) -> dict[str, Any]:
        report = build_ticket_workflow_service().evaluate_escalations(
            dry_run=False,
            actor=actor,
            audit_context=audit_context,
            as_of=datetime.now(timezone.utc),
        )
        return {
            "as_of": report["as_of"],
            "candidate_count": int(report["candidate_count"]),
            "created_count": int(report["created_count"]),
        }

    def _analytics_refresh(self) -> dict[str, Any]:
        source_dir = Path(self.settings.analytics_source_dir).resolve()
        target_dir = Path(self.settings.analytics_processed_dir).resolve()
        _validate_publication_paths(source_dir=source_dir, target_dir=target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(
            tempfile.mkdtemp(
                prefix=f".{target_dir.name}.refresh-",
                dir=target_dir.parent,
            )
        )
        snapshot_dir = staging_root / "analytics_input"
        processed_dir = staging_root / "processed"
        try:
            input_counts = export_analytics_snapshot(
                output_dir=snapshot_dir,
                source_dir=source_dir,
                database_url=self.settings.database_url,
                replace=False,
            )
            feature_path = processed_dir / "asset_daily_features.csv"
            anomaly_path = processed_dir / "anomaly_results.csv"
            risk_path = processed_dir / "risk_scores.csv"
            features = build_features_from_csv(
                input_dir=snapshot_dir,
                output_path=feature_path,
            )
            anomalies = run_anomaly_detection(
                input_path=feature_path,
                output_path=anomaly_path,
            )
            risks = run_risk_scoring(
                feature_path=feature_path,
                anomaly_path=anomaly_path,
                output_path=risk_path,
            )
            maintenance_outputs = build_maintenance_analytics_from_csv(
                input_dir=snapshot_dir,
                risk_path=risk_path,
                processed_dir=processed_dir,
            )
            missing = [
                filename
                for filename in PROCESSED_FILENAMES
                if not (processed_dir / filename).is_file()
            ]
            if missing:
                raise RuntimeError(
                    f"Analytics staging is missing expected outputs: {missing}"
                )
            sensor_readings = pd.read_csv(snapshot_dir / "sensor_readings.csv")
            timestamps = pd.to_datetime(sensor_readings["timestamp"], utc=True)
            output_counts = {
                "asset_daily_features": len(features),
                "anomaly_results": len(anomalies),
                "risk_scores": len(risks),
                **{
                    name: len(frame)
                    for name, frame in maintenance_outputs.items()
                },
            }
            _atomic_publish_directory(processed_dir, target_dir)
            return {
                "input_counts": input_counts,
                "input_time_from": timestamps.min().isoformat(),
                "input_time_to": timestamps.max().isoformat(),
                "output_counts": output_counts,
            }
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)

    def _inventory_reorder_detection(
        self,
        *,
        execution_id: UUID,
        actor: CurrentUser,
    ) -> dict[str, Any]:
        balances = build_inventory_management_service().list_balances(
            actor=actor,
            filters={},
            sort_by="part_number",
            sort_direction="asc",
            page=1,
            page_size=100_000,
        )["items"]
        observed_keys = {
            f"{item['part_id']}:{item['stock_location_id']}" for item in balances
        }
        low_items = [
            item
            for item in balances
            if item["stock_state"]
            in {"out_of_stock", "low_stock", "at_reorder_point"}
        ]
        return self.operations_repository.record_low_stock_cycles(
            low_stock_items=low_items,
            observed_entity_keys=observed_keys,
            execution_id=execution_id,
        )


def _validate_publication_paths(*, source_dir: Path, target_dir: Path) -> None:
    cwd = Path.cwd().resolve()
    if target_dir.parent == target_dir or target_dir == cwd:
        raise ValueError("ANALYTICS_PROCESSED_DIR cannot be a filesystem or repository root.")
    if target_dir == source_dir or target_dir in source_dir.parents:
        raise ValueError(
            "ANALYTICS_PROCESSED_DIR must be separate from ANALYTICS_SOURCE_DIR."
        )


def _atomic_publish_directory(staging: Path, target: Path) -> None:
    """Replace the complete output set and restore the last valid set on failure."""

    backup: Path | None = None
    if target.exists():
        backup = target.with_name(f".{target.name}.backup-{uuid4().hex}")
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
