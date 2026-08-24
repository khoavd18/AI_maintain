"""Restartable COPY loader for Stage 10 application and compatibility domains."""

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
from data_platform.domain_generator import (
    CALENDAR_COLUMNS,
    COST_COLUMNS,
    INVENTORY_MOVEMENT_COLUMNS,
    PART_CATEGORY_COLUMNS,
    SLA_POLICY_COLUMNS,
    SLA_TARGET_COLUMNS,
    SPARE_PART_COLUMNS,
    STATUS_COLUMNS,
    STOCK_LOCATION_COLUMNS,
    TICKET_COLUMNS,
    TICKET_ESCALATION_EVENT_COLUMNS,
    TICKET_LINK_COLUMNS,
    TICKET_SLA_EVENT_COLUMNS,
    TICKET_SLA_STATE_COLUMNS,
    UNIT_COLUMNS,
)
from data_platform.object_store import checksum


LOGGER = logging.getLogger("data_platform.domain_loader")
UTC = timezone.utc


@dataclass(frozen=True, slots=True)
class LoadSpec:
    schema: str
    table: str
    columns: tuple[str, ...]
    conflict_columns: tuple[str, ...]
    mutable: bool = False


_SPECS: dict[str, LoadSpec] = {
    "business_calendars": LoadSpec(
        "public", "business_calendars", tuple(CALENDAR_COLUMNS), ("id",), True
    ),
    "sla_policies": LoadSpec(
        "public", "sla_policies", tuple(SLA_POLICY_COLUMNS), ("id",), True
    ),
    "sla_policy_targets": LoadSpec(
        "public", "sla_policy_targets", tuple(SLA_TARGET_COLUMNS), ("id",), True
    ),
    "tickets": LoadSpec(
        "public", "maintenance_tickets", tuple(TICKET_COLUMNS), ("ticket_id",), True
    ),
    "ticket_updates": LoadSpec(
        "public", "maintenance_tickets", tuple(TICKET_COLUMNS), ("ticket_id",), True
    ),
    "ticket_links": LoadSpec(
        "analytics_compat",
        "ticket_work_order_links",
        tuple(TICKET_LINK_COLUMNS),
        ("ticket_id",),
    ),
    "ticket_sla_states": LoadSpec(
        "public", "ticket_sla_states", tuple(TICKET_SLA_STATE_COLUMNS), ("id",)
    ),
    "ticket_sla_events": LoadSpec(
        "public", "ticket_sla_events", tuple(TICKET_SLA_EVENT_COLUMNS), ("id",)
    ),
    "ticket_escalation_events": LoadSpec(
        "public",
        "ticket_escalation_events",
        tuple(TICKET_ESCALATION_EVENT_COLUMNS),
        ("id",),
    ),
    "part_categories": LoadSpec(
        "public", "part_categories", tuple(PART_CATEGORY_COLUMNS), ("id",), True
    ),
    "units_of_measure": LoadSpec(
        "public", "units_of_measure", tuple(UNIT_COLUMNS), ("id",), True
    ),
    "stock_locations": LoadSpec(
        "public", "stock_locations", tuple(STOCK_LOCATION_COLUMNS), ("id",), True
    ),
    "spare_parts": LoadSpec(
        "public", "spare_parts", tuple(SPARE_PART_COLUMNS), ("id",), True
    ),
    "spare_part_updates": LoadSpec(
        "public", "spare_parts", tuple(SPARE_PART_COLUMNS), ("id",), True
    ),
    "work_order_status_history": LoadSpec(
        "analytics_compat",
        "work_order_status_history",
        tuple(STATUS_COLUMNS),
        ("event_id",),
    ),
    "work_order_costs": LoadSpec(
        "analytics_compat",
        "work_order_cost_facts",
        tuple(COST_COLUMNS),
        ("work_order_id",),
    ),
}

_ORDER = {
    "business_calendars": 0,
    "sla_policies": 1,
    "sla_policy_targets": 2,
    "part_categories": 3,
    "units_of_measure": 4,
    "stock_locations": 5,
    "tickets": 6,
    "ticket_updates": 6,
    "ticket_links": 7,
    "ticket_sla_states": 8,
    "ticket_sla_events": 9,
    "ticket_escalation_events": 10,
    "spare_parts": 11,
    "spare_part_updates": 11,
    "work_order_status_history": 12,
    "inventory_movements": 13,
    "work_order_costs": 14,
}


