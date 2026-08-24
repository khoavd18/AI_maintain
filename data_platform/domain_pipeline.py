"""Independent-watermark Stage 10 ingestion, recovery, and reconciliation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg import sql

from data_platform.config import DataPlatformSettings
from data_platform.database import connect
from data_platform.domain_loader import domain_source_counts, validate_domain_integrity
from data_platform.object_store import build_object_store, checksum


LOGGER = logging.getLogger("data_platform.domain_pipeline")
UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
ZERO_ID = ""
DOMAINS = (
    "work_order_status_history",
    "tickets",
    "ticket_events",
    "spare_parts",
    "inventory_movements",
    "work_order_costs",
)
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_MESSAGE_LIMIT = 1_000
_SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|token|secret)\s*[=:]\s*[^,\s;]+"
)
_URI_CREDENTIAL_PATTERN = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^:/\s]+:)[^@/\s]+@")


@dataclass(frozen=True, slots=True)
class DomainSpec:
    source_view: str
    raw_table: str
    columns: tuple[str, ...]
    identity_column: str
    warehouse_relation: str


_SPECS = {
    "work_order_status_history": DomainSpec(
        "analytics_source.work_order_status_history",
        "raw.work_order_status_history",
        (
            "event_id",
            "work_order_id",
            "work_order_number",
            "site_id",
            "asset_id",
            "sequence_number",
            "status",
            "transitioned_at",
            "next_transitioned_at",
            "is_late_arriving",
            "source_available_at",
        ),
        "event_id",
        "analytics_warehouse.fact_work_order_status_duration",
    ),
    "tickets": DomainSpec(
        "analytics_source.tickets",
        "raw.tickets",
        (
            "ticket_id",
            "asset_id",
            "site_id",
            "work_order_id",
            "severity",
            "priority",
            "status",
            "category",
            "issue_description",
            "assigned_user_id",
            "technician_id",
            "opened_at",
            "first_response_at",
            "resolved_at",
            "closed_at",
            "resolution_summary",
            "technician_note",
            "reopen_count",
            "source_available_at",
        ),
        "ticket_id",
        "analytics_warehouse.fact_ticket_sla",
    ),
    "ticket_events": DomainSpec(
        "analytics_source.ticket_events",
        "raw.ticket_events",
        (
            "event_id",
            "ticket_id",
            "event_domain",
            "event_type",
            "clock_type",
            "occurrence_number",
            "occurred_at",
            "details",
            "created_by_user_id",
            "source_available_at",
        ),
        "event_id",
        "analytics_warehouse.fact_ticket_sla",
    ),
    "spare_parts": DomainSpec(
        "analytics_source.spare_parts",
        "raw.spare_parts",
        (
            "part_id",
            "part_number",
            "part_name",
            "category_id",
            "category_code",
            "unit_of_measure_id",
            "unit_code",
            "lifecycle_status",
            "minimum_stock",
            "reorder_point",
            "maximum_stock",
            "unit_cost",
            "currency_code",
            "source_available_at",
        ),
        "part_id",
        "analytics_warehouse.dim_spare_part",
    ),
    "inventory_movements": DomainSpec(
        "analytics_source.inventory_movements",
        "raw.inventory_movements",
        (
            "movement_id",
            "movement_number",
            "operation_id",
            "part_id",
            "stock_location_id",
            "quantity",
            "movement_type",
            "business_reference",
            "actor_user_id",
            "occurred_at",
            "work_order_id",
            "unit_cost_snapshot",
            "resulting_on_hand_quantity",
            "resulting_reserved_quantity",
            "source_available_at",
        ),
        "movement_id",
        "analytics_warehouse.fact_inventory_movement",
    ),
    "work_order_costs": DomainSpec(
        "analytics_source.work_order_costs",
        "raw.work_order_costs",
        (
            "work_order_id",
            "work_order_number",
            "site_id",
            "asset_id",
            "estimated_labor_cost",
            "actual_labor_cost",
            "planned_part_cost",
            "actual_part_cost",
            "external_service_cost",
            "total_estimated_cost",
            "total_actual_cost",
            "cost_variance",
            "currency_code",
            "source_available_at",
        ),
        "work_order_id",
        "analytics_warehouse.fact_work_order_cost",
    ),
}


class InjectedDomainFailure(RuntimeError):
    """Explicit isolated-environment failure after a committed raw load."""


def _validated_run_id(run_id: str) -> str:
    if not _SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError("Stage 10 run ID contains unsupported characters.")
    return run_id


def _domain(domain: str) -> DomainSpec:
    try:
        return _SPECS[domain]
    except KeyError:
        raise ValueError(f"Unsupported Stage 10 domain: {domain!r}") from None


def _sanitize(message: object) -> str:
    value = " ".join(str(message or "").split())
    value = _SECRET_PATTERN.sub(r"\1=<redacted>", value)
    value = _URI_CREDENTIAL_PATTERN.sub(r"\1<redacted>@", value)
    return value[:_MESSAGE_LIMIT]


def start_run(
    run_id: str,
    phase: str,
    *,
    fault_domain: str | None = None,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Create or safely resume a domain-scale pipeline run."""

    run_id = _validated_run_id(run_id)
    if phase not in {"baseline", "incremental", "empty"}:
        raise ValueError("Stage 10 phase must be baseline, incremental, or empty.")
    if fault_domain:
        _domain(fault_domain)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    with connect(resolved) as connection:
        existing = connection.execute(
            "SELECT phase, status, retry_count FROM audit.domain_pipeline_runs WHERE run_id = %s",
            (run_id,),
        ).fetchone()
        if existing and str(existing[0]) != phase:
            raise RuntimeError("Stage 10 run ID already belongs to a different phase.")
        connection.execute(
            """
            INSERT INTO audit.domain_pipeline_runs (
                run_id, phase, status, fault_domain
            ) VALUES (%s, %s, 'running', %s)
            ON CONFLICT (run_id) DO UPDATE SET
                status = CASE
                    WHEN audit.domain_pipeline_runs.status = 'success' THEN 'success'
                    ELSE 'running'
                END,
                fault_domain = coalesce(audit.domain_pipeline_runs.fault_domain, EXCLUDED.fault_domain),
                updated_at = current_timestamp
            """,
            (run_id, phase, fault_domain or None),
        )
    return {
        "run_id": run_id,
        "phase": phase,
        "status": "success" if existing and str(existing[1]) == "success" else "running",
        "prior_retry_count": int(existing[2]) if existing else 0,
    }


