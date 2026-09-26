"""Durable run-state and audit operations for multi-domain ingestion."""

from __future__ import annotations

from data_platform.config import DataPlatformSettings
from data_platform.database import connect
from data_platform.ingestion.domains.catalog import domain_spec
from data_platform.ingestion.domains.safety import (
    sanitize_audit_message,
    validate_run_id,
)


def start_run(
    run_id: str,
    phase: str,
    *,
    fault_domain: str | None = None,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Create or safely resume a domain-scale pipeline run."""

    run_id = validate_run_id(run_id)
    if phase not in {"baseline", "incremental", "empty"}:
        raise ValueError("Stage 10 phase must be baseline, incremental, or empty.")
    if fault_domain:
        domain_spec(fault_domain)
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
                fault_domain = coalesce(
                    audit.domain_pipeline_runs.fault_domain,
                    EXCLUDED.fault_domain
                ),
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


def complete_run(
    run_id: str,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Mark success only after reconciliation and atomic finalization."""

    run_id = validate_run_id(run_id)
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

    run_id = validate_run_id(run_id)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    safe_step = sanitize_audit_message(step)
    with connect(resolved) as connection:
        connection.execute(
            """
            UPDATE audit.domain_pipeline_runs
            SET status = 'failed', failed_step = %s, error_message = %s,
                finished_at = current_timestamp, updated_at = current_timestamp
            WHERE run_id = %s AND status <> 'success'
            """,
            (safe_step, sanitize_audit_message(error), run_id),
        )
    return {"run_id": run_id, "status": "failed", "failed_step": safe_step}


def retry_run(
    run_id: str,
    step: str,
    error: object,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Record one Airflow retry and resume a failed run without touching batches."""

    run_id = validate_run_id(run_id)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    safe_step = sanitize_audit_message(step)
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
            (sanitize_audit_message(error), run_id),
        ).fetchone()
    if row is None:
        return {"run_id": run_id, "status": "unchanged", "step": safe_step}
    return {
        "run_id": run_id,
        "status": "running",
        "step": safe_step,
        "retry_count": int(row[0]),
    }


def pipeline_state(
    run_id: str,
    settings: DataPlatformSettings | None = None,
) -> dict[str, object]:
    """Return machine-readable audit evidence without connection details."""

    run_id = validate_run_id(run_id)
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
