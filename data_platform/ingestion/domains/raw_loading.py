"""Checksum-verified, idempotent raw loading for one domain batch."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from psycopg import sql

from data_platform.config import DataPlatformSettings
from data_platform.database import connect
from data_platform.ingestion.domains.catalog import DomainSpec, domain_spec
from data_platform.ingestion.domains.extraction import existing_batch
from data_platform.ingestion.domains.safety import validate_run_id
from data_platform.object_store import checksum


class InjectedDomainFailure(RuntimeError):
    """Explicit isolated-environment failure after a committed raw load."""


def copy_raw_object(connection, spec: DomainSpec, path: Path, batch_id: UUID) -> int:
    """COPY one immutable object into a temporary buffer and raw relation."""

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

    run_id = validate_run_id(run_id)
    spec = domain_spec(domain)
    if fault_domain:
        domain_spec(fault_domain)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    with connect(resolved, read_only=True) as connection:
        batch = existing_batch(connection, run_id, domain)
    if batch is None:
        raise RuntimeError(f"No extracted Stage 10 batch exists for {domain}/{run_id}.")
    path = Path(str(batch["object_path"]))
    if not path.exists() or checksum(path) != batch["object_sha256"]:
        raise RuntimeError(f"Stage 10 raw object checksum changed: {path}")
    batch_id = UUID(str(batch["batch_id"]))
    inserted = 0

    # This is one transaction boundary: raw rows and batch state commit together.
    with connect(resolved) as connection:
        if int(batch["row_count"]) > 0:
            inserted = copy_raw_object(connection, spec, path, batch_id)
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
