"""Operator-drill tests grouped by atomic protocol."""

from __future__ import annotations

from ._protocol_scenarios import (
    BackupArtifactError,
    BackupArtifactResult,
    BackupChecksumMismatchError,
    Event,
    Path,
    Thread,
    VALIDATED_BACKUP_INDEX_NAME,
    create_atomic_backup_artifact,
    datetime,
    drills,
    json,
    pytest,
    read_validated_backup_index,
    select_backup_retention,
    timedelta,
    timezone,
    verify_backup_artifact,
)


def test_backup_writer_failure_keeps_prior_index_and_removes_partial(
    tmp_path: Path,
) -> None:
    root = tmp_path / "backups"
    first = create_atomic_backup_artifact(
        allowed_root=root,
        artifact_name="pilot-first.dump",
        writer=lambda path: path.write_bytes(b"last-validated-backup"),
        created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
    )
    prior_artifact = (root / first.artifact_name).read_bytes()
    prior_metadata = (root / first.metadata_name).read_bytes()
    prior_index = (root / VALIDATED_BACKUP_INDEX_NAME).read_bytes()

    def failed_writer(path: Path) -> None:
        path.write_bytes(b"incomplete-secret-free-placeholder")
        raise OSError("controlled writer failure")

    with pytest.raises(BackupArtifactError, match="no artifact was published"):
        create_atomic_backup_artifact(
            allowed_root=root,
            artifact_name="pilot-second.dump",
            writer=failed_writer,
        )

    assert (root / first.artifact_name).read_bytes() == prior_artifact
    assert (root / first.metadata_name).read_bytes() == prior_metadata
    assert (root / VALIDATED_BACKUP_INDEX_NAME).read_bytes() == prior_index
    assert not (root / "pilot-second.dump").exists()
    assert list(root.glob("*.partial")) == []
    assert list(root.glob(".*.partial")) == []
    assert not (root / ".backup-publication.lock").exists()


def test_backup_checksum_mismatch_does_not_advance_prior_index(
    tmp_path: Path,
) -> None:
    root = tmp_path / "backups"
    first = create_atomic_backup_artifact(
        allowed_root=root,
        artifact_name="pilot-first.dump",
        writer=lambda path: path.write_bytes(b"validated"),
    )
    prior_artifact = (root / first.artifact_name).read_bytes()
    prior_metadata = (root / first.metadata_name).read_bytes()
    prior_index = (root / VALIDATED_BACKUP_INDEX_NAME).read_bytes()

    with pytest.raises(BackupChecksumMismatchError, match="checksum"):
        create_atomic_backup_artifact(
            allowed_root=root,
            artifact_name="pilot-second.dump",
            writer=lambda path: path.write_bytes(b"corrupt"),
            expected_sha256="0" * 64,
        )

    assert (root / first.artifact_name).read_bytes() == prior_artifact
    assert (root / first.metadata_name).read_bytes() == prior_metadata
    assert (root / VALIDATED_BACKUP_INDEX_NAME).read_bytes() == prior_index
    assert not (root / "pilot-second.dump").exists()
    assert verify_backup_artifact(
        allowed_root=root,
        artifact_name=first.artifact_name,
    ).valid

    (root / first.artifact_name).write_bytes(b"later-corruption")
    verification = verify_backup_artifact(
        allowed_root=root,
        artifact_name=first.artifact_name,
    )
    assert verification.valid is False
    assert verification.reason == "checksum_mismatch"
    with pytest.raises(BackupArtifactError, match="invalid immutable"):
        read_validated_backup_index(allowed_root=root)


def test_backup_metadata_is_allow_listed_and_retention_is_deterministic(
    tmp_path: Path,
) -> None:
    root = tmp_path / "backups"
    created = datetime(2026, 7, 26, tzinfo=timezone.utc)
    result = create_atomic_backup_artifact(
        allowed_root=root,
        artifact_name="pilot.dump",
        writer=lambda path: path.write_bytes(b"backup-without-secret-metadata"),
        created_at=created,
    )
    metadata = json.loads((root / result.metadata_name).read_text(encoding="utf-8"))
    assert set(metadata) == {
        "artifact_name",
        "created_at",
        "manifest_version",
        "sha256",
        "size_bytes",
        "status",
    }
    assert str(tmp_path) not in json.dumps(metadata)
    assert "password" not in json.dumps(metadata).lower()
    index = json.loads((root / VALIDATED_BACKUP_INDEX_NAME).read_text(encoding="utf-8"))
    assert set(index) == {
        "artifact_name",
        "created_at",
        "index_version",
        "metadata_name",
        "sha256",
        "size_bytes",
        "status",
    }
    assert index["artifact_name"] == result.artifact_name
    assert index["metadata_name"] == result.metadata_name
    assert read_validated_backup_index(allowed_root=root) == result

    writer_called = False

    def forbidden_overwrite(_path: Path) -> None:
        nonlocal writer_called
        writer_called = True

    with pytest.raises(BackupArtifactError, match="already exists"):
        create_atomic_backup_artifact(
            allowed_root=root,
            artifact_name=result.artifact_name,
            writer=forbidden_overwrite,
        )
    assert writer_called is False

    older = BackupArtifactResult(
        artifact_name="older.dump",
        metadata_name="older.dump.metadata.json",
        created_at=created - timedelta(days=1),
        size_bytes=1,
        sha256="1" * 64,
    )
    selection = select_backup_retention((older, result), keep_count=1)
    assert selection.retain == ("pilot.dump",)
    assert selection.expire == ("older.dump",)


