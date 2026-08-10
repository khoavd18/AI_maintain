"""Path-safe attachment-byte assessment, archive, inspection, and restore drills."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from uuid import uuid4
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

from src.reliability.operator_drills.artifact_io import (
    _aware_utc,
    _contained_child,
    _isoformat_utc,
    _prepare_root,
    _sha256_file,
    _sync_descriptor,
    _sync_directory,
    _sync_file,
    _unlink_regular_file,
    _validate_safe_filename,
    _validate_sha256,
)
from src.reliability.operator_drills.contracts import _validate_opaque_label


_ATTACHMENT_KEY_PATTERN = re.compile(
    r"^(?:assets|work-orders|inventory)/[0-9a-f]{2}/"
    r"[0-9a-f]{32}\.(?:pdf|png|jpg|jpeg)$"
)
_ATTACHMENT_MANIFEST_NAME = "attachment-manifest.json"
_ATTACHMENT_MEMBER_PREFIX = "attachment-bytes/"
_ATTACHMENT_ARCHIVE_VERSION = 1
_MAX_ARCHIVE_ENTRY_COUNT = 10_000
_MAX_ARCHIVE_ENTRY_BYTES = 50 * 1024 * 1024
_MAX_ARCHIVE_TOTAL_BYTES = 5 * 1024 * 1024 * 1024
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_ATTACHMENT_STREAM_CHUNK_BYTES = 1024 * 1024


class AttachmentArchiveError(RuntimeError):
    """Raised when attachment bytes cannot be safely archived or restored."""


class AttachmentArchiveIntegrityError(AttachmentArchiveError):
    """Raised when an attachment-byte archive fails integrity validation."""


@dataclass(frozen=True)
class AttachmentArchiveEntry:
    """Expected attachment metadata paired with one generated storage key."""

    storage_key: str
    sha256: str

    def __post_init__(self) -> None:
        _validate_attachment_key(self.storage_key)
        _validate_sha256(self.sha256)


@dataclass(frozen=True)
class AttachmentIntegrityReport:
    """Aggregate-only attachment byte/metadata comparison."""

    expected_count: int
    ok_count: int
    missing_count: int
    checksum_mismatch_count: int
    orphan_count: int

    @property
    def valid(self) -> bool:
        return (
            self.expected_count > 0
            and self.ok_count == self.expected_count
            and self.missing_count == 0
            and self.checksum_mismatch_count == 0
            and self.orphan_count == 0
        )


@dataclass(frozen=True)
class AttachmentArchiveReport:
    """Path-free attachment-byte archive summary.

    This report does not assert that PostgreSQL attachment metadata was backed up.
    """

    archive_name: str
    created_at: datetime
    attachment_count: int
    attachment_bytes: int
    archive_sha256: str
    source_orphan_count: int
    postgresql_metadata_backed_up: bool = False


@dataclass(frozen=True)
class AttachmentRestoreReport:
    """Path-free attachment-byte restore summary.

    This report does not assert that PostgreSQL attachment metadata was restored.
    """

    archive_name: str
    restore_label: str
    restored_count: int
    restored_bytes: int
    missing_count: int
    checksum_mismatch_count: int
    orphan_count: int
    postgresql_metadata_restored: bool = False


@dataclass(frozen=True)
class _ArchivedAttachment:
    storage_key: str
    sha256: str
    size_bytes: int


def assess_attachment_bytes(
    *,
    storage_root: Path,
    entries: Iterable[AttachmentArchiveEntry],
) -> AttachmentIntegrityReport:
    """Compare a metadata snapshot to bytes under one configured storage root."""

    expected = _entry_map(entries)
    root = storage_root.resolve()
    if root.exists() and not root.is_dir():
        raise AttachmentArchiveError("Attachment storage root is not a directory.")
    ok_count = 0
    missing_count = 0
    mismatch_count = 0
    for entry in expected.values():
        target = _attachment_path(root, entry.storage_key)
        if not target.is_file():
            missing_count += 1
            continue
        if target.is_symlink():
            mismatch_count += 1
            continue
        try:
            actual = _sha256_file(target)
        except OSError:
            mismatch_count += 1
            continue
        if hmac.compare_digest(actual, entry.sha256):
            ok_count += 1
        else:
            mismatch_count += 1
    referenced = set(expected)
    orphan_count = 0
    if root.exists():
        for path in root.rglob("*"):
            if not path.is_file() and not path.is_symlink():
                continue
            try:
                key = path.relative_to(root).as_posix()
            except ValueError:
                orphan_count += 1
                continue
            if key not in referenced:
                orphan_count += 1
    return AttachmentIntegrityReport(
        expected_count=len(expected),
        ok_count=ok_count,
        missing_count=missing_count,
        checksum_mismatch_count=mismatch_count,
        orphan_count=orphan_count,
    )


def create_attachment_archive(
    *,
    storage_root: Path,
    entries: Sequence[AttachmentArchiveEntry],
    archive_root: Path,
    archive_name: str,
    created_at: datetime | None = None,
) -> AttachmentArchiveReport:
    """Create a bounded-memory ZIP of bytes and an allow-listed checksum manifest.

    The archive is a byte backup only. It does not claim that corresponding
    PostgreSQL attachment metadata was backed up.
    """

    _validate_safe_filename(archive_name)
    if not archive_name.endswith(".zip"):
        raise ValueError("Attachment archive name must end with .zip.")
    expected = _entry_map(entries)
    if not expected:
        raise ValueError("Attachment archive must contain at least one entry.")
    if len(expected) > _MAX_ARCHIVE_ENTRY_COUNT:
        raise ValueError("Attachment archive exceeds the bounded entry count.")
    source_root = storage_root.resolve()
    assessment = assess_attachment_bytes(
        storage_root=source_root,
        entries=tuple(expected.values()),
    )
    if assessment.missing_count or assessment.checksum_mismatch_count:
        raise AttachmentArchiveIntegrityError(
            "Attachment source failed checksum or presence validation."
        )
    output_root = _prepare_root(archive_root)
    destination = _contained_child(output_root, archive_name)
    partial = _contained_child(output_root, f".{archive_name}.{uuid4().hex}.partial")
    timestamp = _aware_utc(created_at or datetime.now(timezone.utc))
    archived: list[_ArchivedAttachment] = []
    total_bytes = 0
    try:
        with ZipFile(partial, mode="x", compression=ZIP_DEFLATED) as archive:
            for entry in expected.values():
                target = _attachment_path(source_root, entry.storage_key)
                archived_entry = _stream_attachment_member(
                    archive=archive,
                    source_root=source_root,
                    source_path=target,
                    entry=entry,
                    existing_total_bytes=total_bytes,
                )
                archived.append(archived_entry)
                total_bytes += archived_entry.size_bytes
            manifest = {
                "archive_version": _ATTACHMENT_ARCHIVE_VERSION,
                "created_at": _isoformat_utc(timestamp),
                "entries": [
                    {
                        "sha256": item.sha256,
                        "size_bytes": item.size_bytes,
                        "storage_key": item.storage_key,
                    }
                    for item in archived
                ],
            }
            archive.writestr(
                _ATTACHMENT_MANIFEST_NAME,
                json.dumps(
                    manifest,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8"),
            )
        _sync_file(partial)
        inspection = inspect_attachment_archive(
            archive_path=partial,
            expected_entries=tuple(expected.values()),
        )
        if not inspection.valid:
            raise AttachmentArchiveIntegrityError(
                "Created attachment archive failed integrity validation."
            )
        archive_checksum = _sha256_file(partial)
        os.replace(partial, destination)
        _sync_directory(output_root)
        return AttachmentArchiveReport(
            archive_name=archive_name,
            created_at=timestamp,
            attachment_count=len(archived),
            attachment_bytes=total_bytes,
            archive_sha256=archive_checksum,
            source_orphan_count=assessment.orphan_count,
        )
    except (AttachmentArchiveError, ValueError):
        raise
    except (BadZipFile, OSError):
        raise AttachmentArchiveError("Attachment archive could not be safely published.") from None
    finally:
        _unlink_regular_file(partial)


def _stream_attachment_member(
    *,
    archive: ZipFile,
    source_root: Path,
    source_path: Path,
    entry: AttachmentArchiveEntry,
    existing_total_bytes: int,
) -> _ArchivedAttachment:
    """Copy one source into the ZIP with fixed-size reads and an inline digest."""

    if (
        not source_path.is_file()
        or source_path.is_symlink()
        or not source_path.resolve().is_relative_to(source_root)
    ):
        raise AttachmentArchiveIntegrityError(
            "Attachment source changed while the archive was created."
        )
    try:
        source = source_path.open("rb")
    except OSError:
        raise AttachmentArchiveIntegrityError(
            "Attachment source changed while the archive was created."
        ) from None
    digest = hashlib.sha256()
    size_bytes = 0
    member_name = f"{_ATTACHMENT_MEMBER_PREFIX}{entry.storage_key}"
    with source:
        with archive.open(member_name, mode="w", force_zip64=True) as member:
            while True:
                try:
                    block = source.read(_ATTACHMENT_STREAM_CHUNK_BYTES)
                except OSError:
                    raise AttachmentArchiveIntegrityError(
                        "Attachment source changed while the archive was created."
                    ) from None
                if not block:
                    break
                next_entry_size = size_bytes + len(block)
                if next_entry_size > _MAX_ARCHIVE_ENTRY_BYTES:
                    raise AttachmentArchiveError(
                        "Attachment archive entry exceeds the bounded size."
                    )
                if existing_total_bytes + next_entry_size > _MAX_ARCHIVE_TOTAL_BYTES:
                    raise AttachmentArchiveError(
                        "Attachment archive exceeds the bounded total size."
                    )
                digest.update(block)
                member.write(block)
                size_bytes = next_entry_size
    if size_bytes <= 0:
        raise AttachmentArchiveError("Attachment archive entry must contain non-empty bytes.")
    checksum = digest.hexdigest()
    if not hmac.compare_digest(checksum, entry.sha256):
        raise AttachmentArchiveIntegrityError(
            "Attachment source changed while the archive was created."
        )
    return _ArchivedAttachment(
        storage_key=entry.storage_key,
        sha256=entry.sha256,
        size_bytes=size_bytes,
    )


def inspect_attachment_archive(
    *,
    archive_path: Path,
    expected_entries: Sequence[AttachmentArchiveEntry] | None = None,
) -> AttachmentIntegrityReport:
    """Validate ZIP members and compare them with an optional metadata snapshot."""

    try:
        with ZipFile(archive_path, mode="r") as archive:
            return _inspect_open_attachment_archive(
                archive,
                expected_entries=expected_entries,
            )
    except AttachmentArchiveError:
        raise
    except (BadZipFile, OSError, UnicodeError, json.JSONDecodeError):
        raise AttachmentArchiveIntegrityError(
            "Attachment archive is unreadable or malformed."
        ) from None


def restore_attachment_archive(
    *,
    archive_path: Path,
    restore_root: Path,
    restore_label: str,
    expected_entries: Sequence[AttachmentArchiveEntry],
) -> AttachmentRestoreReport:
    """Validate and restore bytes without asserting PostgreSQL metadata recovery."""

    _validate_opaque_label(restore_label)
    expected = _entry_map(expected_entries)
    if not expected:
        raise ValueError("Attachment restore requires non-empty expected metadata.")
    root = _prepare_root(restore_root)
    destination = _contained_child(root, restore_label)
    if destination.exists():
        raise AttachmentArchiveError("Attachment restore destination already exists.")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{restore_label}.", suffix=".partial", dir=root)
    ).resolve()
    restored_bytes = 0
    archive_name = archive_path.name
    _validate_safe_filename(archive_name)
    try:
        try:
            with ZipFile(archive_path, mode="r") as archive:
                inspection = _inspect_open_attachment_archive(
                    archive,
                    expected_entries=tuple(expected.values()),
                )
                if not inspection.valid:
                    raise AttachmentArchiveIntegrityError(
                        "Attachment archive does not match the expected metadata."
                    )
                archived = _read_attachment_manifest(archive)
                for entry in archived.values():
                    member_name = f"{_ATTACHMENT_MEMBER_PREFIX}{entry.storage_key}"
                    body = archive.read(member_name)
                    target = _attachment_path(staging, entry.storage_key)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as output:
                        output.write(body)
                        output.flush()
                        _sync_descriptor(output.fileno())
                    restored_bytes += len(body)
        except AttachmentArchiveError:
            raise
        except (BadZipFile, KeyError, OSError, UnicodeError, json.JSONDecodeError):
            raise AttachmentArchiveIntegrityError(
                "Attachment archive restore failed validation."
            ) from None
        restored = assess_attachment_bytes(
            storage_root=staging,
            entries=tuple(expected.values()),
        )
        if not restored.valid:
            raise AttachmentArchiveIntegrityError(
                "Restored attachment bytes failed integrity validation."
            )
        os.replace(staging, destination)
        _sync_directory(root)
        return AttachmentRestoreReport(
            archive_name=archive_name,
            restore_label=restore_label,
            restored_count=restored.ok_count,
            restored_bytes=restored_bytes,
            missing_count=0,
            checksum_mismatch_count=0,
            orphan_count=0,
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _inspect_open_attachment_archive(
    archive: ZipFile,
    *,
    expected_entries: Sequence[AttachmentArchiveEntry] | None,
) -> AttachmentIntegrityReport:
    infos = archive.infolist()
    if not infos or len(infos) > _MAX_ARCHIVE_ENTRY_COUNT + 1:
        raise AttachmentArchiveIntegrityError("Attachment archive has an invalid entry count.")
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise AttachmentArchiveIntegrityError("Attachment archive contains duplicate members.")
    for info in infos:
        _validate_zip_info(info)
    archived = _read_attachment_manifest(archive)
    if expected_entries is None:
        expected = {
            key: AttachmentArchiveEntry(storage_key=key, sha256=value.sha256)
            for key, value in archived.items()
        }
    else:
        expected = _entry_map(expected_entries)
    member_infos = {
        name.removeprefix(_ATTACHMENT_MEMBER_PREFIX): info
        for name, info in zip(names, infos, strict=True)
        if name.startswith(_ATTACHMENT_MEMBER_PREFIX)
    }
    unknown_members = {
        name
        for name in names
        if name != _ATTACHMENT_MANIFEST_NAME and not name.startswith(_ATTACHMENT_MEMBER_PREFIX)
    }
    missing_count = 0
    mismatch_count = 0
    ok_count = 0
    for key, expected_entry in expected.items():
        manifest_entry = archived.get(key)
        member_info = member_infos.get(key)
        if manifest_entry is None or member_info is None:
            missing_count += 1
            continue
        if (
            not hmac.compare_digest(manifest_entry.sha256, expected_entry.sha256)
            or manifest_entry.size_bytes != member_info.file_size
        ):
            mismatch_count += 1
            continue
        actual = _sha256_zip_member(archive, member_info)
        if hmac.compare_digest(actual, expected_entry.sha256):
            ok_count += 1
        else:
            mismatch_count += 1
    archived_keys = set(archived)
    member_keys = set(member_infos)
    expected_keys = set(expected)
    orphan_count = len(archived_keys - expected_keys)
    orphan_count += len(member_keys - archived_keys)
    orphan_count += len(unknown_members)
    return AttachmentIntegrityReport(
        expected_count=len(expected),
        ok_count=ok_count,
        missing_count=missing_count,
        checksum_mismatch_count=mismatch_count,
        orphan_count=orphan_count,
    )


def _read_attachment_manifest(
    archive: ZipFile,
) -> dict[str, _ArchivedAttachment]:
    try:
        info = archive.getinfo(_ATTACHMENT_MANIFEST_NAME)
    except KeyError:
        raise AttachmentArchiveIntegrityError("Attachment archive manifest is missing.") from None
    if info.file_size > _MAX_MANIFEST_BYTES:
        raise AttachmentArchiveIntegrityError(
            "Attachment archive manifest exceeds the bounded size."
        )
    raw = archive.read(info)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise AttachmentArchiveIntegrityError("Attachment archive manifest is malformed.") from None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"archive_version", "created_at", "entries"}
        or payload.get("archive_version") != _ATTACHMENT_ARCHIVE_VERSION
        or not isinstance(payload.get("created_at"), str)
        or not isinstance(payload.get("entries"), list)
    ):
        raise AttachmentArchiveIntegrityError("Attachment archive manifest contract is invalid.")
    records: dict[str, _ArchivedAttachment] = {}
    for raw_entry in payload["entries"]:
        if (
            not isinstance(raw_entry, dict)
            or set(raw_entry) != {"sha256", "size_bytes", "storage_key"}
            or not isinstance(raw_entry.get("storage_key"), str)
            or not isinstance(raw_entry.get("sha256"), str)
            or isinstance(raw_entry.get("size_bytes"), bool)
            or not isinstance(raw_entry.get("size_bytes"), int)
            or raw_entry["size_bytes"] <= 0
            or raw_entry["size_bytes"] > _MAX_ARCHIVE_ENTRY_BYTES
        ):
            raise AttachmentArchiveIntegrityError("Attachment archive manifest entry is invalid.")
        try:
            _validate_attachment_key(raw_entry["storage_key"])
            _validate_sha256(raw_entry["sha256"])
        except ValueError:
            raise AttachmentArchiveIntegrityError(
                "Attachment archive manifest entry is invalid."
            ) from None
        key = raw_entry["storage_key"]
        if key in records:
            raise AttachmentArchiveIntegrityError(
                "Attachment archive manifest contains duplicate storage keys."
            )
        records[key] = _ArchivedAttachment(
            storage_key=key,
            sha256=raw_entry["sha256"],
            size_bytes=raw_entry["size_bytes"],
        )
    if not records or len(records) > _MAX_ARCHIVE_ENTRY_COUNT:
        raise AttachmentArchiveIntegrityError("Attachment archive manifest entry count is invalid.")
    if sum(record.size_bytes for record in records.values()) > _MAX_ARCHIVE_TOTAL_BYTES:
        raise AttachmentArchiveIntegrityError(
            "Attachment archive manifest exceeds the bounded total size."
        )
    return records


def _validate_zip_info(info: ZipInfo) -> None:
    name = info.filename
    pure = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or ":" in name
        or pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or info.is_dir()
        or info.flag_bits & 0x1
    ):
        raise AttachmentArchiveIntegrityError("Attachment archive contains an unsafe member.")
    mode = (info.external_attr >> 16) & 0o170000
    if mode == 0o120000:
        raise AttachmentArchiveIntegrityError("Attachment archive contains a symbolic link.")
    if info.file_size < 0 or (
        name != _ATTACHMENT_MANIFEST_NAME and info.file_size > _MAX_ARCHIVE_ENTRY_BYTES
    ):
        raise AttachmentArchiveIntegrityError("Attachment archive member exceeds the bounded size.")
    if name.startswith(_ATTACHMENT_MEMBER_PREFIX):
        try:
            _validate_attachment_key(name.removeprefix(_ATTACHMENT_MEMBER_PREFIX))
        except ValueError:
            raise AttachmentArchiveIntegrityError(
                "Attachment archive contains an unsafe storage key."
            ) from None


def _sha256_zip_member(archive: ZipFile, info: ZipInfo) -> str:
    digest = hashlib.sha256()
    total = 0
    with archive.open(info, mode="r") as source:
        while block := source.read(1024 * 1024):
            total += len(block)
            if total > _MAX_ARCHIVE_ENTRY_BYTES:
                raise AttachmentArchiveIntegrityError(
                    "Attachment archive member exceeds the bounded size."
                )
            digest.update(block)
    return digest.hexdigest()


def _entry_map(
    entries: Iterable[AttachmentArchiveEntry],
) -> dict[str, AttachmentArchiveEntry]:
    result: dict[str, AttachmentArchiveEntry] = {}
    for entry in entries:
        if not isinstance(entry, AttachmentArchiveEntry):
            raise TypeError("Attachment entries must be AttachmentArchiveEntry values.")
        if entry.storage_key in result:
            raise ValueError("Attachment metadata contains duplicate storage keys.")
        result[entry.storage_key] = entry
    return dict(sorted(result.items()))


def _attachment_path(root: Path, storage_key: str) -> Path:
    _validate_attachment_key(storage_key)
    target = (root / Path(*storage_key.split("/"))).resolve()
    if not target.is_relative_to(root):
        raise AttachmentArchiveError("Attachment storage key is outside the configured root.")
    return target


def _validate_attachment_key(value: str) -> None:
    if not _ATTACHMENT_KEY_PATTERN.fullmatch(value):
        raise ValueError("Attachment storage key is not a generated supported key.")
