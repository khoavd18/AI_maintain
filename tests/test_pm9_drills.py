"""Focused safe-default tests for PM9 injected reliability drill helpers."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from threading import Event, Thread
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from src.reliability import drills
from src.reliability.drills import (
    DISK_ACTION_ESCALATE_CRITICAL,
    DISK_ACTION_NONE,
    DISK_ACTION_RAISE_WARNING,
    DISK_ACTION_RECOVER,
    VALIDATED_BACKUP_INDEX_NAME,
    AttachmentArchiveEntry,
    AttachmentArchiveIntegrityError,
    BackupArtifactError,
    BackupArtifactResult,
    BackupChecksumMismatchError,
    DiskAlertCycle,
    DiskCapacity,
    assess_attachment_bytes,
    create_atomic_backup_artifact,
    create_attachment_archive,
    inspect_attachment_archive,
    read_validated_backup_index,
    restore_attachment_archive,
    select_backup_retention,
    verify_backup_artifact,
)


def test_disk_drill_uses_injected_capacity_and_deduplicates_cycle() -> None:
    observations = iter(
        (
            DiskCapacity(total_bytes=1_000, free_bytes=150),
            DiskCapacity(total_bytes=1_000, free_bytes=140),
            DiskCapacity(total_bytes=1_000, free_bytes=90),
            DiskCapacity(total_bytes=1_000, free_bytes=80),
            DiskCapacity(total_bytes=1_000, free_bytes=300),
            DiskCapacity(total_bytes=1_000, free_bytes=150),
        )
    )
    provider_calls = 0

    def controlled_provider() -> DiskCapacity:
        nonlocal provider_calls
        provider_calls += 1
        return next(observations)

    cycle = DiskAlertCycle(
        target_label="pilot_storage",
        warning_free_percent=20,
        critical_free_percent=10,
    )
    reports = [cycle.evaluate(controlled_provider) for _ in range(6)]

    assert [report.severity for report in reports] == [
        "warning",
        "warning",
        "critical",
        "critical",
        "healthy",
        "warning",
    ]
    assert [report.runbook_action for report in reports] == [
        DISK_ACTION_RAISE_WARNING,
        DISK_ACTION_NONE,
        DISK_ACTION_ESCALATE_CRITICAL,
        DISK_ACTION_NONE,
        DISK_ACTION_RECOVER,
        DISK_ACTION_RAISE_WARNING,
    ]
    assert provider_calls == 6
    assert reports[0].as_dict() == {
        "target_label": "pilot_storage",
        "free_percent": 15.0,
        "used_percent": 85.0,
        "severity": "warning",
        "runbook_action": DISK_ACTION_RAISE_WARNING,
    }
    assert all("\\" not in json.dumps(report.as_dict()) for report in reports)
    assert all(":/" not in json.dumps(report.as_dict()) for report in reports)


def test_disk_drill_classifies_direct_critical_without_real_disk_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_disk_usage(*_args, **_kwargs):
        raise AssertionError("real disk usage must not be queried")

    monkeypatch.setattr("shutil.disk_usage", forbidden_disk_usage)
    cycle = DiskAlertCycle(
        target_label="backup_volume",
        warning_free_percent=25,
        critical_free_percent=10,
    )
    report = cycle.evaluate(lambda: DiskCapacity(total_bytes=2_000, free_bytes=100))
    assert report.severity == "critical"
    assert report.free_percent == 5.0
    assert report.runbook_action != DISK_ACTION_NONE

    with pytest.raises(ValueError, match="opaque"):
        DiskAlertCycle(
            target_label=r"C:\private\backup",
            warning_free_percent=25,
            critical_free_percent=10,
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


def test_attachment_archive_restores_non_empty_generated_bytes(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "source"
    archive_root = tmp_path / "archives"
    restore_root = tmp_path / "restores"
    body = b"%PDF-1.7\nnon-sensitive PM9 generated attachment\n"
    entry = _write_attachment(
        storage_root,
        key="assets/ab/ab000000000000000000000000000001.pdf",
        body=body,
    )

    archive_report = create_attachment_archive(
        storage_root=storage_root,
        entries=(entry,),
        archive_root=archive_root,
        archive_name="attachments.zip",
        created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
    )
    assert archive_report.attachment_count == 1
    assert archive_report.attachment_bytes == len(body)
    assert archive_report.postgresql_metadata_backed_up is False
    assert str(tmp_path) not in repr(archive_report)

    restore_report = restore_attachment_archive(
        archive_path=archive_root / archive_report.archive_name,
        restore_root=restore_root,
        restore_label="pm9_restore",
        expected_entries=(entry,),
    )
    assert restore_report.restored_count == 1
    assert restore_report.missing_count == 0
    assert restore_report.postgresql_metadata_restored is False
    assert (restore_root / "pm9_restore" / Path(*entry.storage_key.split("/"))).read_bytes() == body
    assert assess_attachment_bytes(
        storage_root=restore_root / "pm9_restore",
        entries=(entry,),
    ).valid


def test_attachment_archive_streams_source_with_bounded_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root = tmp_path / "source"
    target_key = "assets/ab/ab000000000000000000000000000008.pdf"
    chunk_size = 1024 * 1024
    body = b"%PDF-" + (b"x" * (chunk_size * 2 + 17))
    entry = _write_attachment(storage_root, key=target_key, body=body)
    target = storage_root / Path(*target_key.split("/"))
    real_open = Path.open
    observed_read_sizes: list[int] = []

    class BoundedReader:
        def __init__(self, wrapped) -> None:
            self._wrapped = wrapped

        def __enter__(self):
            self._wrapped.__enter__()
            return self

        def __exit__(self, *args):
            return self._wrapped.__exit__(*args)

        def read(self, size: int = -1):
            if size <= 0 or size > chunk_size:
                raise AssertionError("attachment reads must remain bounded")
            observed_read_sizes.append(size)
            return self._wrapped.read(size)

        def __getattr__(self, name: str):
            return getattr(self._wrapped, name)

    def bounded_open(path: Path, *args, **kwargs):
        opened = real_open(path, *args, **kwargs)
        mode = args[0] if args else kwargs.get("mode", "r")
        if path.resolve() == target.resolve() and mode == "rb":
            return BoundedReader(opened)
        return opened

    monkeypatch.setattr(Path, "open", bounded_open)
    report = create_attachment_archive(
        storage_root=storage_root,
        entries=(entry,),
        archive_root=tmp_path / "archives",
        archive_name="streamed-attachments.zip",
    )

    assert report.attachment_bytes == len(body)
    assert len(observed_read_sizes) >= 6
    assert set(observed_read_sizes) == {chunk_size}
    assert inspect_attachment_archive(
        archive_path=tmp_path / "archives" / report.archive_name,
        expected_entries=(entry,),
    ).valid


def test_attachment_assessment_detects_missing_mismatch_and_orphan(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "attachments"
    valid_body = b"\x89PNG\r\n\x1a\nvalid-generated"
    valid = _write_attachment(
        storage_root,
        key="assets/ab/ab000000000000000000000000000002.png",
        body=valid_body,
    )
    mismatch = _write_attachment(
        storage_root,
        key="work-orders/cd/cd000000000000000000000000000003.pdf",
        body=b"%PDF-generated-original",
    )
    mismatch_path = storage_root / Path(*mismatch.storage_key.split("/"))
    mismatch_path.write_bytes(b"%PDF-generated-corrupt")
    missing = AttachmentArchiveEntry(
        storage_key="inventory/ef/ef000000000000000000000000000004.jpg",
        sha256=hashlib.sha256(b"\xff\xd8\xffmissing").hexdigest(),
    )
    orphan = storage_root / "inventory" / "aa" / ("aa" + "0" * 30 + ".jpg")
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"\xff\xd8\xfforphan")

    report = assess_attachment_bytes(
        storage_root=storage_root,
        entries=(valid, mismatch, missing),
    )
    assert report.expected_count == 3
    assert report.ok_count == 1
    assert report.missing_count == 1
    assert report.checksum_mismatch_count == 1
    assert report.orphan_count == 1
    assert report.valid is False


def test_attachment_archive_detects_corrupt_bytes_and_external_orphan(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "source"
    archive_root = tmp_path / "archives"
    entry = _write_attachment(
        storage_root,
        key="assets/ab/ab000000000000000000000000000005.pdf",
        body=b"%PDF-generated",
    )
    report = create_attachment_archive(
        storage_root=storage_root,
        entries=(entry,),
        archive_root=archive_root,
        archive_name="attachments.zip",
    )
    archive_path = archive_root / report.archive_name
    with ZipFile(archive_path, mode="r") as source:
        manifest = source.read("attachment-manifest.json")
    with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("attachment-manifest.json", manifest)
        archive.writestr(
            f"attachment-bytes/{entry.storage_key}",
            b"%PDF-tampered",
        )
    inspection = inspect_attachment_archive(
        archive_path=archive_path,
        expected_entries=(entry,),
    )
    assert inspection.checksum_mismatch_count == 1
    assert inspection.valid is False
    with pytest.raises(AttachmentArchiveIntegrityError):
        restore_attachment_archive(
            archive_path=archive_path,
            restore_root=tmp_path / "restore",
            restore_label="corrupt_restore",
            expected_entries=(entry,),
        )
    assert not (tmp_path / "restore" / "corrupt_restore").exists()

    other = AttachmentArchiveEntry(
        storage_key="assets/ab/ab000000000000000000000000000006.pdf",
        sha256="0" * 64,
    )
    missing_and_orphan = inspect_attachment_archive(
        archive_path=archive_path,
        expected_entries=(other,),
    )
    assert missing_and_orphan.missing_count == 1
    assert missing_and_orphan.orphan_count == 1


def test_attachment_restore_rejects_archive_traversal_and_cleans_staging(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "malicious.zip"
    entry = AttachmentArchiveEntry(
        storage_key="assets/ab/ab000000000000000000000000000007.pdf",
        sha256=hashlib.sha256(b"%PDF-safe").hexdigest(),
    )
    manifest = {
        "archive_version": 1,
        "created_at": "2026-07-26T00:00:00Z",
        "entries": [
            {
                "sha256": entry.sha256,
                "size_bytes": 9,
                "storage_key": entry.storage_key,
            }
        ],
    }
    with ZipFile(archive_path, mode="w") as archive:
        archive.writestr(
            "attachment-manifest.json",
            json.dumps(manifest),
        )
        archive.writestr("../outside.pdf", b"%PDF-unsafe")

    restore_root = tmp_path / "restore"
    with pytest.raises(AttachmentArchiveIntegrityError, match="unsafe"):
        restore_attachment_archive(
            archive_path=archive_path,
            restore_root=restore_root,
            restore_label="traversal_restore",
            expected_entries=(entry,),
        )
    assert not (tmp_path / "outside.pdf").exists()
    assert not (restore_root / "traversal_restore").exists()
    assert list(restore_root.glob("*.partial")) == []
    assert list(restore_root.glob(".*.partial")) == []


def _write_attachment(
    root: Path,
    *,
    key: str,
    body: bytes,
) -> AttachmentArchiveEntry:
    target = root / Path(*key.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    return AttachmentArchiveEntry(
        storage_key=key,
        sha256=hashlib.sha256(body).hexdigest(),
    )