def migrate_domain_scale_database(settings: DataPlatformSettings | None = None) -> None:
    """Advance only the independent Data Platform history to its Stage 10 head."""

    resolved = (settings or DataPlatformSettings.from_env()).validated()
    environment = {
        **dict(__import__("os").environ),
        "DATA_PLATFORM_DB_HOST": resolved.host,
        "DATA_PLATFORM_DB_PORT": str(resolved.port),
        "DATA_PLATFORM_DB_NAME": resolved.database,
        "DATA_PLATFORM_DB_USER": resolved.user,
        "DATA_PLATFORM_DB_PASSWORD": resolved.password,
    }
    LOGGER.info("Migrating Stage 10 database %s", safe_database_label(resolved))
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


def _copy_to_stage(connection, path: Path, qualified_table, columns: tuple[str, ...]) -> int:
    stage = "stage10_copy_buffer"
    connection.execute(
        sql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP").format(
            sql.Identifier(stage), qualified_table
        )
    )
    column_list = sql.SQL(", ").join(map(sql.Identifier, columns))
    statement = sql.SQL(
        "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')"
    ).format(sql.Identifier(stage), column_list)
    with path.open("rb") as source, connection.cursor().copy(statement) as copy:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            copy.write(block)
    row = connection.execute(
        sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(stage))
    ).fetchone()
    return int(row[0]) if row else 0


def _copy_generic(connection, path: Path, spec: LoadSpec) -> int:
    qualified = sql.SQL("{}.{}").format(sql.Identifier(spec.schema), sql.Identifier(spec.table))
    count = _copy_to_stage(connection, path, qualified, spec.columns)
    columns = sql.SQL(", ").join(map(sql.Identifier, spec.columns))
    conflict = sql.SQL(", ").join(map(sql.Identifier, spec.conflict_columns))
    if spec.mutable:
        update_columns = [column for column in spec.columns if column not in spec.conflict_columns]
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(column), sql.Identifier(column))
            for column in update_columns
        )
        action = sql.SQL("DO UPDATE SET {} ").format(assignments)
        if "updated_at" in spec.columns:
            action += sql.SQL(
                "WHERE EXCLUDED.updated_at >= {}.updated_at"
            ).format(sql.Identifier(spec.table))
    else:
        action = sql.SQL("DO NOTHING")
    connection.execute(
        sql.SQL(
            "INSERT INTO {} ({}) SELECT {} FROM stage10_copy_buffer "
            "ON CONFLICT ({}) {}"
        ).format(qualified, columns, columns, conflict, action)
    )
    return count


def _copy_inventory_movements(connection, path: Path) -> int:
    qualified = sql.SQL("public.inventory_movements")
    count = _copy_to_stage(
        connection,
        path,
        qualified,
        tuple(INVENTORY_MOVEMENT_COLUMNS),
    )
    connection.execute(
        """
        INSERT INTO public.inventory_operations (
            id, idempotency_key, operation_type, request_hash,
            result_type, result_id, actor_user_id, created_at
        )
        SELECT
            operation_id,
            idempotency_key,
            CASE movement_type
                WHEN 'transfer_out' THEN 'transfer'
                WHEN 'transfer_in' THEN 'transfer'
                ELSE movement_type
            END,
            md5(idempotency_key) || md5(idempotency_key || ':stage10'),
            'inventory_movement',
            id::text,
            actor_user_id,
            created_at
        FROM stage10_copy_buffer
        ON CONFLICT (id) DO NOTHING
        """
    )
    columns = sql.SQL(", ").join(map(sql.Identifier, INVENTORY_MOVEMENT_COLUMNS))
    connection.execute(
        sql.SQL(
            "INSERT INTO public.inventory_movements ({}) "
            "SELECT {} FROM stage10_copy_buffer ON CONFLICT (id) DO NOTHING"
        ).format(columns, columns)
    )
    connection.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (part_id, stock_location_id)
                part_id,
                stock_location_id,
                resulting_on_hand_quantity,
                resulting_reserved_quantity,
                occurred_at
            FROM stage10_copy_buffer
            ORDER BY part_id, stock_location_id, occurred_at DESC, id DESC
        )
        INSERT INTO public.inventory_positions (
            id, part_id, stock_location_id, on_hand_quantity,
            reserved_quantity, updated_at, version
        )
        SELECT
            md5(part_id::text || ':' || stock_location_id::text)::uuid,
            part_id,
            stock_location_id,
            resulting_on_hand_quantity,
            resulting_reserved_quantity,
            occurred_at,
            1
        FROM latest
        ON CONFLICT (part_id, stock_location_id) DO UPDATE SET
            on_hand_quantity = EXCLUDED.on_hand_quantity,
            reserved_quantity = EXCLUDED.reserved_quantity,
            updated_at = EXCLUDED.updated_at,
            version = public.inventory_positions.version + 1
        WHERE EXCLUDED.updated_at >= public.inventory_positions.updated_at
        """
    )
    return count


def _loaded_checksum(
    connection,
    *,
    run_id: str,
    phase: str,
    entity: str,
    chunk_name: str,
) -> str | None:
    row = connection.execute(
        """
        SELECT file_sha256
        FROM audit.stage10_dataset_load_chunks
        WHERE dataset_run_id = %s AND phase = %s
          AND entity = %s AND chunk_name = %s
        """,
        (run_id, phase, entity, chunk_name),
    ).fetchone()
    return str(row[0]).strip() if row else None


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
        INSERT INTO audit.stage10_dataset_load_chunks (
            dataset_run_id, phase, entity, chunk_name, file_sha256, row_count
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (dataset_run_id, phase, entity, chunk_name) DO NOTHING
        """,
        (run_id, phase, entity, chunk_name, file_sha256, row_count),
    )


