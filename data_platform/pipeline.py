"""Incremental extraction, raw loading, audit, and reconciliation commands."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from data_platform.config import DataPlatformSettings
from data_platform.database import check_database, connect
from data_platform.object_store import build_object_store, checksum


LOGGER = logging.getLogger("data_platform.pipeline")
UTC = timezone.utc
PIPELINE_NAME = "work_orders_incremental"
DAG_ID = "maintenance_scale_pipeline"
ZERO_UUID = UUID(int=0)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

RAW_COLUMNS = [
    "ingestion_batch_id",
    "work_order_id",
    "work_order_number",
    "site_id",
    "asset_id",
    "assigned_technician_id",
    "work_order_type",
    "priority",
    "status",
    "title",
    "description",
    "created_at",
    "scheduled_start_at",
    "started_at",
    "completed_at",
    "due_date",
    "estimated_duration_minutes",
    "labor_minutes",
    "resolution_note",
    "estimated_cost",
    "actual_cost",
    "source_updated_at",
    "source_extracted_at",
    "source_system",
]

_EXTRACT_QUERY = """
    SELECT
        %s::uuid AS ingestion_batch_id,
        work_order_id,
        work_order_number,
        site_id,
        asset_id,
        assigned_technician_id,
        work_order_type,
        priority,
        status,
        title,
        description,
        created_at,
        scheduled_start_at,
        started_at,
        completed_at,
        due_date,
        estimated_duration_minutes,
        labor_minutes,
        resolution_note,
        estimated_cost,
        actual_cost,
        updated_at AS source_updated_at,
        %s::timestamptz AS source_extracted_at,
        'ai_maintenance_copilot'::text AS source_system
    FROM analytics_source.work_orders
    WHERE (updated_at, work_order_id) > (%s::timestamptz, %s::uuid)
    ORDER BY updated_at, work_order_id