def _watermark(connection, domain: str) -> tuple[datetime, str]:
    row = connection.execute(
        """
        SELECT source_available_at, source_id
        FROM audit.domain_watermarks
        WHERE domain_name = %s
        """,
        (domain,),
    ).fetchone()
    return (row[0], str(row[1])) if row else (EPOCH, ZERO_ID)


def _existing_batch(connection, run_id: str, domain: str) -> dict[str, object] | None:
    row = connection.execute(
        """
        SELECT batch_id, status, row_count, object_key, object_path,
               object_sha256, upper_available_at, upper_source_id,
               source_extracted_at, error_message
        FROM audit.domain_extraction_batches
        WHERE run_id = %s AND domain_name = %s
        """,
        (run_id, domain),
    ).fetchone()
    if row is None:
        return None
    return {
        "batch_id": row[0],
        "status": row[1],
        "row_count": int(row[2]),
        "object_key": row[3],
        "object_path": row[4],
        "object_sha256": str(row[5]).strip(),
        "upper_available_at": row[6],
        "upper_source_id": row[7],
        "source_extracted_at": row[8],
        "error_message": row[9],
    }


def extract_domain(
    run_id: str,
    phase: str,
    domain: str,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Stream one domain delta to a checksum-addressed local CSV object."""

    run_id = _validated_run_id(run_id)
    spec = _domain(domain)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    with connect(resolved, read_only=True) as connection:
        existing = _existing_batch(connection, run_id, domain)
    if existing is not None:
        object_path = Path(str(existing["object_path"]))
        if not object_path.exists() or checksum(object_path) != existing["object_sha256"]:
            raise RuntimeError(f"Immutable Stage 10 object changed for {domain}/{run_id}.")
        return existing

    batch_id = uuid5(NAMESPACE_URL, f"stage10:{run_id}:{domain}")
    extracted_at = datetime.now(UTC)
    run_pipeline_dir = resolved.data_root / "pipeline" / "stage10" / run_id
    pipeline_dir = run_pipeline_dir / domain
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    temporary = pipeline_dir / f"{domain}.csv.partial"
    final_source = pipeline_dir / f"{domain}.csv"
    lower_at: datetime
    lower_id: str
    upper_at: datetime | None = None
    upper_id: str | None = None
    newline_count = 0
    relation = sql.SQL(spec.source_view)
    selected = sql.SQL(", ").join(sql.Identifier(column) for column in spec.columns)
    with connect(resolved, read_only=True) as connection:
        lower_at, lower_id = _watermark(connection, domain)
        upper_row = connection.execute(
            sql.SQL(
                "SELECT source_available_at, source_id::text FROM {} "
                "WHERE (source_available_at, source_id::text) > (%s, %s) "
                "ORDER BY source_available_at DESC, source_id::text DESC LIMIT 1"
            ).format(relation),
            (lower_at, lower_id),
        ).fetchone()
        if upper_row:
            upper_at, upper_id = upper_row[0], str(upper_row[1])
        copy_statement = sql.SQL(
            "COPY (SELECT {}, %s::timestamptz AS source_extracted_at FROM {} "
            "WHERE (source_available_at, source_id::text) > (%s, %s) "
            "ORDER BY source_available_at, source_id::text) "
            "TO STDOUT WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')"
        ).format(selected, relation)
        with temporary.open("wb") as target, connection.cursor().copy(
            copy_statement,
            (extracted_at, lower_at, lower_id),
        ) as copy:
            for block in copy:
                data = bytes(block)
                target.write(data)
                newline_count += data.count(b"\n")
    temporary.replace(final_source)
    row_count = max(0, newline_count - 1)
    key = f"stage10/{phase}/{run_id}/{domain}.csv"
    stored = build_object_store(resolved).put(final_source, key)
    final_source.unlink(missing_ok=True)
    try:
        pipeline_dir.rmdir()
    except OSError:
        pass
    try:
        run_pipeline_dir.rmdir()
    except OSError:
        pass
    with connect(resolved) as connection:
        connection.execute(
            """
            INSERT INTO audit.domain_extraction_batches (
                batch_id, domain_name, run_id, phase, status,
                lower_available_at, lower_source_id,
                upper_available_at, upper_source_id, row_count,
                object_key, object_path, object_sha256, source_extracted_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                batch_id,
                domain,
                run_id,
                phase,
                "empty" if row_count == 0 else "extracted",
                lower_at,
                lower_id,
                upper_at,
                upper_id,
                row_count,
                stored.key,
                str(stored.path),
                stored.sha256,
                extracted_at,
            ),
        )
    return {
        "batch_id": batch_id,
        "domain": domain,
        "status": "empty" if row_count == 0 else "extracted",
        "row_count": row_count,
        "object_key": stored.key,
        "object_path": str(stored.path),
        "object_sha256": stored.sha256,
        "upper_available_at": upper_at,
        "upper_source_id": upper_id,
        "source_extracted_at": extracted_at,
    }


