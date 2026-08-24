"""Restartable PostgreSQL COPY loader for the isolated Stage 9 source database."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from psycopg import sql

from data_platform.config import DataPlatformSettings, safe_database_label
from data_platform.database import connect
from data_platform.generator import (
    ASSET_COLUMNS,
    LOCATION_COLUMNS,
    LOG_COLUMNS,
    PLAN_COLUMNS,
    USER_COLUMNS,
    WORK_ORDER_COLUMNS,
)
from data_platform.object_store import checksum


LOGGER = logging.getLogger("data_platform.loader")
UTC = timezone.utc


@dataclass(frozen=True, slots=True)
class LoadSpec:
    table_schema: str
    table_name: str
    columns: tuple[str, ...]
    conflict_columns: tuple[str, ...]


_SPECS: dict[str, LoadSpec] = {
    "users": LoadSpec("public", "users", tuple(USER_COLUMNS), ("id",)),
    "locations": LoadSpec("public", "locations", tuple(LOCATION_COLUMNS), ("id",)),
    "assets": LoadSpec("public", "assets", tuple(ASSET_COLUMNS), ("asset_id",)),
    "preventive_plans": LoadSpec(
        "public", "preventive_maintenance_plans", tuple(PLAN_COLUMNS), ("id",)
    ),
    "work_orders": LoadSpec("public", "work_orders", tuple(WORK_ORDER_COLUMNS), ("id",)),
    "work_order_updates": LoadSpec("public", "work_orders", tuple(WORK_ORDER_COLUMNS), ("id",)),
    "maintenance_logs": LoadSpec("public", "maintenance_logs", tuple(LOG_COLUMNS), ("log_id",)),
}


def migrate_scale_database(
    settings: DataPlatformSettings | None = None,
    *,
    data_platform_revision: str = "20260824_dp0001",
) -> None:
    """Apply application migrations, then the independent analytics history."""

    resolved = (settings or DataPlatformSettings.from_env()).validated()
    environment = {
        **dict(__import__("os").environ),
        "APP_ENVIRONMENT": "development",
        "STORAGE_BACKEND": "postgresql",
        "DATABASE_URL": resolved.sqlalchemy_url,
        "DATA_PLATFORM_DB_HOST": resolved.host,
        "DATA_PLATFORM_DB_PORT": str(resolved.port),
        "DATA_PLATFORM_DB_NAME": resolved.database,
        "DATA_PLATFORM_DB_USER": resolved.user,
        "DATA_PLATFORM_DB_PASSWORD": resolved.password,
    }
    LOGGER.info("Migrating isolated database %s", safe_database_label(resolved))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=environment,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "data_platform/alembic.ini",
            "upgrade",
            data_platform_revision,
        ],
        check=True,
        env=environment,
    )


def apply_measured_watermark_index(settings: DataPlatformSettings | None = None) -> None:
    """Advance only the Data Platform migration history to its measured index head."""

    resolved = (settings or DataPlatformSettings.from_env()).validated()
    environment = {
        **dict(__import__("os").environ),
        "DATA_PLATFORM_DB_HOST": resolved.host,
        "DATA_PLATFORM_DB_PORT": str(resolved.port),
        "DATA_PLATFORM_DB_NAME": resolved.database,
        "DATA_PLATFORM_DB_USER": resolved.user,
        "DATA_PLATFORM_DB_PASSWORD": resolved.password,
    }
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "data_platform/alembic.ini",
            "upgrade",
            "head",
        ],
        check=True,
        env=environment,
    )


def _copy_upsert(connection, path: Path, spec: LoadSpec) -> int:
    stage_name = "stage9_copy_buffer"
    qualified_table = sql.SQL("{}.{}").format(
        sql.Identifier(spec.table_schema), sql.Identifier(spec.table_name)
    )
    connection.execute(
        sql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP").format(
            sql.Identifier(stage_name), qualified_table
        )
    )
    column_list = sql.SQL(", ").join(map(sql.Identifier, spec.columns))
    copy_statement = sql.SQL(
        "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')"
    ).format(sql.Identifier(stage_name), column_list)
    with path.open("rb") as source, connection.cursor().copy(copy_statement) as copy:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            copy.write(block)

    update_columns = [column for column in spec.columns if column not in spec.conflict_columns]
    assignments = sql.SQL(", ").join(
        sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(column), sql.Identifier(column))
        for column in update_columns
    )
    insert_statement = sql.SQL(
        "INSERT INTO {} ({}) SELECT {} FROM {} ON CONFLICT ({}) DO UPDATE SET {}"
    ).format(
        qualified_table,
        column_list,
        column_list,
        sql.Identifier(stage_name),
        sql.SQL(", ").join(map(sql.Identifier, spec.conflict_columns)),
        assignments,
    )
    connection.execute(insert_statement)
    row = connection.execute(
        sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(stage_name))
    ).fetchone()
    return int(row[0]) if row else 0


def _already_loaded(
    connection,
    *,
    run_id: str,
    phase: str,
    entity: str,
    chunk_name: str,
    expected_sha256: str,
) -> bool:
    row = connection.execute(
        """
        SELECT file_sha256
        FROM audit.dataset_load_chunks
        WHERE benchmark_run_id = %s AND phase = %s
          AND entity = %s AND chunk_name = %s
        """,
        (run_id, phase, entity, chunk_name),
    ).fetchone()
    if row is None:
        return False
    if str(row[0]).strip() != expected_sha256:
        raise RuntimeError(f"Loaded chunk checksum conflict for {entity}/{chunk_name}.")
    return True


def _record_chunk(
    connection,
    *,
    run_id: str,
    phase: str,
    entity: str,
    chunk_name: str,
    file_sha256: str,
    row_count: int,
) -> None:
    connection.execute(
        """
        INSERT INTO audit.dataset_load_chunks (
            benchmark_run_id, phase, entity, chunk_name, file_sha256, row_count
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (benchmark_run_id, phase, entity, chunk_name) DO NOTHING
        """,
        (run_id, phase, entity, chunk_name, file_sha256, row_count),
    )


def load_scale_manifest(
    manifest_path: Path,
    settings: DataPlatformSettings | None = None,
) -> dict[str, Any]:
    """COPY a manifest in dependency order with chunk-level restart markers."""

    resolved = (settings or DataPlatformSettings.from_env()).validated()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_id = str(manifest["run_id"])
    phase = str(manifest["phase"])
    manifest_sha = checksum(manifest_path)
    requested = int(manifest["requested_work_orders"])
    started = time.perf_counter()
    total_loaded_rows = 0
    total_loaded_work_order_rows = 0
    skipped_files = 0

    with connect(resolved) as connection:
        existing = connection.execute(
            """
            SELECT manifest_sha256, status
            FROM audit.scale_load_runs
            WHERE benchmark_run_id = %s AND phase = %s
            """,
            (run_id, phase),
        ).fetchone()
        if existing and str(existing[0]).strip() != manifest_sha:
            raise RuntimeError("Run ID/phase already exists with a different manifest checksum.")
        connection.execute(
            """
            INSERT INTO audit.scale_load_runs (
                benchmark_run_id, phase, manifest_sha256, status, requested_work_orders
            ) VALUES (%s, %s, %s, 'loading', %s)
            ON CONFLICT (benchmark_run_id, phase) DO UPDATE SET
                status = 'loading', error_message = NULL
            """,
            (run_id, phase, manifest_sha, requested),
        )

    order = {
        "users": 0,
        "locations": 1,
        "assets": 2,
        "preventive_plans": 3,
        "work_orders": 4,
        "work_order_updates": 5,
        "maintenance_logs": 6,
    }
    entries = sorted(manifest["files"], key=lambda entry: (order[entry["entity"]], entry["name"]))
    try:
        for entry in entries:
            entity = str(entry["entity"])
            file_path = Path(entry["path"])
            expected_sha = str(entry["sha256"])
            if not file_path.exists() or checksum(file_path) != expected_sha:
                raise RuntimeError(f"Generated file checksum validation failed: {file_path}")
            with connect(resolved) as connection:
                if _already_loaded(
                    connection,
                    run_id=run_id,
                    phase=phase,
                    entity=entity,
                    chunk_name=file_path.name,
                    expected_sha256=expected_sha,
                ):
                    skipped_files += 1
                    LOGGER.info("Skipping verified loaded chunk %s", file_path.name)
                    continue
                row_count = _copy_upsert(connection, file_path, _SPECS[entity])
                if row_count != int(entry["row_count"]):
                    raise RuntimeError(
                        f"COPY count mismatch for {file_path.name}: {row_count} != {entry['row_count']}"
                    )
                _record_chunk(
                    connection,
                    run_id=run_id,
                    phase=phase,
                    entity=entity,
                    chunk_name=file_path.name,
                    file_sha256=expected_sha,
                    row_count=row_count,
                )
                total_loaded_rows += row_count
                if entity in {"work_orders", "work_order_updates"}:
                    total_loaded_work_order_rows += row_count
            elapsed = max(time.perf_counter() - started, 0.001)
            LOGGER.info(
                "Loaded %s rows=%s aggregate_throughput=%.0f rows/s",
                file_path.name,
                row_count,
                total_loaded_rows / elapsed,
            )

        with connect(resolved) as connection:
            loaded_work_order_row = connection.execute(
                """
                SELECT coalesce(sum(row_count), 0)
                FROM audit.dataset_load_chunks
                WHERE benchmark_run_id = %s AND phase = %s
                  AND entity IN ('work_orders', 'work_order_updates')
                """,
                (run_id, phase),
            ).fetchone()
            recorded_work_order_rows = int(loaded_work_order_row[0])
            connection.execute("ANALYZE public.users")
            connection.execute("ANALYZE public.locations")
            connection.execute("ANALYZE public.assets")
            connection.execute("ANALYZE public.preventive_maintenance_plans")
            connection.execute("ANALYZE public.work_orders")
            connection.execute("ANALYZE public.maintenance_logs")
            connection.execute(
                """
                UPDATE audit.scale_load_runs
                SET status = 'success', loaded_work_orders = %s,
                    finished_at = current_timestamp, error_message = NULL
                WHERE benchmark_run_id = %s AND phase = %s
                """,
                (recorded_work_order_rows, run_id, phase),
            )
    except BaseException as exc:
        with connect(resolved) as connection:
            connection.execute(
                """
                UPDATE audit.scale_load_runs
                SET status = 'failed', finished_at = current_timestamp,
                    error_message = left(%s, 1000)
                WHERE benchmark_run_id = %s AND phase = %s
                """,
                (str(exc), run_id, phase),
            )
        raise

    duration = time.perf_counter() - started
    result = {
        "run_id": run_id,
        "phase": phase,
        "loaded_rows_this_invocation": total_loaded_rows,
        "loaded_work_order_rows_this_invocation": total_loaded_work_order_rows,
        "skipped_verified_files": skipped_files,
        "duration_seconds": round(duration, 6),
        "rows_per_second": round(total_loaded_rows / max(duration, 0.001), 2),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    return result


def validate_operational_source(
    settings: DataPlatformSettings | None = None,
) -> dict[str, Any]:
    """Run integrity, enum, chronology, and relation-size checks after COPY."""

    resolved = settings or DataPlatformSettings.from_env()
    validations = {
        "work_order_duplicates": """
            SELECT count(*) FROM (
                SELECT id FROM public.work_orders GROUP BY id HAVING count(*) > 1
            ) AS duplicates
        """,
        "work_order_asset_orphans": """
            SELECT count(*) FROM public.work_orders w
            LEFT JOIN public.assets a ON a.asset_id = w.asset_id
            WHERE a.asset_id IS NULL
        """,
        "work_order_assignee_orphans": """
            SELECT count(*) FROM public.work_orders w
            LEFT JOIN public.users u ON u.id = w.assigned_to_user_id
            WHERE w.assigned_to_user_id IS NOT NULL AND u.id IS NULL
        """,
        "maintenance_log_orphans": """
            SELECT count(*) FROM public.maintenance_logs ml
            LEFT JOIN public.work_orders w ON w.id = ml.work_order_id
            WHERE ml.work_order_id IS NOT NULL AND w.id IS NULL
        """,
        "invalid_timestamp_order": """
            SELECT count(*) FROM public.work_orders
            WHERE created_at > updated_at
               OR (started_at IS NOT NULL AND started_at < created_at)
               OR (completed_at IS NOT NULL AND (
                    started_at IS NULL OR completed_at < started_at
               ))
        """,
        "invalid_status_values": """
            SELECT count(*) FROM public.work_orders
            WHERE status NOT IN (
                'planned','assigned','in_progress','on_hold',
                'completed','verified','cancelled'
            )
        """,
        "invalid_type_values": """
            SELECT count(*) FROM public.work_orders
            WHERE work_order_type NOT IN (
                'preventive','corrective','inspection','emergency'
            )
        """,
        "unvalidated_constraints": """
            SELECT count(*) FROM pg_constraint WHERE NOT convalidated
        """,
    }
    with connect(resolved, read_only=True) as connection:
        counts: dict[str, int] = {}
        for name, query in validations.items():
            row = connection.execute(query).fetchone()
            counts[name] = int(row[0]) if row else -1
        nonzero = {name: value for name, value in counts.items() if value != 0}
        if nonzero:
            raise RuntimeError(f"Operational source validation failed: {nonzero}")
        entity_counts = dict(
            connection.execute(
                """
                SELECT entity, row_count FROM (
                    SELECT 'users' AS entity, count(*)::bigint AS row_count FROM public.users
                    UNION ALL SELECT 'locations', count(*) FROM public.locations
                    UNION ALL SELECT 'assets', count(*) FROM public.assets
                    UNION ALL SELECT 'preventive_plans', count(*) FROM public.preventive_maintenance_plans
                    UNION ALL SELECT 'work_orders', count(*) FROM public.work_orders
                    UNION ALL SELECT 'maintenance_logs', count(*) FROM public.maintenance_logs
                ) AS counts
                """
            ).fetchall()
        )
        sizes = [
            {"relation": row[0], "total_bytes": int(row[1]), "index_bytes": int(row[2])}
            for row in connection.execute(
                """
                SELECT c.oid::regclass::text,
                       pg_total_relation_size(c.oid),
                       pg_indexes_size(c.oid)
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r' AND n.nspname IN ('public','raw','audit')
                ORDER BY pg_total_relation_size(c.oid) DESC
                LIMIT 20
                """
            ).fetchall()
        ]
    return {"validations": counts, "entity_counts": entity_counts, "largest_relations": sizes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--data-platform-revision", default="20260824_dp0001")
    load_parser = subparsers.add_parser("load")
    load_parser.add_argument("--manifest", type=Path, required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("apply-watermark-index")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "migrate":
        migrate_scale_database(data_platform_revision=args.data_platform_revision)
        result: dict[str, Any] = {"status": "migrated", "revision": args.data_platform_revision}
    elif args.command == "load":
        result = load_scale_manifest(args.manifest)
    elif args.command == "validate":
        result = validate_operational_source()
    else:
        apply_measured_watermark_index()
        result = {"status": "watermark_index_applied"}
    print(json.dumps(result, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
