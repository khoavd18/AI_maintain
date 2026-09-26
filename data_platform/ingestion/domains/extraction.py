"""Tuple-watermark extraction and immutable object publication by domain."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from psycopg import sql

from data_platform.config import DataPlatformSettings
from data_platform.database import connect
from data_platform.ingestion.domains.catalog import domain_spec
from data_platform.ingestion.domains.safety import validate_run_id
from data_platform.object_store import build_object_store, checksum


LOGGER = logging.getLogger("data_platform.domain_pipeline")
UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
ZERO_ID = ""


def watermark(connection, domain: str) -> tuple[datetime, str]:
    """Read the committed lower tuple for one domain."""

    row = connection.execute(
        """
        SELECT source_available_at, source_id
        FROM audit.domain_watermarks
        WHERE domain_name = %s
        """,
        (domain,),
    ).fetchone()
    return (row[0], str(row[1])) if row else (EPOCH, ZERO_ID)


def existing_batch(connection, run_id: str, domain: str) -> dict[str, object] | None:
    """Return persisted extraction metadata used for idempotent replay."""

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

    run_id = validate_run_id(run_id)
    spec = domain_spec(domain)
    resolved = (settings or DataPlatformSettings.from_env()).validated()
    with connect(resolved, read_only=True) as connection:
        existing = existing_batch(connection, run_id, domain)
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
        lower_at, lower_id = watermark(connection, domain)
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
