"""Behavior contract for path-safe attachment archive drills."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import hashlib
from inspect import signature
from pathlib import Path

import pytest

from src.reliability import drills
from src.reliability.operator_drills import attachment_archives
from src.reliability.drills import (
    AttachmentArchiveEntry,
    AttachmentArchiveError,
    AttachmentArchiveIntegrityError,
    AttachmentArchiveReport,
    AttachmentIntegrityReport,
    AttachmentRestoreReport,
    assess_attachment_bytes,
    create_attachment_archive,
    inspect_attachment_archive,
    restore_attachment_archive,
)


KEY = "assets/ab/ab000000000000000000000000000001.pdf"
BODY = b"%PDF-1.7\ncharacterized attachment\n"
DIGEST = hashlib.sha256(BODY).hexdigest()


def _write_entry(root: Path) -> AttachmentArchiveEntry:
    path = root / Path(*KEY.split("/"))
    path.parent.mkdir(parents=True)
    path.write_bytes(BODY)
    return AttachmentArchiveEntry(storage_key=KEY, sha256=DIGEST)


def test_attachment_archive_signatures_and_historical_bindings_are_stable() -> None:
    assert list(signature(assess_attachment_bytes).parameters) == ["storage_root", "entries"]
    assert list(signature(create_attachment_archive).parameters) == [
        "storage_root",
        "entries",
        "archive_root",
        "archive_name",
        "created_at",
    ]
    assert list(signature(inspect_attachment_archive).parameters) == [
        "archive_path",
        "expected_entries",
    ]
    assert list(signature(restore_attachment_archive).parameters) == [
        "archive_path",
        "restore_root",
        "restore_label",
        "expected_entries",
    ]
    for name, value in (
        ("AttachmentArchiveError", AttachmentArchiveError),
        ("AttachmentArchiveIntegrityError", AttachmentArchiveIntegrityError),
        ("AttachmentArchiveEntry", AttachmentArchiveEntry),
        ("AttachmentIntegrityReport", AttachmentIntegrityReport),
        ("AttachmentArchiveReport", AttachmentArchiveReport),
        ("AttachmentRestoreReport", AttachmentRestoreReport),
        ("assess_attachment_bytes", assess_attachment_bytes),
        ("create_attachment_archive", create_attachment_archive),
        ("inspect_attachment_archive", inspect_attachment_archive),
        ("restore_attachment_archive", restore_attachment_archive),
    ):
        assert getattr(drills, name) is value


def test_attachment_archive_owner_is_the_historical_facade_binding() -> None:
    for name in (
        "AttachmentArchiveError",
        "AttachmentArchiveIntegrityError",
        "AttachmentArchiveEntry",
        "AttachmentIntegrityReport",
        "AttachmentArchiveReport",
        "AttachmentRestoreReport",
        "assess_attachment_bytes",
        "create_attachment_archive",
        "inspect_attachment_archive",
        "restore_attachment_archive",
    ):
        assert getattr(drills, name) is getattr(attachment_archives, name)


@pytest.mark.parametrize(
    "storage_key",
    [
        "../attachment.pdf",
        "/assets/ab/ab000000000000000000000000000001.pdf",
        "assets/AB/ab000000000000000000000000000001.pdf",
        "assets/ab/ab000000000000000000000000000001.exe",
    ],
)
def test_attachment_entry_rejects_non_generated_storage_keys(storage_key: str) -> None:
    with pytest.raises(
        ValueError,
        match="^Attachment storage key is not a generated supported key[.]$",
    ):
        AttachmentArchiveEntry(storage_key=storage_key, sha256=DIGEST)


def test_attachment_entry_preserves_strict_lowercase_checksum_contract() -> None:
    with pytest.raises(
        ValueError,
        match="^SHA-256 value must contain 64 lowercase hexadecimal characters[.]$",
    ):
        AttachmentArchiveEntry(storage_key=KEY, sha256=DIGEST.upper())


def test_attachment_integrity_report_validity_and_frozen_contract_are_exact() -> None:
    empty = AttachmentIntegrityReport(0, 0, 0, 0, 0)
    valid = AttachmentIntegrityReport(1, 1, 0, 0, 0)
    orphaned = AttachmentIntegrityReport(1, 1, 0, 0, 1)

    assert empty.valid is False
    assert valid.valid is True
    assert orphaned.valid is False
    with pytest.raises(FrozenInstanceError):
        valid.ok_count = 0  # type: ignore[misc]


def test_attachment_assessment_is_read_only_and_does_not_mutate_entries(tmp_path: Path) -> None:
    source = tmp_path / "source"
    entry = _write_entry(source)
    entries = [entry]

    assert assess_attachment_bytes(storage_root=source, entries=entries) == (
        AttachmentIntegrityReport(1, 1, 0, 0, 0)
    )
    assert entries == [entry]
    assert sorted(
        path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()
    ) == [KEY]

    missing_root = tmp_path / "missing"
    assert assess_attachment_bytes(storage_root=missing_root, entries=()) == (
        AttachmentIntegrityReport(0, 0, 0, 0, 0)
    )
    assert not missing_root.exists()


def test_attachment_entry_collection_rejects_duplicates_and_wrong_types(tmp_path: Path) -> None:
    entry = AttachmentArchiveEntry(storage_key=KEY, sha256=DIGEST)
    with pytest.raises(
        ValueError,
        match="^Attachment metadata contains duplicate storage keys[.]$",
    ):
        assess_attachment_bytes(storage_root=tmp_path, entries=(entry, entry))
    with pytest.raises(
        TypeError,
        match="^Attachment entries must be AttachmentArchiveEntry values[.]$",
    ):
        assess_attachment_bytes(storage_root=tmp_path, entries=({"storage_key": KEY},))  # type: ignore[arg-type]


def test_archive_round_trip_reports_are_path_free_and_inputs_are_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "source"
    archive_root = tmp_path / "archives"
    restore_root = tmp_path / "restore"
    entry = _write_entry(source)
    entries = [entry]
    created_at = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)

    archived = create_attachment_archive(
        storage_root=source,
        entries=entries,
        archive_root=archive_root,
        archive_name="attachments.zip",
        created_at=created_at,
    )
    inspected = inspect_attachment_archive(
        archive_path=archive_root / "attachments.zip",
        expected_entries=entries,
    )
    restored = restore_attachment_archive(
        archive_path=archive_root / "attachments.zip",
        restore_root=restore_root,
        restore_label="rehearsal_restore",
        expected_entries=entries,
    )

    assert archived == AttachmentArchiveReport(
        archive_name="attachments.zip",
        created_at=created_at,
        attachment_count=1,
        attachment_bytes=len(BODY),
        archive_sha256=archived.archive_sha256,
        source_orphan_count=0,
        postgresql_metadata_backed_up=False,
    )
    assert inspected == AttachmentIntegrityReport(1, 1, 0, 0, 0)
    assert restored == AttachmentRestoreReport(
        archive_name="attachments.zip",
        restore_label="rehearsal_restore",
        restored_count=1,
        restored_bytes=len(BODY),
        missing_count=0,
        checksum_mismatch_count=0,
        orphan_count=0,
        postgresql_metadata_restored=False,
    )
    assert entries == [entry]
    assert (restore_root / "rehearsal_restore" / Path(*KEY.split("/"))).read_bytes() == BODY


def test_archive_and_restore_reject_unsafe_names_before_creating_roots(tmp_path: Path) -> None:
    source = tmp_path / "source"
    entry = _write_entry(source)
    archive_root = tmp_path / "archives"
    with pytest.raises(ValueError, match="^Artifact name must be a safe generated filename[.]$"):
        create_attachment_archive(
            storage_root=source,
            entries=(entry,),
            archive_root=archive_root,
            archive_name="../attachments.zip",
        )
    assert not archive_root.exists()

    with pytest.raises(
        ValueError,
        match="^Target label must be an opaque lowercase identifier[.]$",
    ):
        restore_attachment_archive(
            archive_path=tmp_path / "missing.zip",
            restore_root=tmp_path / "restore",
            restore_label="Unsafe Label",
            expected_entries=(entry,),
        )
    assert not (tmp_path / "restore").exists()