def test_backup_pair_crash_before_index_replace_keeps_prior_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "backups"
    first = create_atomic_backup_artifact(
        allowed_root=root,
        artifact_name="pilot-first.dump",
        writer=lambda path: path.write_bytes(b"first-validated"),
    )
    prior_index = (root / VALIDATED_BACKUP_INDEX_NAME).read_bytes()

    def controlled_crash(**_kwargs) -> None:
        raise BackupArtifactError("controlled crash before index replacement")

    monkeypatch.setattr(
        drills,
        "_publish_validated_backup_index",
        controlled_crash,
    )
    with pytest.raises(BackupArtifactError, match="controlled crash"):
        create_atomic_backup_artifact(
            allowed_root=root,
            artifact_name="pilot-second.dump",
            writer=lambda path: path.write_bytes(b"second-validated"),
        )

    assert (root / "pilot-second.dump").is_file()
    assert (root / "pilot-second.dump.metadata.json").is_file()
    assert verify_backup_artifact(
        allowed_root=root,
        artifact_name="pilot-second.dump",
    ).valid
    assert (root / VALIDATED_BACKUP_INDEX_NAME).read_bytes() == prior_index
    assert read_validated_backup_index(allowed_root=root) == first


def test_backup_pair_interruption_between_immutable_files_keeps_prior_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "backups"
    first = create_atomic_backup_artifact(
        allowed_root=root,
        artifact_name="pilot-first.dump",
        writer=lambda path: path.write_bytes(b"first-validated"),
    )
    prior_index = (root / VALIDATED_BACKUP_INDEX_NAME).read_bytes()
    real_rename = drills.os.rename

    def interrupted_rename(source, destination) -> None:
        if Path(destination).name == "pilot-second.dump.metadata.json":
            raise OSError("controlled interruption")
        real_rename(source, destination)

    monkeypatch.setattr(drills.os, "rename", interrupted_rename)
    with pytest.raises(BackupArtifactError, match="interrupted"):
        create_atomic_backup_artifact(
            allowed_root=root,
            artifact_name="pilot-second.dump",
            writer=lambda path: path.write_bytes(b"second-validated"),
        )

    assert (root / "pilot-second.dump").is_file()
    assert not (root / "pilot-second.dump.metadata.json").exists()
    assert (root / VALIDATED_BACKUP_INDEX_NAME).read_bytes() == prior_index
    assert read_validated_backup_index(allowed_root=root) == first


def test_overlapping_backup_writers_are_excluded_across_publication_lock(
    tmp_path: Path,
) -> None:
    root = tmp_path / "backups"
    writer_started = Event()
    release_writer = Event()
    results: list[BackupArtifactResult] = []
    failures: list[BaseException] = []

    def slow_writer(path: Path) -> None:
        path.write_bytes(b"first-overlapping-writer")
        writer_started.set()
        if not release_writer.wait(timeout=5):
            raise AssertionError("test did not release the first writer")

    def run_first_writer() -> None:
        try:
            results.append(
                create_atomic_backup_artifact(
                    allowed_root=root,
                    artifact_name="pilot-first.dump",
                    writer=slow_writer,
                )
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    thread = Thread(target=run_first_writer)
    thread.start()
    try:
        assert writer_started.wait(timeout=5)
        with pytest.raises(BackupArtifactError, match="already in progress"):
            create_atomic_backup_artifact(
                allowed_root=root,
                artifact_name="pilot-second.dump",
                writer=lambda path: path.write_bytes(b"second-overlapping-writer"),
            )
    finally:
        release_writer.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert failures == []
    assert len(results) == 1
    assert read_validated_backup_index(allowed_root=root) == results[0]
    assert not (root / "pilot-second.dump").exists()