"""


def _sanitize(value: str | None, limit: int = 1_000) -> str:
    message = "" if value is None else " ".join(value.split())
    message = re.sub(
        r"(?i)(password|passwd|pwd)\s*[=:]\s*[^,;\s]+",
        r"\1=<redacted>",
        message,
    )
    message = re.sub(
        r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:\s]+:)[^@\s]+@",
        r"\1<redacted>@",
        message,
    )
    return message[:limit]


def _watermark(connection) -> tuple[datetime, UUID]:
    row = connection.execute(
        """
        SELECT updated_at, work_order_id
        FROM audit.pipeline_watermarks
        WHERE pipeline_name = %s
        """,
        (PIPELINE_NAME,),
    ).fetchone()
    if row is None:
        return EPOCH, ZERO_UUID
    return row[0], row[1]


def check_source(settings: DataPlatformSettings | None = None) -> dict[str, Any]:
    resolved = settings or DataPlatformSettings.from_env()
    evidence = check_database(resolved)
    with connect(resolved, read_only=True) as connection:
        row = connection.execute(
            """
            SELECT
                to_regclass('analytics_source.work_orders') IS NOT NULL,
                to_regclass('raw.work_orders') IS NOT NULL,
                to_regclass('audit.pipeline_watermarks') IS NOT NULL,
                count(*)
            FROM analytics_source.work_orders
            """
        ).fetchone()
    if row is None or not all(row[:3]):
        raise RuntimeError("Data Platform source contract or raw/audit schema is missing.")
    return {**evidence, "source_work_orders": int(row[3])}


def snapshot_dimensions(
    run_id: str,
    settings: DataPlatformSettings | None = None,
) -> dict[str, Any]:
    """Create retry-safe SCD1-style raw snapshots with set-based SQL."""

    resolved = settings or DataPlatformSettings.from_env()
    batch_id = uuid5(NAMESPACE_URL, f"stage9-dimensions:{run_id}")
    extracted_at = datetime.now(UTC)
    statements = {
        "sites": """
            INSERT INTO raw.sites (
                ingestion_batch_id, site_id, site_code, site_name, location_type,
                parent_site_id, is_active, source_created_at, source_updated_at,
                source_extracted_at
            )
            SELECT %s, site_id, site_code, site_name, location_type, parent_site_id,
                   is_active, created_at, updated_at, %s
            FROM analytics_source.sites
            ON CONFLICT (ingestion_batch_id, site_id) DO NOTHING
        """,
        "assets": """
            INSERT INTO raw.assets (
                ingestion_batch_id, asset_id, asset_name, site_id, manufacturer, model,
                asset_type, criticality, lifecycle_status, operational_status, installed_at,
                source_created_at, source_updated_at, source_extracted_at
            )
            SELECT %s, asset_id, asset_name, site_id, manufacturer, model, asset_type,
                   criticality, lifecycle_status, operational_status, installed_at,
                   created_at, updated_at, %s
            FROM analytics_source.assets
            ON CONFLICT (ingestion_batch_id, asset_id) DO NOTHING
        """,
        "technicians": """
            INSERT INTO raw.technicians (
                ingestion_batch_id, technician_id, employee_code, display_name, role,
                is_active, source_created_at, source_updated_at, source_extracted_at
            )
            SELECT %s, technician_id, employee_code, display_name, role, is_active,
                   created_at, updated_at, %s
            FROM analytics_source.technicians
            ON CONFLICT (ingestion_batch_id, technician_id) DO NOTHING
        """,
    }
    counts: dict[str, int] = {}
    with connect(resolved) as connection:
        for entity, statement in statements.items():
            cursor = connection.execute(statement, (batch_id, extracted_at))
            counts[entity] = max(cursor.rowcount, 0)
    return {"batch_id": str(batch_id), "counts": counts}


def _resolve_object_path(
    settings: DataPlatformSettings,
    object_key: str,
    recorded_path: str,
) -> Path:
    if settings.object_store == "local":
        local_path = (settings.data_root / "objects" / object_key).resolve()
        if local_path.exists():
            return local_path
    return Path(recorded_path)


def _existing_extraction(
    connection,
    run_id: str,
    settings: DataPlatformSettings,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT batch_id, status, row_count, object_key, object_path, object_sha256,
               upper_updated_at, upper_work_order_id
        FROM audit.extraction_batches
        WHERE pipeline_name = %s AND run_id = %s
        """,
        (PIPELINE_NAME, run_id),
    ).fetchone()
    if row is None:
        return None
    path = _resolve_object_path(settings, str(row[3]), str(row[4]))
    if not path.exists() or checksum(path) != str(row[5]).strip():
        raise RuntimeError("Retry found an extraction audit row with a missing/changed object.")
    return {
        "batch_id": str(row[0]),
        "status": row[1],
        "row_count": int(row[2]),
        "object_key": row[3],
        "object_path": str(path),
        "sha256": str(row[5]).strip(),
        "upper_watermark": [
            row[6].isoformat() if row[6] else None,
            str(row[7]) if row[7] else None,
        ],
        "reused": True,
    }


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".json.partial")
    partial.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(path)


def _summarize_extraction_object(path: Path) -> tuple[int, str | None, str | None]:
    row_count = 0
    upper_updated_at: str | None = None
    upper_work_order_id: str | None = None
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != RAW_COLUMNS:
            raise RuntimeError("Extraction recovery object has an incompatible header.")
        for row in reader:
            row_count += 1
            upper_updated_at = row["source_updated_at"]
            upper_work_order_id = row["work_order_id"]
    return row_count, upper_updated_at, upper_work_order_id