def _copy_raw_object(connection, spec: DomainSpec, path: Path, batch_id: UUID) -> int:
    stage = "stage10_domain_raw_buffer"
    columns = (*spec.columns, "source_extracted_at")
    selected = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
    connection.execute(
        sql.SQL("CREATE TEMP TABLE {} AS SELECT {} FROM {} WITH NO DATA").format(
            sql.Identifier(stage), selected, sql.SQL(spec.raw_table)
        )
    )
    copy_statement = sql.SQL(
        "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')"
    ).format(sql.Identifier(stage), selected)
    with path.open("rb") as source, connection.cursor().copy(copy_statement) as copy:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            copy.write(block)
    insert_columns = sql.SQL(", ").join(
        [sql.Identifier("ingestion_batch_id"), *map(sql.Identifier, columns)]
    )
    cursor = connection.execute(
        sql.SQL(
            "INSERT INTO {} ({}) SELECT %s::uuid, {} FROM {} ON CONFLICT DO NOTHING"
        ).format(
            sql.SQL(spec.raw_table),
            insert_columns,
            selected,
            sql.Identifier(stage),
        ),
        (batch_id,),
    )
    return max(0, int(cursor.rowcount or 0))


def load_raw_domain(
    run_id: str,
    domain: str,
    *,
    fault_domain: str | None = None,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Commit raw rows idempotently, then optionally inject one explicit fault."""

    run_id = _validated_run_id(run_id)
    spec = _domain(domain)
    if fault_domain:
        _domain(fault_domain)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    with connect(resolved, read_only=True) as connection:
        batch = _existing_batch(connection, run_id, domain)
    if batch is None:
        raise RuntimeError(f"No extracted Stage 10 batch exists for {domain}/{run_id}.")
    path = Path(str(batch["object_path"]))
    if not path.exists() or checksum(path) != batch["object_sha256"]:
        raise RuntimeError(f"Stage 10 raw object checksum changed: {path}")
    batch_id = UUID(str(batch["batch_id"]))
    inserted = 0
    with connect(resolved) as connection:
        if int(batch["row_count"]) > 0:
            inserted = _copy_raw_object(connection, spec, path, batch_id)
        connection.execute(
            """
            UPDATE audit.domain_extraction_batches
            SET status = CASE WHEN row_count = 0 THEN 'empty' ELSE 'raw_loaded' END,
                raw_inserted_count = coalesce(raw_inserted_count, %s),
                raw_loaded_at = coalesce(raw_loaded_at, current_timestamp),
                error_message = CASE
                    WHEN error_message = 'fault_injected_after_raw'
                        THEN error_message
                    ELSE NULL
                END
            WHERE batch_id = %s
            """,
            (inserted, batch_id),
        )

    should_fault = fault_domain == domain
    if should_fault:
        with connect(resolved) as connection:
            row = connection.execute(
                "SELECT failed_step, status FROM audit.domain_pipeline_runs "
                "WHERE run_id = %s FOR UPDATE",
                (run_id,),
            ).fetchone()
            marker = f"fault_after_raw:{domain}"
            if row is None:
                raise RuntimeError("Stage 10 run audit is missing before fault injection.")
            if str(batch.get("error_message") or "") != "fault_injected_after_raw":
                connection.execute(
                    """
                    UPDATE audit.domain_extraction_batches
                    SET error_message = 'fault_injected_after_raw'
                    WHERE batch_id = %s
                    """,
                    (batch_id,),
                )
                connection.execute(
                    """
                    UPDATE audit.domain_pipeline_runs
                    SET status = 'failed', failed_step = %s,
                        error_message = %s, finished_at = current_timestamp,
                        updated_at = current_timestamp
                    WHERE run_id = %s
                    """,
                    (marker, "Explicit test-only fault after committed raw load.", run_id),
                )
                raise InjectedDomainFailure(
                    f"Explicit Stage 10 fault injected after {domain} raw load."
                )
            if str(row[1]) == "failed":
                connection.execute(
                    """
                    UPDATE audit.domain_pipeline_runs
                    SET status = 'running', retry_count = retry_count + 1,
                        finished_at = NULL, error_message = NULL,
                        updated_at = current_timestamp
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
    return {
        "run_id": run_id,
        "domain": domain,
        "batch_id": batch_id,
        "row_count": int(batch["row_count"]),
        "inserted_count": inserted,
        "status": "empty" if int(batch["row_count"]) == 0 else "raw_loaded",
    }


def _relation_count(connection, relation: str, *, distinct: str | None = None) -> int:
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

    run_id = _validated_run_id(run_id)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    source_counts = domain_source_counts(resolved)
    source = {
        "work_order_status_history": source_counts["work_order_status_history"],
        "tickets": source_counts["tickets"],
        "ticket_events": source_counts["ticket_events"],
        "spare_parts": source_counts["spare_parts"],
        "inventory_movements": source_counts["inventory_movements"],
        "work_order_costs": source_counts["work_order_costs"],
    }
    with connect(resolved, read_only=True) as connection:
        raw = {
            "work_order_status_history": _relation_count(
                connection, "raw.work_order_status_history", distinct="event_id"
            ),
            "tickets": _relation_count(connection, "raw.tickets", distinct="ticket_id"),
            "ticket_events": _relation_count(
                connection, "raw.ticket_events", distinct="event_id"
            ),
            "spare_parts": _relation_count(
                connection, "raw.spare_parts", distinct="part_id"
            ),
            "inventory_movements": _relation_count(
                connection, "raw.inventory_movements", distinct="movement_id"
            ),
            "work_order_costs": _relation_count(
                connection, "raw.work_order_costs", distinct="work_order_id"
            ),
        }
        warehouse = {
            "work_order_status_history": _relation_count(
                connection, _SPECS["work_order_status_history"].warehouse_relation
            ),
            "tickets": _relation_count(connection, _SPECS["tickets"].warehouse_relation),
            "ticket_events": int(
                connection.execute(
                    "SELECT coalesce(sum(event_count), 0) "
                    "FROM analytics_warehouse.fact_ticket_sla"
                ).fetchone()[0]
            ),
            "spare_parts": _relation_count(
                connection, _SPECS["spare_parts"].warehouse_relation
            ),
            "inventory_movements": _relation_count(
                connection, _SPECS["inventory_movements"].warehouse_relation
            ),
            "work_order_costs": _relation_count(
                connection, _SPECS["work_order_costs"].warehouse_relation
            ),
        }
    mismatches = {
        domain: {"source": source[domain], "raw": raw[domain], "warehouse": warehouse[domain]}
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

    run_id = _validated_run_id(run_id)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    advanced: dict[str, bool] = {}
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
            domain, batch_id, status, row_count = str(row[0]), row[1], str(row[2]), int(row[3])
            if status not in {"raw_loaded", "empty", "complete"}:
                raise RuntimeError(f"Stage 10 batch is not finalizable: {domain}/{status}")
            if row_count == 0:
                connection.execute(
                    """
                    UPDATE audit.domain_extraction_batches
                    SET status = 'empty', completed_at = coalesce(completed_at, current_timestamp)
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
                current_value = (current[0], str(current[1])) if current else (EPOCH, ZERO_ID)
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
                SET status = 'complete', completed_at = coalesce(completed_at, current_timestamp)
                WHERE batch_id = %s
                """,
                (batch_id,),
            )
    return {"run_id": run_id, "advanced": advanced}


def complete_run(
    run_id: str,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Mark success only after reconciliation and atomic finalization."""

    run_id = _validated_run_id(run_id)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    with connect(resolved) as connection:
        row = connection.execute(
            """
            UPDATE audit.domain_pipeline_runs
            SET status = 'success', finished_at = current_timestamp,
                error_message = NULL, updated_at = current_timestamp
            WHERE run_id = %s AND status = 'running'
            RETURNING phase, retry_count, started_at, finished_at
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            existing = connection.execute(
                """
                SELECT phase, retry_count, started_at, finished_at, status
                FROM audit.domain_pipeline_runs WHERE run_id = %s
                """,
                (run_id,),
            ).fetchone()
            if existing is None or str(existing[4]) != "success":
                raise RuntimeError("Stage 10 run is not in a completable state.")
            row = existing[:4]
    return {
        "run_id": run_id,
        "phase": row[0],
        "status": "success",
        "retry_count": int(row[1]),
        "started_at": row[2],
        "finished_at": row[3],
    }


def fail_run(
    run_id: str,
    step: str,
    error: object,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Persist one sanitized terminal failure without changing watermarks."""

    run_id = _validated_run_id(run_id)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    with connect(resolved) as connection:
        connection.execute(
            """
            UPDATE audit.domain_pipeline_runs
            SET status = 'failed', failed_step = %s, error_message = %s,
                finished_at = current_timestamp, updated_at = current_timestamp
            WHERE run_id = %s AND status <> 'success'
            """,
            (_sanitize(step), _sanitize(error), run_id),
        )
    return {"run_id": run_id, "status": "failed", "failed_step": _sanitize(step)}


def retry_run(
    run_id: str,
    step: str,
    error: object,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Record one Airflow retry and resume a failed run without touching batches."""

    run_id = _validated_run_id(run_id)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    with connect(resolved) as connection:
        row = connection.execute(
            """
            UPDATE audit.domain_pipeline_runs
            SET status = 'running', retry_count = retry_count + 1,
                finished_at = NULL, error_message = %s,
                updated_at = current_timestamp
            WHERE run_id = %s AND status <> 'success'
            RETURNING retry_count
            """,
            (_sanitize(error), run_id),
        ).fetchone()
    if row is None:
        return {"run_id": run_id, "status": "unchanged", "step": _sanitize(step)}
    return {
        "run_id": run_id,
        "status": "running",
        "step": _sanitize(step),
        "retry_count": int(row[0]),
    }


def pipeline_state(
    run_id: str,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Return machine-readable audit evidence without connection details."""

    run_id = _validated_run_id(run_id)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    with connect(resolved, read_only=True) as connection:
        run = connection.execute(
            """
            SELECT phase, status, fault_domain, started_at, finished_at,
                   retry_count, failed_step, source_counts, raw_counts, warehouse_counts
            FROM audit.domain_pipeline_runs WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()
        batches = connection.execute(
            """
            SELECT domain_name, batch_id, status, row_count, raw_inserted_count,
                   object_sha256, source_extracted_at, raw_loaded_at, completed_at
            FROM audit.domain_extraction_batches
            WHERE run_id = %s ORDER BY domain_name
            """,
            (run_id,),
        ).fetchall()
    if run is None:
        raise RuntimeError(f"Unknown Stage 10 run: {run_id}")
    return {
        "run_id": run_id,
        "phase": run[0],
        "status": run[1],
        "fault_domain": run[2],
        "started_at": run[3],
        "finished_at": run[4],
        "retry_count": int(run[5]),
        "failed_step": run[6],
        "source_counts": run[7],
        "raw_counts": run[8],
        "warehouse_counts": run[9],
        "batches": [
            {
                "domain": row[0],
                "batch_id": row[1],
                "status": row[2],
                "row_count": int(row[3]),
                "raw_inserted_count": int(row[4] or 0),
                "sha256": str(row[5]).strip(),
                "source_extracted_at": row[6],
                "raw_loaded_at": row[7],
                "completed_at": row[8],
            }
            for row in batches
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    start.add_argument("--run-id", required=True)
    start.add_argument("--phase", required=True)
    start.add_argument("--fault-domain", default="")
    extract = subparsers.add_parser("extract")
    extract.add_argument("--run-id", required=True)
    extract.add_argument("--phase", required=True)
    extract.add_argument("--domain", choices=DOMAINS, required=True)
    load = subparsers.add_parser("load-raw")
    load.add_argument("--run-id", required=True)
    load.add_argument("--domain", choices=DOMAINS, required=True)
    load.add_argument("--fault-domain", default="")
    reconcile = subparsers.add_parser("reconcile")
    reconcile.add_argument("--run-id", required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--run-id", required=True)
    complete = subparsers.add_parser("complete")
    complete.add_argument("--run-id", required=True)
    fail = subparsers.add_parser("audit-fail")
    fail.add_argument("--run-id", required=True)
    fail.add_argument("--step", required=True)
    fail.add_argument("--error", default="")
    retry = subparsers.add_parser("audit-retry")
    retry.add_argument("--run-id", required=True)
    retry.add_argument("--step", required=True)
    retry.add_argument("--error", default="")
    state = subparsers.add_parser("state")
    state.add_argument("--run-id", required=True)
    subparsers.add_parser("validate")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "start":
        result = start_run(
            args.run_id,
            args.phase,
            fault_domain=args.fault_domain or None,
        )
    elif args.command == "extract":
        result = extract_domain(args.run_id, args.phase, args.domain)
    elif args.command == "load-raw":
        result = load_raw_domain(
            args.run_id,
            args.domain,
            fault_domain=args.fault_domain or None,
        )
    elif args.command == "reconcile":
        result = reconcile_run(args.run_id)
    elif args.command == "finalize":
        result = finalize_watermarks(args.run_id)
    elif args.command == "complete":
        result = complete_run(args.run_id)
    elif args.command == "audit-fail":
        result = fail_run(args.run_id, args.step, args.error)
    elif args.command == "audit-retry":
        result = retry_run(args.run_id, args.step, args.error)
    elif args.command == "state":
        result = pipeline_state(args.run_id)
    else:
        result = validate_domain_integrity()
    print(json.dumps(result, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
