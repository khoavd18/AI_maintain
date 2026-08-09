"""Operator-driven PostgreSQL backup publication for an OS-level schedule.

This module is not a scheduler and does not add a worker job. It creates one
immutable, checksummed backup pair and atomically advances a validated index
under an explicitly configured root. Restore validation remains the separate
``backup_restore`` drill.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
from typing import BinaryIO
from urllib.parse import unquote
from uuid import uuid4

from sqlalchemy.engine import make_url

from src.reliability.backup_restore import build_pg_commands
from src.reliability.deployment_rehearsal import load_environment_file
from src.reliability.drills import (
    BackupArtifactError,
    BackupArtifactResult,
    create_atomic_backup_artifact,
    verify_backup_artifact,
)

_BACKUP_FLAG = "PM9_ALLOW_SCHEDULED_BACKUP"
_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

Runner = Callable[..., subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]]


@dataclass(frozen=True, slots=True)
class ScheduledBackupReport:
    """Secret-free result suitable for an operator log."""

    status: str
    target_label: str
    artifact_name: str | None
    metadata_name: str | None
    size_bytes: int | None
    sha256: str | None
    validated: bool
    restore_validated: bool
    retention_keep_count: int
    production_readiness_claim: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def run_scheduled_backup(
    *,
    source_url: str,
    allowed_root: Path,
    target_label: str,
    retention_keep_count: int,
    docker_container: str | None = None,
    runner: Runner = subprocess.run,
    now: datetime | None = None,
) -> ScheduledBackupReport:
    """Publish one uniquely named backup and atomically advance its validated index."""

    if os.getenv(_BACKUP_FLAG) != "true":
        raise RuntimeError(f"Scheduled backup requires {_BACKUP_FLAG}=true.")
    if not _LABEL_PATTERN.fullmatch(target_label):
        raise ValueError("Backup target label must be an opaque lowercase identifier.")
    if (
        isinstance(retention_keep_count, bool)
        or not isinstance(retention_keep_count, int)
        or not 1 <= retention_keep_count <= 365
    ):
        raise ValueError("Backup retention count must be between 1 and 365.")
    root = _validated_backup_root(allowed_root)
    source = make_url(source_url)
    if source.drivername != "postgresql+psycopg" or not source.database or not source.username:
        raise ValueError("Backup source must be a complete postgresql+psycopg URL.")
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    artifact_name = (
        f"postgresql-{target_label}-{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex}.dump"
    )

    def writer(partial_path: Path) -> None:
        commands = build_pg_commands(
            source_url,
            "unused_restore",
            partial_path,
            docker_container=docker_container,
        )
        environment = os.environ.copy()
        if source.password:
            environment["PGPASSWORD"] = unquote(source.password)
        if docker_container:
            with partial_path.open("wb") as stream:
                _run_backup_command(
                    commands.dump,
                    environment=environment,
                    runner=runner,
                    stdout=stream,
                )
        else:
            _run_backup_command(
                commands.dump,
                environment=environment,
                runner=runner,
            )

    result = create_atomic_backup_artifact(
        allowed_root=root,
        artifact_name=artifact_name,
        writer=writer,
        created_at=timestamp,
    )
    verification = verify_backup_artifact(
        allowed_root=root,
        artifact_name=result.artifact_name,
    )
    if not verification.valid:
        raise BackupArtifactError(
            "Published backup failed immediate verification; restore is prohibited."
        )
    return _report_from_result(
        result,
        target_label=target_label,
        retention_keep_count=retention_keep_count,
    )


def failed_backup_report(
    *,
    target_label: str,
    retention_keep_count: int,
) -> ScheduledBackupReport:
    """Return a redacted failure marker after a caught controlled backup failure."""

    if not _LABEL_PATTERN.fullmatch(target_label):
        raise ValueError("Backup target label must be an opaque lowercase identifier.")
    return ScheduledBackupReport(
        status="failed",
        target_label=target_label,
        artifact_name=None,
        metadata_name=None,
        size_bytes=None,
        sha256=None,
        validated=False,
        restore_validated=False,
        retention_keep_count=retention_keep_count,
    )


def _report_from_result(
    result: BackupArtifactResult,
    *,
    target_label: str,
    retention_keep_count: int,
) -> ScheduledBackupReport:
    return ScheduledBackupReport(
        status="passed",
        target_label=target_label,
        artifact_name=result.artifact_name,
        metadata_name=result.metadata_name,
        size_bytes=result.size_bytes,
        sha256=result.sha256,
        validated=True,
        restore_validated=False,
        retention_keep_count=retention_keep_count,
    )


def _run_backup_command(
    command: Sequence[str],
    *,
    environment: dict[str, str],
    runner: Runner,
    stdout: BinaryIO | None = None,
) -> None:
    try:
        runner(
            tuple(command),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout or subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BackupArtifactError(
            "PostgreSQL backup command failed; no artifact was published."
        ) from exc


def _validated_backup_root(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == _REPOSITORY_ROOT or resolved.is_relative_to(_REPOSITORY_ROOT):
        raise ValueError("Scheduled backup root must be outside the repository.")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment-file", type=Path)
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--target-label", required=True)
    parser.add_argument("--retention-keep-count", type=int)
    parser.add_argument("--docker-container")
    args = parser.parse_args(argv)
    configured = (
        load_environment_file(args.environment_file) if args.environment_file is not None else {}
    )
    source_url = configured.get(args.database_url_env) or os.getenv(args.database_url_env)
    if not source_url:
        raise RuntimeError(f"{args.database_url_env} is required.")
    backup_root = args.backup_root
    if backup_root is None:
        configured_root = configured.get("PILOT_BACKUP_ROOT")
        if not configured_root:
            raise RuntimeError("PILOT_BACKUP_ROOT or --backup-root is required.")
        backup_root = Path(configured_root) / "postgresql"
    retention_keep_count = args.retention_keep_count
    if retention_keep_count is None:
        configured_retention = configured.get("PILOT_BACKUP_RETENTION_COUNT")
        if not configured_retention:
            raise RuntimeError(
                "PILOT_BACKUP_RETENTION_COUNT or --retention-keep-count is required."
            )
        try:
            retention_keep_count = int(configured_retention)
        except ValueError as exc:
            raise RuntimeError("PILOT_BACKUP_RETENTION_COUNT must be an integer.") from exc
    try:
        report = run_scheduled_backup(
            source_url=source_url,
            allowed_root=backup_root,
            target_label=args.target_label,
            retention_keep_count=retention_keep_count,
            docker_container=args.docker_container,
        )
    except BackupArtifactError:
        report = failed_backup_report(
            target_label=args.target_label,
            retention_keep_count=retention_keep_count,
        )
    print(
        f"PM9 backup status={report.status} target={report.target_label} "
        f"validated={report.validated} restore_validated={report.restore_validated}"
    )
    return 0 if report.validated else 2


if __name__ == "__main__":
    raise SystemExit(main())
