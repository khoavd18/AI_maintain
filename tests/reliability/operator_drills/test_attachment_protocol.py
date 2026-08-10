"""Operator-drill tests grouped by atomic protocol."""

from __future__ import annotations

from ._protocol_scenarios import (
    AttachmentArchiveEntry,
    AttachmentArchiveIntegrityError,
    Path,
    ZIP_DEFLATED,
    ZipFile,
    _write_attachment,
    assess_attachment_bytes,
    create_attachment_archive,
    datetime,
    hashlib,
    inspect_attachment_archive,
    json,
    pytest,
    restore_attachment_archive,
    timezone,
)


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
