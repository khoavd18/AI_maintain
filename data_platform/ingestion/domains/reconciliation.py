"""Cross-layer reconciliation and atomic domain-watermark finalization."""

from __future__ import annotations

from datetime import datetime, timezone
import json

from psycopg import sql

from data_platform.config import DataPlatformSettings
from data_platform.database import connect
from data_platform.ingestion.domains.catalog import DOMAINS, DOMAIN_SPECS
from data_platform.ingestion.domains.safety import validate_run_id
from data_platform.ingestion.domains.source_validation import domain_source_counts


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
ZERO_ID = ""


def relation_count(connection, relation: str, *, distinct: str | None = None) -> int:
    """Count one closed internal relation, optionally at a distinct grain."""

    expression = (
        sql.SQL("count(distinct {})").format(sql.Identifier(distinct))
        if distinct
        else sql.SQL("count(*)")
    )
    row = connection.execute(
        sql.SQL("SELECT {} FROM {}").format(expression, sql.SQL(relation))
    ).fetchone()
    return int(row[0]) if row else -1


def reconcile_run(
    run_id: str,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Require exact source/raw/staging/fact agreement before watermarking."""

    run_id = validate_run_id(run_id)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    source_counts = domain_source_counts(resolved)
    source = {domain: source_counts[domain] for domain in DOMAINS}
    with connect(resolved, read_only=True) as connection:
        raw = {
            "work_order_status_history": relation_count(
                connection, "raw.work_order_status_history", distinct="event_id"
            ),
            "tickets": relation_count(connection, "raw.tickets", distinct="ticket_id"),
            "ticket_events": relation_count(
                connection, "raw.ticket_events", distinct="event_id"
            ),
            "spare_parts": relation_count(
                connection, "raw.spare_parts", distinct="part_id"
            ),
            "inventory_movements": relation_count(
                connection, "raw.inventory_movements", distinct="movement_id"
            ),
            "work_order_costs": relation_count(
                connection, "raw.work_order_costs", distinct="work_order_id"
            ),
        }
        warehouse = {
            "work_order_status_history": relation_count(
                connection,
                DOMAIN_SPECS["work_order_status_history"].warehouse_relation,
            ),
            "tickets": relation_count(
                connection, DOMAIN_SPECS["tickets"].warehouse_relation
            ),
            "ticket_events": int(
                connection.execute(
                    "SELECT coalesce(sum(event_count), 0) "
                    "FROM analytics_warehouse.fact_ticket_sla"
                ).fetchone()[0]
            ),
            "spare_parts": relation_count(
                connection, DOMAIN_SPECS["spare_parts"].warehouse_relation
            ),
            "inventory_movements": relation_count(
                connection,
                DOMAIN_SPECS["inventory_movements"].warehouse_relation,
            ),
            "work_order_costs": relation_count(
                connection, DOMAIN_SPECS["work_order_costs"].warehouse_relation
            ),
        }
    mismatches = {
        domain: {
            "source": source[domain],
            "raw": raw[domain],
            "warehouse": warehouse[domain],
        }
        for domain in DOMAINS
        if len({source[domain], raw[domain], warehouse[domain]}) != 1
    }
    if mismatches:
        raise RuntimeError(f"Stage 10 layer reconciliation failed: {mismatches}")
    with connect(resolved) as connection:
        connection.execute(
            """
            UPDATE audit.domain_pipeline_runs
            SET source_counts = %s::jsonb, raw_counts = %s::jsonb,
                warehouse_counts = %s::jsonb, updated_at = current_timestamp
            WHERE run_id = %s
            """,
            (json.dumps(source), json.dumps(raw), json.dumps(warehouse), run_id),
        )
    return {"source": source, "raw": raw, "warehouse": warehouse, "mismatches": {}}


def finalize_watermarks(
    run_id: str,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Advance every non-empty domain watermark atomically exactly once."""

    run_id = validate_run_id(run_id)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    advanced: dict[str, bool] = {}

    # Keep every batch lock, watermark lock/update, and completion write in this
    # single transaction. Partial finalization is not an allowed state.
    with connect(resolved) as connection:
        batches = connection.execute(
            """
            SELECT domain_name, batch_id, status, row_count,
                   lower_available_at, lower_source_id,
                   upper_available_at, upper_source_id
            FROM audit.domain_extraction_batches
            WHERE run_id = %s
            ORDER BY domain_name
            FOR UPDATE
            """,
            (run_id,),
        ).fetchall()
        if len(batches) != len(DOMAINS):
            raise RuntimeError("Stage 10 cannot finalize without all six domain batches.")
        for row in batches:
            domain = str(row[0])
            batch_id = row[1]
            status = str(row[2])
            row_count = int(row[3])
            if status not in {"raw_loaded", "empty", "complete"}:
                raise RuntimeError(f"Stage 10 batch is not finalizable: {domain}/{status}")
            if row_count == 0:
                connection.execute(
                    """
                    UPDATE audit.domain_extraction_batches
                    SET status = 'empty',
                        completed_at = coalesce(completed_at, current_timestamp)
                    WHERE batch_id = %s
                    """,
                    (batch_id,),
                )
                advanced[domain] = False
                continue
            current = connection.execute(
                """
                SELECT source_available_at, source_id
                FROM audit.domain_watermarks
                WHERE domain_name = %s FOR UPDATE
                """,
                (domain,),
            ).fetchone()
            upper = (row[6], str(row[7]))
            if current and (current[0], str(current[1])) == upper:
                advanced[domain] = False
            else:
                lower = (row[4], str(row[5]))
                current_value = (
                    (current[0], str(current[1])) if current else (EPOCH, ZERO_ID)
                )
                if current_value != lower:
                    raise RuntimeError(
                        f"Stage 10 watermark changed concurrently for {domain}: "
                        f"{current_value} != {lower}"
                    )
                connection.execute(
                    """
                    INSERT INTO audit.domain_watermarks (
                        domain_name, source_available_at, source_id, batch_id
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (domain_name) DO UPDATE SET
                        source_available_at = EXCLUDED.source_available_at,
                        source_id = EXCLUDED.source_id,
                        batch_id = EXCLUDED.batch_id,
                        version = audit.domain_watermarks.version + 1,
                        advanced_at = current_timestamp
                    """,
                    (domain, upper[0], upper[1], batch_id),
                )
                advanced[domain] = True
            connection.execute(
                """
                UPDATE audit.domain_extraction_batches
                SET status = 'complete',
                    completed_at = coalesce(completed_at, current_timestamp)
                WHERE batch_id = %s
                """,
                (batch_id,),
            )
    return {"run_id": run_id, "advanced": advanced}