def _record_published_extraction(
    state: dict[str, Any],
    settings: DataPlatformSettings,
) -> None:
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO audit.extraction_batches (
                batch_id, pipeline_name, run_id, status,
                lower_updated_at, lower_work_order_id,
                upper_updated_at, upper_work_order_id,
                row_count, object_key, object_path, object_sha256,
                source_extracted_at
            ) VALUES (
                %s, %s, %s, 'extracted', %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            ON CONFLICT (pipeline_name, run_id) DO NOTHING
            """,
            (
                state["batch_id"],
                PIPELINE_NAME,
                state["run_id"],
                state["lower_updated_at"],
                state["lower_work_order_id"],
                state.get("upper_updated_at"),
                state.get("upper_work_order_id"),
                state["row_count"],
                state["object_key"],
                state["object_path"],
                state["object_sha256"],
                state["source_extracted_at"],
            ),
        )


def _state_result(state: dict[str, Any], *, reused: bool) -> dict[str, Any]:
    return {
        "batch_id": state["batch_id"],
        "status": "extracted",
        "row_count": int(state["row_count"]),
        "object_key": state["object_key"],
        "object_path": state["object_path"],
        "sha256": state["object_sha256"],
        "lower_watermark": [
            state["lower_updated_at"],
            state["lower_work_order_id"],
        ],
        "upper_watermark": [
            state.get("upper_updated_at"),
            state.get("upper_work_order_id"),
        ],
        "reused": reused,
    }


def extract_work_orders(
    run_id: str,
    settings: DataPlatformSettings | None = None,
) -> dict[str, Any]:
    """Stream rows after the committed tuple watermark into an immutable object."""

    resolved = settings or DataPlatformSettings.from_env()
    batch_id = uuid5(NAMESPACE_URL, f"stage9-work-orders:{run_id}")
    staging_path = resolved.data_root / "pipeline" / "staging" / f"{batch_id}.csv"
    state_path = resolved.data_root / "pipeline" / "state" / f"{batch_id}.json"
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    partial = staging_path.with_suffix(".csv.partial")

    with connect(resolved, read_only=True) as connection:
        existing = _existing_extraction(connection, run_id, resolved)
        if existing is not None:
            return existing
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state.get("status") == "published":
                object_path = _resolve_object_path(
                    resolved,
                    state["object_key"],
                    state["object_path"],
                )
                if not object_path.exists() or checksum(object_path) != state["object_sha256"]:
                    raise RuntimeError("Published extraction recovery state has invalid bytes.")
                state["object_path"] = str(object_path)
                _record_published_extraction(state, resolved)
                return _state_result(state, reused=True)
            extracted_at = datetime.fromisoformat(state["source_extracted_at"])
            lower_updated_at = datetime.fromisoformat(state["lower_updated_at"])
            lower_id = UUID(state["lower_work_order_id"])
            recovery_key = (
                f"raw/work_orders/extract_date={extracted_at.date().isoformat()}/"
                f"batch_id={batch_id}/work_orders_incremental.csv"
            )
            recovery_path = resolved.data_root / "objects" / recovery_key
            if resolved.object_store == "local" and recovery_path.exists():
                recovered_count, recovered_updated_at, recovered_id = _summarize_extraction_object(
                    recovery_path
                )
                state.update(
                    {
                        "status": "published",
                        "row_count": recovered_count,
                        "object_key": recovery_key,
                        "object_path": recovery_key,
                        "object_sha256": checksum(recovery_path),
                        "upper_updated_at": recovered_updated_at,
                        "upper_work_order_id": recovered_id,
                    }
                )
                _write_state(state_path, state)
                _record_published_extraction(state, resolved)
                return _state_result(state, reused=True)
        else:
            extracted_at = datetime.now(UTC)
            lower_updated_at, lower_id = _watermark(connection)
            state = {
                "status": "extracting",
                "batch_id": str(batch_id),
                "run_id": run_id,
                "source_extracted_at": extracted_at.isoformat(),
                "lower_updated_at": lower_updated_at.isoformat(),
                "lower_work_order_id": str(lower_id),
            }
            _write_state(state_path, state)
        row_count = 0
        upper_updated_at: datetime | None = None
        upper_id: UUID | None = None
        with partial.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(RAW_COLUMNS)
            with connection.cursor(name=f"stage9_extract_{batch_id.hex}") as cursor:
                cursor.itersize = resolved.batch_size
                cursor.execute(
                    _EXTRACT_QUERY,
                    (batch_id, extracted_at, lower_updated_at, lower_id),
                )
                while rows := cursor.fetchmany(resolved.batch_size):
                    writer.writerows(rows)
                    row_count += len(rows)
                    upper_updated_at = rows[-1][21]
                    upper_id = rows[-1][1]
                    LOGGER.info("Extracted %d work-order versions", row_count)
    partial.replace(staging_path)
    key = (
        f"raw/work_orders/extract_date={extracted_at.date().isoformat()}/"
        f"batch_id={batch_id}/work_orders_incremental.csv"
    )
    stored = build_object_store(resolved).put(staging_path, key)
    if stored.path.resolve() != staging_path.resolve():
        staging_path.unlink()
    state.update(
        {
            "status": "published",
            "row_count": row_count,
            "object_key": key,
            # Persist the portable object key. Resolution uses the current
            # runtime's data root, whether invoked on Windows or in Airflow.
            "object_path": key if resolved.object_store == "local" else str(stored.path),
            "object_sha256": stored.sha256,
            "upper_updated_at": upper_updated_at.isoformat() if upper_updated_at else None,
            "upper_work_order_id": str(upper_id) if upper_id else None,
        }
    )
    _write_state(state_path, state)
    _record_published_extraction(state, resolved)
    return _state_result(state, reused=False)


def load_raw_batch(
    run_id: str,
    settings: DataPlatformSettings | None = None,
) -> dict[str, Any]:
    """COPY a batch and advance its watermark in the same successful transaction."""

    resolved = settings or DataPlatformSettings.from_env()
    with connect(resolved) as connection:
        batch = connection.execute(
            """
            SELECT batch_id, status, row_count, object_key, object_path, object_sha256,
                   upper_updated_at, upper_work_order_id
            FROM audit.extraction_batches
            WHERE pipeline_name = %s AND run_id = %s
            FOR UPDATE
            """,
            (PIPELINE_NAME, run_id),
        ).fetchone()
        if batch is None:
            raise RuntimeError(f"No extracted batch exists for run_id={run_id!r}.")
        batch_id, status, expected_count = batch[0], batch[1], int(batch[2])
        path = _resolve_object_path(resolved, str(batch[3]), str(batch[4]))
        if status in {"loaded", "empty"}:
            return {
                "batch_id": str(batch_id),
                "status": status,
                "row_count": expected_count,
                "reused": True,
            }
        if not path.exists() or checksum(path) != str(batch[5]).strip():
            raise RuntimeError("Raw load object checksum validation failed.")

        connection.execute(
            "CREATE TEMP TABLE stage9_raw_work_orders "
            "(LIKE raw.work_orders INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        columns_sql = ", ".join(RAW_COLUMNS)
        copy_sql = (
            f"COPY stage9_raw_work_orders ({columns_sql}) "
            "FROM STDIN WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')"
        )
        with path.open("rb") as source, connection.cursor().copy(copy_sql) as copy:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                copy.write(block)
        copied_row = connection.execute("SELECT count(*) FROM stage9_raw_work_orders").fetchone()
        copied = int(copied_row[0]) if copied_row else -1
        if copied != expected_count:
            raise RuntimeError(f"Raw COPY count mismatch: {copied} != {expected_count}.")
        connection.execute(
            """
            INSERT INTO raw.work_orders (
                ingestion_batch_id, work_order_id, work_order_number, site_id, asset_id,
                assigned_technician_id, work_order_type, priority, status, title, description,
                created_at, scheduled_start_at, started_at, completed_at, due_date,
                estimated_duration_minutes, labor_minutes, resolution_note, estimated_cost,
                actual_cost, source_updated_at, source_extracted_at, source_system
            )
            SELECT
                ingestion_batch_id, work_order_id, work_order_number, site_id, asset_id,
                assigned_technician_id, work_order_type, priority, status, title, description,
                created_at, scheduled_start_at, started_at, completed_at, due_date,
                estimated_duration_minutes, labor_minutes, resolution_note, estimated_cost,
                actual_cost, source_updated_at, source_extracted_at, source_system
            FROM stage9_raw_work_orders
            ON CONFLICT (work_order_id, source_updated_at) DO NOTHING
            """
        )
        if expected_count == 0:
            final_status = "empty"
        else:
            upper_updated_at, upper_id = batch[6], batch[7]
            if upper_updated_at is None or upper_id is None:
                raise RuntimeError("Non-empty extraction is missing its upper watermark.")
            connection.execute(
                """
                INSERT INTO audit.pipeline_watermarks (
                    pipeline_name, updated_at, work_order_id, batch_id
                ) VALUES (%s, %s, %s, NULL)
                ON CONFLICT (pipeline_name) DO NOTHING
                """,
                (PIPELINE_NAME, EPOCH, ZERO_UUID),
            )
            current_watermark = connection.execute(
                """
                SELECT updated_at, work_order_id
                FROM audit.pipeline_watermarks
                WHERE pipeline_name = %s
                FOR UPDATE
                """,
                (PIPELINE_NAME,),
            ).fetchone()
            if current_watermark is None:
                raise RuntimeError("Unable to lock the pipeline watermark.")
            should_advance = (upper_updated_at, upper_id) > (
                current_watermark[0],
                current_watermark[1],
            )
            if should_advance:
                connection.execute(
                    """
                    UPDATE audit.pipeline_watermarks
                    SET updated_at = %s, work_order_id = %s, batch_id = %s,
                        version = version + 1, advanced_at = current_timestamp
                    WHERE pipeline_name = %s
                    """,
                    (upper_updated_at, upper_id, batch_id, PIPELINE_NAME),
                )
            final_status = "loaded"
        connection.execute(
            """
            UPDATE audit.extraction_batches
            SET status = %s, loaded_at = current_timestamp, error_message = NULL
            WHERE batch_id = %s
            """,
            (final_status, batch_id),
        )
    return {
        "batch_id": str(batch_id),
        "status": final_status,
        "row_count": expected_count,
        "reused": False,
    }


def _relation_count(connection, relation: str) -> int | None:
    if connection.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0] is None:
        return None
    # Relation names are a closed internal list, never caller input.
    row = connection.execute(f"SELECT count(*) FROM {relation}").fetchone()
    return int(row[0]) if row else None


def reconcile(
    settings: DataPlatformSettings | None = None,
    *,
    expected_count: int | None = None,
    require_transformed: bool = True,
) -> dict[str, Any]:
    resolved = settings or DataPlatformSettings.from_env()
    with connect(resolved, read_only=True) as connection:
        source_count = _relation_count(connection, "analytics_source.work_orders")
        raw_versions = _relation_count(connection, "raw.work_orders")
        row = connection.execute(
            "SELECT count(DISTINCT work_order_id) FROM raw.work_orders"
        ).fetchone()
        raw_unique = int(row[0]) if row else 0
        staging_count = _relation_count(connection, "analytics_staging.stg_work_orders")
        fact_count = _relation_count(connection, "analytics_warehouse.fact_work_order")
        duplicate_sql = "SELECT 0"
        if fact_count is not None:
            duplicate_sql = """
                SELECT count(*) FROM (
                    SELECT work_order_id
                    FROM analytics_warehouse.fact_work_order
                    GROUP BY work_order_id HAVING count(*) > 1
                ) AS duplicates
            """
        duplicate_row = connection.execute(duplicate_sql)
        duplicate_count = int(duplicate_row.fetchone()[0])
    required_counts = [source_count, raw_unique]
    transformed_present = staging_count is not None and fact_count is not None
    if transformed_present:
        required_counts.extend([staging_count, fact_count])
    reconciled = (
        source_count is not None
        and raw_versions is not None
        and (transformed_present or not require_transformed)
        and len(set(required_counts)) == 1
        and duplicate_count == 0
        and (expected_count is None or source_count == expected_count)
    )
    result = {
        "source_work_orders": source_count,
        "raw_versions": raw_versions,
        "raw_unique_work_orders": raw_unique,
        "raw_update_versions": (raw_versions or 0) - raw_unique,
        "staging_work_orders": staging_count,
        "fact_work_orders": fact_count,
        "fact_duplicates": duplicate_count,
        "expected_work_orders": expected_count,
        "transformed_layers_present": transformed_present,
        "reconciled": reconciled,
    }
    if not reconciled:
        raise RuntimeError(f"Pipeline reconciliation failed: {result}")
    return result


def audit_start(run_id: str, settings: DataPlatformSettings | None = None) -> dict[str, str]:
    resolved = settings or DataPlatformSettings.from_env()
    with connect(resolved) as connection:
        connection.execute(
            """
            INSERT INTO audit.pipeline_run_audit (
                dag_id, dag_run_id, run_type, status, started_at
            ) VALUES (%s, %s, 'manual', 'running', current_timestamp)
            ON CONFLICT (dag_id, dag_run_id) DO UPDATE SET
                status = 'running', finished_at = NULL, failed_task_id = NULL,
                error_type = NULL, error_message = NULL, updated_at = current_timestamp
            """,
            (DAG_ID, run_id),
        )
    return {"run_id": run_id, "status": "running"}


def audit_complete(run_id: str, settings: DataPlatformSettings | None = None) -> dict[str, Any]:
    resolved = settings or DataPlatformSettings.from_env()
    counts = reconcile(resolved)
    with connect(resolved) as connection:
        connection.execute(
            """
            UPDATE audit.pipeline_run_audit
            SET status = 'success', finished_at = current_timestamp,
                source_work_order_count = %s, raw_work_order_count = %s,
                staging_work_order_count = %s, fact_work_order_count = %s,
                updated_at = current_timestamp
            WHERE dag_id = %s AND dag_run_id = %s
            """,
            (
                counts["source_work_orders"],
                counts["raw_unique_work_orders"],
                counts["staging_work_orders"],
                counts["fact_work_orders"],
                DAG_ID,
                run_id,
            ),
        )
    return {"run_id": run_id, "status": "success", **counts}


def audit_event(
    *,
    run_id: str,
    task_id: str,
    event_type: str,
    try_number: int = 0,
    error_type: str = "TaskFailure",
    error_message: str = "",
    settings: DataPlatformSettings | None = None,
) -> dict[str, str]:
    if event_type not in {"retry", "failure"}:
        raise ValueError("Unsupported audit event type.")
    resolved = settings or DataPlatformSettings.from_env()
    safe_message = _sanitize(error_message)
    with connect(resolved) as connection:
        connection.execute(
            """
            INSERT INTO audit.pipeline_task_event (
                dag_id, dag_run_id, task_id, event_type, try_number, event_message
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (DAG_ID, run_id, task_id, event_type, try_number, safe_message),
        )
        if event_type == "failure":
            connection.execute(
                """
                UPDATE audit.pipeline_run_audit
                SET status = 'failed', finished_at = current_timestamp,
                    failed_task_id = %s, error_type = %s, error_message = %s,
                    updated_at = current_timestamp
                WHERE dag_id = %s AND dag_run_id = %s
                """,
                (task_id, _sanitize(error_type, 200), safe_message, DAG_ID, run_id),
            )
    return {"run_id": run_id, "task_id": task_id, "event_type": event_type}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("audit-start", "snapshot-dimensions", "extract", "load-raw", "audit-complete"):
        command = subparsers.add_parser(name)
        command.add_argument("--run-id", required=True)
    subparsers.add_parser("check-source")
    reconcile_parser = subparsers.add_parser("reconcile")
    reconcile_parser.add_argument("--run-id", required=False)
    reconcile_parser.add_argument("--expected-count", type=int)
    retry = subparsers.add_parser("audit-retry")
    retry.add_argument("--run-id", required=True)
    retry.add_argument("--task-id", required=True)
    retry.add_argument("--try-number", type=int, default=0)
    retry.add_argument("--error-message", default="")
    failure = subparsers.add_parser("audit-fail")
    failure.add_argument("--run-id", required=True)
    failure.add_argument("--task-id", required=True)
    failure.add_argument("--error-type", default="TaskFailure")
    failure.add_argument("--error-message", default="")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "audit-start":
        result = audit_start(args.run_id)
    elif args.command == "check-source":
        result = check_source()
    elif args.command == "snapshot-dimensions":
        result = snapshot_dimensions(args.run_id)
    elif args.command == "extract":
        result = extract_work_orders(args.run_id)
    elif args.command == "load-raw":
        result = load_raw_batch(args.run_id)
    elif args.command == "reconcile":
        result = reconcile(expected_count=args.expected_count)
    elif args.command == "audit-complete":
        result = audit_complete(args.run_id)
    elif args.command == "audit-retry":
        result = audit_event(
            run_id=args.run_id,
            task_id=args.task_id,
            event_type="retry",
            try_number=args.try_number,
            error_message=args.error_message,
        )
    else:
        result = audit_event(
            run_id=args.run_id,
            task_id=args.task_id,
            event_type="failure",
            error_type=args.error_type,
            error_message=args.error_message,
        )
    print(json.dumps(result, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
