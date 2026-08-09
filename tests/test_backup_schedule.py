"""Tests for atomic operator-driven PM9 backup publication."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

import pytest

from src.reliability import backup_schedule
from src.reliability.backup_schedule import (
    ScheduledBackupReport,
    failed_backup_report,
    run_scheduled_backup,
)
from src.reliability.backup_restore import _validated_output_dir
from src.reliability.drills import (
    VALIDATED_BACKUP_INDEX_NAME,
    BackupArtifactError,
    read_validated_backup_index,
)


def _source_url() -> str:
    return (
        "postgresql+psycopg://pilot_user:synthetic-secret@database.example.test:5432/pilot_database"
    )


def test_scheduled_backup_publishes_only_validated_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_SCHEDULED_BACKUP", "true")

    def runner(command, **_kwargs):
        file_index = command.index("--file") + 1
        Path(command[file_index]).write_bytes(b"synthetic-postgresql-backup")
        return subprocess.CompletedProcess(command, 0)

    report = run_scheduled_backup(
        source_url=_source_url(),
        allowed_root=tmp_path,
        target_label="pilot_primary",
        retention_keep_count=7,
        runner=runner,
        now=datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert report.status == "passed"
    assert report.validated is True
    assert report.restore_validated is False
    assert re.fullmatch(
        r"postgresql-pilot_primary-20260726T120000000000Z-[0-9a-f]{32}\.dump",
        report.artifact_name or "",
    )
    assert (tmp_path / report.artifact_name).is_file()
    assert (tmp_path / report.metadata_name).is_file()
    assert (tmp_path / VALIDATED_BACKUP_INDEX_NAME).is_file()
    indexed = read_validated_backup_index(allowed_root=tmp_path)
    assert indexed is not None
    assert indexed.artifact_name == report.artifact_name
    assert indexed.metadata_name == report.metadata_name


def test_scheduled_backup_names_resist_same_timestamp_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_SCHEDULED_BACKUP", "true")
    nonces = iter(("1" * 32, "2" * 32))
    monkeypatch.setattr(
        backup_schedule,
        "uuid4",
        lambda: SimpleNamespace(hex=next(nonces)),
    )

    def runner(command, **_kwargs):
        file_index = command.index("--file") + 1
        Path(command[file_index]).write_bytes(b"synthetic-postgresql-backup")
        return subprocess.CompletedProcess(command, 0)

    timestamp = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    first = run_scheduled_backup(
        source_url=_source_url(),
        allowed_root=tmp_path,
        target_label="pilot_primary",
        retention_keep_count=7,
        runner=runner,
        now=timestamp,
    )
    second = run_scheduled_backup(
        source_url=_source_url(),
        allowed_root=tmp_path,
        target_label="pilot_primary",
        retention_keep_count=7,
        runner=runner,
        now=timestamp,
    )

    assert first.artifact_name != second.artifact_name
    assert first.artifact_name is not None
    assert second.artifact_name is not None
    assert first.artifact_name.endswith(f"-{'1' * 32}.dump")
    assert second.artifact_name.endswith(f"-{'2' * 32}.dump")
    assert (tmp_path / first.artifact_name).is_file()
    assert (tmp_path / second.artifact_name).is_file()
    indexed = read_validated_backup_index(allowed_root=tmp_path)
    assert indexed is not None
    assert indexed.artifact_name == second.artifact_name


def test_failed_backup_preserves_last_valid_and_removes_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_SCHEDULED_BACKUP", "true")
    existing = tmp_path / "last-validated.dump"
    existing.write_bytes(b"last-valid")

    def runner(_command, **_kwargs):
        raise subprocess.CalledProcessError(1, "pg_dump")

    with pytest.raises(BackupArtifactError, match="no artifact"):
        run_scheduled_backup(
            source_url=_source_url(),
            allowed_root=tmp_path,
            target_label="pilot_primary",
            retention_keep_count=7,
            runner=runner,
            now=datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc),
        )

    assert existing.read_bytes() == b"last-valid"
    assert not list(tmp_path.glob("*.partial"))
    report = failed_backup_report(
        target_label="pilot_primary",
        retention_keep_count=7,
    )
    assert report.status == "failed"
    assert report.artifact_name is None
    assert "synthetic-secret" not in str(report.as_dict())


def test_backup_root_cannot_be_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_SCHEDULED_BACKUP", "true")
    with pytest.raises(ValueError, match="outside"):
        run_scheduled_backup(
            source_url=_source_url(),
            allowed_root=Path.cwd(),
            target_label="pilot_primary",
            retention_keep_count=7,
        )


def test_restore_backup_output_rejects_repository_from_any_working_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repository_root / "src")

    with pytest.raises(ValueError, match="outside"):
        _validated_output_dir(repository_root / "local-backups")


def test_cli_reads_protected_environment_and_uses_postgresql_subdirectory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_file = tmp_path / "pilot.env"
    backup_root = tmp_path / "backups"
    environment_file.write_text(
        "\n".join(
            (
                f"DATABASE_URL={_source_url()}",
                f"PILOT_BACKUP_ROOT={backup_root}",
                "PILOT_BACKUP_RETENTION_COUNT=9",
            )
        ),
        encoding="utf-8",
    )
    observed: dict[str, object] = {}

    def fake_backup(**kwargs):
        observed.update(kwargs)
        return ScheduledBackupReport(
            status="passed",
            target_label="pilot_primary",
            artifact_name="synthetic.dump",
            metadata_name="synthetic.dump.metadata.json",
            size_bytes=10,
            sha256="a" * 64,
            validated=True,
            restore_validated=False,
            retention_keep_count=9,
        )

    monkeypatch.setattr(backup_schedule, "run_scheduled_backup", fake_backup)

    assert (
        backup_schedule.main(
            (
                "--environment-file",
                str(environment_file),
                "--target-label",
                "pilot_primary",
            )
        )
        == 0
    )
    assert observed["allowed_root"] == backup_root / "postgresql"
    assert observed["retention_keep_count"] == 9
