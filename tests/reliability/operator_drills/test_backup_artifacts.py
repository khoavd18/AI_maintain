"""Behavior contract for immutable operator-drill backup artifacts."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import hashlib
from inspect import signature
from pathlib import Path

import pytest

from src.reliability import drills
from src.reliability.operator_drills import backup_artifacts
from src.reliability.drills import (
    VALIDATED_BACKUP_INDEX_NAME,
    BackupArtifactError,
    BackupArtifactResult,
    BackupChecksumMismatchError,
    BackupRetentionSelection,
    BackupVerificationReport,
    create_atomic_backup_artifact,
    read_validated_backup_index,
    select_backup_retention,
    verify_backup_artifact,
)


def _artifact(name: str, created_at: datetime) -> BackupArtifactResult:
    return BackupArtifactResult(
        artifact_name=name,
        metadata_name=f"{name}.metadata.json",
        created_at=created_at,
        size_bytes=7,
        sha256="a" * 64,
    )


def test_backup_artifact_signatures_and_historical_bindings_are_stable() -> None:
    assert list(signature(create_atomic_backup_artifact).parameters) == [
        "allowed_root",
        "artifact_name",
        "writer",
        "expected_sha256",
        "created_at",
    ]
    assert list(signature(verify_backup_artifact).parameters) == [
        "allowed_root",
        "artifact_name",
    ]
    assert list(signature(read_validated_backup_index).parameters) == ["allowed_root"]
    assert list(signature(select_backup_retention).parameters) == ["artifacts", "keep_count"]
    for name, value in (
        ("BackupArtifactError", BackupArtifactError),
        ("BackupChecksumMismatchError", BackupChecksumMismatchError),
        ("BackupArtifactResult", BackupArtifactResult),
        ("BackupVerificationReport", BackupVerificationReport),
        ("BackupRetentionSelection", BackupRetentionSelection),
        ("create_atomic_backup_artifact", create_atomic_backup_artifact),
        ("verify_backup_artifact", verify_backup_artifact),
        ("read_validated_backup_index", read_validated_backup_index),
        ("select_backup_retention", select_backup_retention),
    ):
        assert getattr(drills, name) is value


def test_backup_artifact_owner_and_failure_injection_facade_are_explicit() -> None:
    assert drills.BackupArtifactError is backup_artifacts.BackupArtifactError
    assert drills.BackupChecksumMismatchError is backup_artifacts.BackupChecksumMismatchError
    assert drills.BackupArtifactResult is backup_artifacts.BackupArtifactResult
    assert drills.BackupVerificationReport is backup_artifacts.BackupVerificationReport
    assert drills.BackupRetentionSelection is backup_artifacts.BackupRetentionSelection
    assert drills.verify_backup_artifact is backup_artifacts.verify_backup_artifact
    assert drills.read_validated_backup_index is backup_artifacts.read_validated_backup_index
    assert drills.select_backup_retention is backup_artifacts.select_backup_retention
    assert drills._create_atomic_backup_artifact is backup_artifacts._create_atomic_backup_artifact
    assert (
        drills._publish_validated_backup_index is backup_artifacts._publish_validated_backup_index
    )
    assert signature(drills.create_atomic_backup_artifact) == signature(
        backup_artifacts.create_atomic_backup_artifact
    )


def test_backup_result_serialization_and_frozen_value_contract_are_exact() -> None:
    created_at = datetime(2026, 8, 9, 12, 34, 56, tzinfo=timezone.utc)
    result = BackupArtifactResult(
        artifact_name="pilot.dump",
        metadata_name="pilot.dump.metadata.json",
        created_at=created_at,
        size_bytes=7,
        sha256="a" * 64,
    )

    assert result.as_dict() == {
        "artifact_name": "pilot.dump",
        "metadata_name": "pilot.dump.metadata.json",
        "created_at": "2026-08-09T12:34:56Z",
        "size_bytes": 7,
        "sha256": "a" * 64,
    }
    with pytest.raises(FrozenInstanceError):
        result.size_bytes = 8  # type: ignore[misc]


def test_missing_validated_index_is_read_only_and_returns_none(tmp_path: Path) -> None:
    root = tmp_path / "not-created"

    assert read_validated_backup_index(allowed_root=root) is None
    assert not root.exists()


@pytest.mark.parametrize(
    "artifact_name",
    [
        "../pilot.dump",
        "pilot/backup.dump",
        VALIDATED_BACKUP_INDEX_NAME,
        "pilot.partial",
        "pilot.metadata.json",
        "a" * 161,
    ],
)
def test_backup_creation_rejects_unsafe_or_reserved_names_before_writer(
    tmp_path: Path,
    artifact_name: str,
) -> None:
    calls = 0

    def writer(path: Path) -> None:
        nonlocal calls
        calls += 1
        path.write_bytes(b"backup")

    with pytest.raises(ValueError):
        create_atomic_backup_artifact(
            allowed_root=tmp_path,
            artifact_name=artifact_name,
            writer=writer,
        )
    assert calls == 0


def test_backup_checksum_input_and_naive_timestamp_fail_before_publication(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match="^SHA-256 value must contain 64 lowercase hexadecimal characters[.]$",
    ):
        create_atomic_backup_artifact(
            allowed_root=tmp_path,
            artifact_name="pilot.dump",
            writer=lambda path: path.write_bytes(b"backup"),
            expected_sha256="A" * 64,
        )
    assert list(tmp_path.iterdir()) == []

    with pytest.raises(ValueError, match="^Timestamp must be timezone-aware[.]$"):
        create_atomic_backup_artifact(
            allowed_root=tmp_path,
            artifact_name="pilot.dump",
            writer=lambda path: path.write_bytes(b"backup"),
            created_at=datetime(2026, 8, 9),
        )
    assert list(tmp_path.iterdir()) == []


def test_backup_writer_failure_maps_exception_and_removes_partial_files(tmp_path: Path) -> None:
    failure = RuntimeError("secret writer detail")

    def writer(path: Path) -> None:
        path.write_bytes(b"partial")
        raise failure

    with pytest.raises(
        BackupArtifactError,
        match="^Backup writer failed; no artifact was published[.]$",
    ) as raised:
        create_atomic_backup_artifact(
            allowed_root=tmp_path,
            artifact_name="pilot.dump",
            writer=writer,
        )
    assert raised.value.__cause__ is None
    assert list(tmp_path.iterdir()) == []


def test_committed_pair_and_index_round_trip_without_mutating_inputs(tmp_path: Path) -> None:
    payload = b"backup"
    expected = hashlib.sha256(payload).hexdigest()
    created_at = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)

    result = create_atomic_backup_artifact(
        allowed_root=tmp_path,
        artifact_name="pilot.dump",
        writer=lambda path: path.write_bytes(payload),
        expected_sha256=expected,
        created_at=created_at,
    )

    assert result == read_validated_backup_index(allowed_root=tmp_path)
    assert verify_backup_artifact(
        allowed_root=tmp_path,
        artifact_name="pilot.dump",
    ) == BackupVerificationReport(
        artifact_name="pilot.dump",
        metadata_name="pilot.dump.metadata.json",
        valid=True,
        reason="validated",
        size_bytes=len(payload),
        sha256=expected,
    )
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        VALIDATED_BACKUP_INDEX_NAME,
        "pilot.dump",
        "pilot.dump.metadata.json",
    ]


def test_retention_is_deterministic_non_mutating_and_rejects_invalid_inputs() -> None:
    older = _artifact("older.dump", datetime(2026, 8, 8, tzinfo=timezone.utc))
    same_time_a = _artifact("a.dump", datetime(2026, 8, 9, tzinfo=timezone.utc))
    same_time_b = _artifact("b.dump", datetime(2026, 8, 9, tzinfo=timezone.utc))
    records = [older, same_time_a, same_time_b]

    assert select_backup_retention(records, keep_count=2) == BackupRetentionSelection(
        retain=("b.dump", "a.dump"),
        expire=("older.dump",),
    )
    assert records == [older, same_time_a, same_time_b]
    with pytest.raises(ValueError, match="^Backup retention must keep at least one"):
        select_backup_retention(records, keep_count=0)
    with pytest.raises(ValueError, match="^Backup retention candidates contain duplicate names"):
        select_backup_retention([older, older], keep_count=1)
