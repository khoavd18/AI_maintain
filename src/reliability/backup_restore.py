"""Safe PostgreSQL backup/restore drill for a separate disposable database."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.engine import URL, make_url

from src.database.models import (
    Asset,
    AuditLog,
    InventoryMovement,
    InventoryPosition,
    JobExecution,
    MaintenanceLog,
    Notification,
    OutboxDeliveryAttempt,
    OutboxEvent,
    ReliabilityValidationRecord,
    ScheduledJob,
    Ticket,
    TicketEscalationEvent,
    TicketSlaEvent,
    User,
    WorkOrder,
)
from src.database.session import build_engine, get_session_factory
from src.repositories.postgres_operations import PostgresOperationsRepository

_DESTRUCTIVE_FLAG = "PM8_ALLOW_DESTRUCTIVE_TESTS"
_MANIFEST_VERSION = 1
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

VALIDATED_MODELS = {
    "users": User,
    "assets": Asset,
    "tickets": Ticket,
    "ticket_sla_events": TicketSlaEvent,
    "ticket_escalation_events": TicketEscalationEvent,
    "work_orders": WorkOrder,
    "maintenance_logs": MaintenanceLog,
    "inventory_positions": InventoryPosition,
    "inventory_movements": InventoryMovement,
    "scheduled_jobs": ScheduledJob,
    "job_executions": JobExecution,
    "outbox_events": OutboxEvent,
    "outbox_delivery_attempts": OutboxDeliveryAttempt,
    "notifications": Notification,
    "audit_logs": AuditLog,
}


@dataclass(frozen=True)
class PgCommands:
    dump: tuple[str, ...]
    create_restore_database: tuple[str, ...]
    restore: tuple[str, ...]
    drop_restore_database: tuple[str, ...]


def build_pg_commands(
    source_url: str,
    restore_database: str,
    archive_path: Path,
    *,
    docker_container: str | None = None,
) -> PgCommands:
    """Build argument arrays without embedding a password."""

    source = _validated_source_url(source_url)
    source_database = source.database or ""
    user = unquote(source.username or "")
    if docker_container:
        prefix = ("docker", "exec", "-i", docker_container)
        return PgCommands(
            dump=prefix
            + (
                "pg_dump",
                "-U",
                user,
                "-d",
                source_database,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
            ),
            create_restore_database=prefix
            + ("createdb", "-U", user, restore_database),
            restore=prefix
            + (
                "pg_restore",
                "-U",
                user,
                "-d",
                restore_database,
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
            ),
            drop_restore_database=prefix
            + ("dropdb", "-U", user, "--if-exists", restore_database),
        )
    host = source.host or "localhost"
    port = str(source.port or 5432)
    common = ("--host", host, "--port", port, "--username", user)
    return PgCommands(
        dump=(
            "pg_dump",
            *common,
            "--dbname",
            source_database,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(archive_path),
        ),
        create_restore_database=(
            "createdb",
            *common,
            restore_database,
        ),
        restore=(
            "pg_restore",
            *common,
            "--dbname",
            restore_database,
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            str(archive_path),
        ),
        drop_restore_database=("dropdb", *common, "--if-exists", restore_database),
    )


def run_backup_restore_drill(
    *,
    source_url: str,
    restore_database: str,
    output_dir: Path,
    docker_container: str | None = None,
    record_validation: bool = True,
) -> dict[str, Any]:
    """Dump, checksum, restore, validate, record evidence, and remove restore DB."""

    if os.getenv(_DESTRUCTIVE_FLAG) != "true":
        raise RuntimeError(f"Restore drill requires {_DESTRUCTIVE_FLAG}=true.")
    source = _validated_source_url(source_url)
    _validate_restore_database(source.database or "", restore_database)
    resolved_output = _validated_output_dir(output_dir)
    resolved_output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = resolved_output / f"postgresql-{stamp}-{uuid4().hex[:8]}.dump"
    manifest_path = archive.with_suffix(".manifest.json")
    commands = build_pg_commands(
        source_url,
        restore_database,
        archive,
        docker_container=docker_container,
    )
    environment = _pg_environment(source)
    restore_created = False
    restore_engine = None
    try:
        if docker_container:
            with archive.open("wb") as output:
                _run(commands.dump, env=environment, stdout=output)
        else:
            _run(commands.dump, env=environment)
        checksum = sha256_file(archive)
        source_counts = collect_row_counts(source_url)
        source_revision = current_revision(source_url)
        manifest = {
            "manifest_version": _MANIFEST_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_database": source.database,
            "source_revision": source_revision,
            "archive_filename": archive.name,
            "archive_size_bytes": archive.stat().st_size,
            "sha256": checksum,
            "row_counts": source_counts,
            "attachment_bytes_included": False,
            "scope": "postgresql-schema-and-data",
            "pitr_claim": False,
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        if sha256_file(archive) != checksum:
            raise RuntimeError("Backup checksum changed before restore.")

        _run(commands.create_restore_database, env=environment)
        restore_created = True
        if docker_container:
            with archive.open("rb") as source_stream:
                _run(commands.restore, env=environment, stdin=source_stream)
        else:
            _run(commands.restore, env=environment)
        restore_url = _replace_database(source, restore_database).render_as_string(
            hide_password=False
        )
        restored_counts = collect_row_counts(restore_url)
        if restored_counts != source_counts:
            raise RuntimeError(
                "Restored critical row counts do not match the backup source."
            )
        restored_revision = current_revision(restore_url)
        if restored_revision != source_revision:
            raise RuntimeError("Restored Alembic revision does not match the source.")
        integrity = validate_critical_integrity(restore_url)
        restore_factory = get_session_factory(restore_url)
        restore_engine = restore_factory.kw["bind"]
        PostgresOperationsRepository(restore_factory).check_health()
        application_smoke = _application_smoke(restore_url)
        restore_engine.dispose()
        report = {
            "status": "passed",
            "source_revision": source_revision,
            "restored_revision": restored_revision,
            "row_counts": restored_counts,
            "integrity": integrity,
            "application_smoke": application_smoke,
            "sha256": checksum,
            "archive": str(archive),
            "manifest": str(manifest_path),
            "restore_database": restore_database,
            "attachment_bytes_validated": False,
            "production_readiness_claim": False,
        }
        if record_validation:
            _record_validation(
                source_url,
                source_revision=source_revision,
                checksum=checksum,
                summary={
                    "validated_table_count": len(restored_counts),
                    "integrity_check_count": len(integrity),
                    "attachment_bytes_validated": False,
                },
            )
        return report
    finally:
        if restore_engine is not None:
            restore_engine.dispose()
        if restore_created:
            _run(commands.drop_restore_database, env=environment)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def collect_row_counts(database_url: str) -> dict[str, int]:
    engine = build_engine(database_url)
    try:
        with engine.connect() as connection:
            return {
                name: int(
                    connection.scalar(select(func.count()).select_from(model)) or 0
                )
                for name, model in VALIDATED_MODELS.items()
            }
    finally:
        engine.dispose()


def current_revision(database_url: str) -> str:
    engine = build_engine(database_url)
    try:
        with engine.connect() as connection:
            value = connection.scalar(text("SELECT version_num FROM alembic_version"))
            if not value:
                raise RuntimeError("Database has no Alembic revision.")
            return str(value)
    finally:
        engine.dispose()


def validate_critical_integrity(database_url: str) -> dict[str, int]:
    engine = build_engine(database_url)
    checks = {
        "negative_on_hand": (
            "SELECT count(*) FROM inventory_positions WHERE on_hand_quantity < 0"
        ),
        "negative_reserved": (
            "SELECT count(*) FROM inventory_positions WHERE reserved_quantity < 0"
        ),
        "negative_available": (
            "SELECT count(*) FROM inventory_positions "
            "WHERE on_hand_quantity - reserved_quantity < 0"
        ),
        "orphan_job_execution": (
            "SELECT count(*) FROM job_executions e LEFT JOIN scheduled_jobs j "
            "ON j.job_key=e.job_key WHERE j.job_key IS NULL"
        ),
        "orphan_outbox_attempt": (
            "SELECT count(*) FROM outbox_delivery_attempts a "
            "LEFT JOIN outbox_events e ON e.id=a.outbox_event_id WHERE e.id IS NULL"
        ),
        "orphan_notification_owner": (
            "SELECT count(*) FROM notifications n LEFT JOIN users u "
            "ON u.id=n.recipient_user_id WHERE u.id IS NULL"
        ),
    }
    try:
        with engine.connect() as connection:
            result = {
                name: int(connection.scalar(text(query)) or 0)
                for name, query in checks.items()
            }
        if any(result.values()):
            raise RuntimeError("Restored database failed critical integrity checks.")
        return result
    finally:
        engine.dispose()


def _record_validation(
    database_url: str,
    *,
    source_revision: str,
    checksum: str,
    summary: dict[str, object],
) -> None:
    factory = get_session_factory(database_url)
    with factory() as session, session.begin():
        session.add(
            ReliabilityValidationRecord(
                id=uuid4(),
                validation_type="backup_restore",
                status="passed",
                performed_at=datetime.now(timezone.utc),
                source_revision=source_revision,
                backup_checksum=checksum,
                summary=summary,
                recorded_by_user_id=None,
            )
        )


def _application_smoke(database_url: str) -> dict[str, object]:
    """Run FastAPI lifespan and safe health routes against the restored database."""

    from fastapi.testclient import TestClient

    from src.api.main import create_app
    from src.api.services import get_processed_data_service
    from src.config.settings import get_settings
    from src.database.session import clear_database_caches, get_engine
    from src.operations.service import build_operations_service

    original_database_url = os.environ.get("DATABASE_URL")
    original_environment = os.environ.get("APP_ENVIRONMENT")
    os.environ["DATABASE_URL"] = database_url
    os.environ["APP_ENVIRONMENT"] = "test"
    get_settings.cache_clear()
    clear_database_caches()
    get_processed_data_service.cache_clear()
    build_operations_service.cache_clear()
    try:
        with TestClient(create_app()) as client:
            live = client.get("/health/live")
            ready = client.get("/health/ready")
        ready_body = ready.json()
        if (
            live.status_code != 200
            or ready.status_code != 200
            or ready_body.get("database_ready") is not True
        ):
            raise RuntimeError("Restored-database FastAPI health smoke failed.")
        return {
            "liveness_status": live.status_code,
            "readiness_status": ready.status_code,
            "database_ready": True,
        }
    finally:
        try:
            get_engine(database_url).dispose()
        finally:
            get_processed_data_service.cache_clear()
            build_operations_service.cache_clear()
            clear_database_caches()
            get_settings.cache_clear()
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url
            if original_environment is None:
                os.environ.pop("APP_ENVIRONMENT", None)
            else:
                os.environ["APP_ENVIRONMENT"] = original_environment


def _validated_source_url(value: str) -> URL:
    parsed = make_url(value)
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("DATABASE_URL must use postgresql+psycopg://.")
    if not parsed.database or not parsed.username:
        raise ValueError("DATABASE_URL must include a database and username.")
    return parsed


def _validate_restore_database(source_database: str, restore_database: str) -> None:
    if restore_database == source_database:
        raise ValueError("Restore database must differ from the source database.")
    if not restore_database.endswith("_restore"):
        raise ValueError("Restore database name must end with _restore.")
    if not restore_database.replace("_", "").isalnum():
        raise ValueError("Restore database contains unsupported characters.")


def _validated_output_dir(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == _REPOSITORY_ROOT or resolved.is_relative_to(_REPOSITORY_ROOT):
        raise ValueError("Backup output must be outside the repository.")
    return resolved


def _replace_database(source: URL, database: str) -> URL:
    return source.set(database=database)


def _pg_environment(source: URL) -> dict[str, str]:
    environment = os.environ.copy()
    if source.password:
        environment["PGPASSWORD"] = unquote(source.password)
    return environment


def _run(
    command: tuple[str, ...],
    *,
    env: dict[str, str],
    stdin=None,
    stdout=None,
) -> None:
    subprocess.run(
        command,
        env=env,
        stdin=stdin,
        stdout=stdout,
        stderr=subprocess.PIPE,
        check=True,
        timeout=600,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--restore-database", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--docker-container")
    parser.add_argument("--no-record-validation", action="store_true")
    args = parser.parse_args()
    database_url = os.getenv(args.database_url_env)
    if not database_url:
        raise RuntimeError(f"{args.database_url_env} is required.")
    report = run_backup_restore_drill(
        source_url=database_url,
        restore_database=args.restore_database,
        output_dir=args.output_dir,
        docker_container=args.docker_container,
        record_validation=not args.no_record_validation,
    )
    print(
        f"Backup restore drill passed: revision={report['source_revision']} "
        f"tables={len(report['row_counts'])}"
    )


if __name__ == "__main__":
    main()