def domain_source_counts(settings: DataPlatformSettings | None = None) -> dict[str, int]:
    """Return exact unique source counts from the isolated scale database."""

    resolved = (settings or DataPlatformSettings.from_env()).validated()
    with connect(resolved, read_only=True) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM public.work_orders),
                (SELECT count(*) FROM analytics_compat.work_order_status_history),
                (SELECT count(*) FROM public.maintenance_tickets),
                (
                    (SELECT count(*) FROM public.ticket_sla_events)
                    + (SELECT count(*) FROM public.ticket_escalation_events)
                ),
                (SELECT count(*) FROM public.spare_parts),
                (SELECT count(*) FROM public.inventory_movements),
                (SELECT count(*) FROM analytics_compat.work_order_cost_facts)
            """
        ).fetchone()
    if row is None:
        raise RuntimeError("Stage 10 count query returned no row.")
    keys = (
        "work_orders",
        "work_order_status_history",
        "tickets",
        "ticket_events",
        "spare_parts",
        "inventory_movements",
        "work_order_costs",
    )
    return dict(zip(keys, map(int, row), strict=True))


def validate_domain_integrity(
    settings: DataPlatformSettings | None = None,
) -> dict[str, int]:
    """Return zero-valued integrity checks or fail with their exact counts."""

    resolved = (settings or DataPlatformSettings.from_env()).validated()
    queries = {
        "status_final_mismatch": """
            SELECT count(*) FROM (
                SELECT DISTINCT ON (h.work_order_id) h.work_order_id, h.status
                FROM analytics_compat.work_order_status_history h
                ORDER BY h.work_order_id, h.sequence_number DESC
            ) latest
            JOIN public.work_orders w ON w.id = latest.work_order_id
            WHERE latest.status <> w.status
        """,
        "status_consecutive_duplicates": """
            SELECT count(*) FROM (
                SELECT status, lag(status) OVER (
                    PARTITION BY work_order_id ORDER BY sequence_number
                ) AS prior_status
                FROM analytics_compat.work_order_status_history
            ) x WHERE status = prior_status
        """,
        "status_negative_duration": """
            SELECT count(*) FROM (
                SELECT transitioned_at, lead(transitioned_at) OVER (
                    PARTITION BY work_order_id ORDER BY sequence_number
                ) AS next_at
                FROM analytics_compat.work_order_status_history
            ) x WHERE next_at < transitioned_at
        """,
        "ticket_resolution_evidence": """
            SELECT count(*) FROM public.maintenance_tickets
            WHERE status IN ('resolved', 'closed')
              AND (resolved_at IS NULL OR nullif(btrim(manager_note), '') IS NULL)
        """,
        "ticket_orphan_events": """
            SELECT count(*) FROM analytics_source.ticket_events e
            LEFT JOIN public.maintenance_tickets t ON t.ticket_id = e.ticket_id
            WHERE t.ticket_id IS NULL
        """,
        "inventory_operation_mismatch": """
            SELECT abs(
                (SELECT count(*) FROM public.inventory_movements)
                - (SELECT count(*) FROM public.inventory_operations)
            )
        """,
        "inventory_invalid_balance": """
            SELECT count(*) FROM public.inventory_positions
            WHERE on_hand_quantity < 0 OR reserved_quantity < 0
               OR reserved_quantity > on_hand_quantity
        """,
        "cost_reconciliation": """
            SELECT count(*) FROM analytics_compat.work_order_cost_facts
            WHERE total_estimated_cost <> estimated_labor_cost + planned_part_cost
               OR total_actual_cost <> actual_labor_cost + actual_part_cost
                    + external_service_cost
               OR cost_variance <> total_actual_cost - total_estimated_cost
        """,
    }
    results: dict[str, int] = {}
    with connect(resolved, read_only=True) as connection:
        for name, statement in queries.items():
            row = connection.execute(statement).fetchone()
            results[name] = int(row[0]) if row else -1
    violations = {name: count for name, count in results.items() if count != 0}
    if violations:
        raise RuntimeError(f"Stage 10 integrity violations: {violations}")
    return results


def load_domain_manifest(
    manifest_path: Path,
    settings: DataPlatformSettings | None = None,
) -> dict[str, Any]:
    """Load a verified Stage 10 manifest with file-level idempotency."""

    resolved = (settings or DataPlatformSettings.from_env()).validated()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_id = str(manifest["run_id"])
    phase = str(manifest["phase"])
    entries = sorted(
        manifest["files"],
        key=lambda entry: (_ORDER[str(entry["entity"])], str(entry["name"])),
    )
    started = time.perf_counter()
    loaded_rows = 0
    skipped_files = 0
    per_entity: dict[str, int] = {}
    for entry in entries:
        entity = str(entry["entity"])
        path = Path(str(entry["path"]))
        expected_sha = str(entry["sha256"])
        if not path.exists() or checksum(path) != expected_sha:
            raise RuntimeError(f"Stage 10 checksum verification failed: {path}")
        with connect(resolved) as connection:
            prior = _loaded_checksum(
                connection,
                run_id=run_id,
                phase=phase,
                entity=entity,
                chunk_name=path.name,
            )
            if prior is not None:
                if prior != expected_sha:
                    raise RuntimeError(f"Stage 10 loaded checksum conflict: {path.name}")
                skipped_files += 1
                continue
            if entity == "inventory_movements":
                copied = _copy_inventory_movements(connection, path)
            else:
                copied = _copy_generic(connection, path, _SPECS[entity])
            if copied != int(entry["row_count"]):
                raise RuntimeError(
                    f"Stage 10 COPY count mismatch for {path.name}: "
                    f"{copied} != {entry['row_count']}"
                )
            _record_chunk(
                connection,
                run_id=run_id,
                phase=phase,
                entity=entity,
                chunk_name=path.name,
                file_sha256=expected_sha,
                row_count=copied,
            )
        loaded_rows += copied
        per_entity[entity] = per_entity.get(entity, 0) + copied
        LOGGER.info("Loaded Stage 10 chunk %s rows=%d", path.name, copied)

    with connect(resolved) as connection:
        for relation in (
            "analytics_compat.work_order_status_history",
            "analytics_compat.work_order_cost_facts",
            "public.maintenance_tickets",
            "public.ticket_sla_states",
            "public.ticket_sla_events",
            "public.ticket_escalation_events",
            "public.spare_parts",
            "public.inventory_movements",
            "public.inventory_positions",
        ):
            connection.execute(sql.SQL("ANALYZE {}").format(sql.SQL(relation)))
    duration = time.perf_counter() - started
    counts = domain_source_counts(resolved)
    if phase == "incremental":
        target_counts = {key: int(value) for key, value in manifest["target_counts"].items()}
        if counts != target_counts:
            raise RuntimeError(f"Final Stage 10 source counts do not match: {counts}")
        integrity = validate_domain_integrity(resolved)
    else:
        integrity = {}
    result = {
        "run_id": run_id,
        "phase": phase,
        "loaded_rows": loaded_rows,
        "skipped_files": skipped_files,
        "duration_seconds": round(duration, 6),
        "rows_per_second": round(loaded_rows / max(duration, 0.001), 2),
        "per_entity": per_entity,
        "source_counts": counts,
        "integrity": integrity,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    result_path = manifest_path.parent / "load-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate")
    load = subparsers.add_parser("load")
    load.add_argument("--manifest", type=Path, required=True)
    subparsers.add_parser("counts")
    subparsers.add_parser("validate")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "migrate":
        migrate_domain_scale_database()
        result: dict[str, object] = {"status": "migrated"}
    elif args.command == "load":
        result = load_domain_manifest(args.manifest)
    elif args.command == "counts":
        result = domain_source_counts()
    else:
        result = validate_domain_integrity()
    print(json.dumps(result, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
