"""Injected, path-safe helpers for PM9 operator reliability drills.

The helpers in this module deliberately do not discover host capacity, invoke
PostgreSQL tools, or mutate application records. Callers supply observations,
backup writers, and isolated attachment roots. Public reports contain only
opaque labels, relative generated names, aggregate counts, and checksums.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import hashlib
import hmac
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Literal
from uuid import uuid4
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo


_OPAQUE_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ATTACHMENT_KEY_PATTERN = re.compile(
    r"^(?:assets|work-orders|inventory)/[0-9a-f]{2}/"
    r"[0-9a-f]{32}\.(?:pdf|png|jpg|jpeg)$"
)
_ATTACHMENT_MANIFEST_NAME = "attachment-manifest.json"
_ATTACHMENT_MEMBER_PREFIX = "attachment-bytes/"
_BACKUP_METADATA_VERSION = 1
_BACKUP_INDEX_VERSION = 1
_ATTACHMENT_ARCHIVE_VERSION = 1
VALIDATED_BACKUP_INDEX_NAME = "latest-validated-backup.json"
_BACKUP_PUBLICATION_LOCK_NAME = ".backup-publication.lock"
_MAX_BACKUP_INDEX_BYTES = 16 * 1024
_MAX_BACKUP_ARTIFACT_NAME_LENGTH = 160
_MAX_ARCHIVE_ENTRY_COUNT = 10_000
_MAX_ARCHIVE_ENTRY_BYTES = 50 * 1024 * 1024
_MAX_ARCHIVE_TOTAL_BYTES = 5 * 1024 * 1024 * 1024
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_ATTACHMENT_STREAM_CHUNK_BYTES = 1024 * 1024

DiskSeverity = Literal["healthy", "warning", "critical"]

DISK_ACTION_NONE = "none"
DISK_ACTION_RAISE_WARNING = "raise_warning_and_follow_disk_capacity_runbook"
DISK_ACTION_RAISE_CRITICAL = "raise_critical_and_follow_disk_capacity_runbook"
DISK_ACTION_ESCALATE_CRITICAL = "escalate_critical_via_disk_capacity_runbook"
DISK_ACTION_RECOVER = "record_recovery_after_capacity_is_verified"


@dataclass(frozen=True)
class DiskCapacity:
    """A capacity observation supplied by a controlled provider."""

    total_bytes: int
    free_bytes: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.total_bytes, bool)
            or not isinstance(self.total_bytes, int)
            or self.total_bytes <= 0
        ):
            raise ValueError("Total bytes must be a positive integer.")
        if (
            isinstance(self.free_bytes, bool)
            or not isinstance(self.free_bytes, int)
            or not 0 <= self.free_bytes <= self.total_bytes
        ):
            raise ValueError("Free bytes must be between zero and total bytes.")


@dataclass(frozen=True)
class DiskCapacityReport:
    """Path-free result from one injected disk-capacity observation."""

    target_label: str
    free_percent: float
    used_percent: float
    severity: DiskSeverity
    runbook_action: str

    def as_dict(self) -> dict[str, str | float]:
        return {
            "target_label": self.target_label,
            "free_percent": self.free_percent,
            "used_percent": self.used_percent,
            "severity": self.severity,
            "runbook_action": self.runbook_action,
        }


class DiskAlertCycle:
    """Deduplicate disk warning, escalation, and recovery actions per cycle."""

    def __init__(
        self,
        *,
        target_label: str,
        warning_free_percent: float,
        critical_free_percent: float,
    ) -> None:
        _validate_opaque_label(target_label)
        _validate_disk_thresholds(
            warning_free_percent=warning_free_percent,
            critical_free_percent=critical_free_percent,
        )
        self.target_label = target_label
        self.warning_free_percent = float(warning_free_percent)
        self.critical_free_percent = float(critical_free_percent)
        self._alert_active = False
        self._critical_announced = False

    def evaluate(
        self,
        capacity_provider: Callable[[], DiskCapacity],
    ) -> DiskCapacityReport:
        """Evaluate one supplied observation without querying the real filesystem."""

        capacity = capacity_provider()
        if not isinstance(capacity, DiskCapacity):
            raise TypeError("Capacity provider must return DiskCapacity.")
        free_percent = capacity.free_bytes * 100.0 / capacity.total_bytes
        severity = self._classify(free_percent)
        action = self._transition(severity)
        rounded_free = round(free_percent, 2)
        return DiskCapacityReport(
            target_label=self.target_label,
            free_percent=rounded_free,
            used_percent=round(100.0 - rounded_free, 2),
            severity=severity,
            runbook_action=action,
        )

    def _classify(self, free_percent: float) -> DiskSeverity:
        if free_percent <= self.critical_free_percent:
            return "critical"
        if free_percent <= self.warning_free_percent:
            return "warning"
        return "healthy"

    def _transition(self, severity: DiskSeverity) -> str:
        if severity == "healthy":
            if not self._alert_active:
                return DISK_ACTION_NONE
            self._alert_active = False
            self._critical_announced = False
            return DISK_ACTION_RECOVER
        if not self._alert_active:
            self._alert_active = True
            if severity == "critical":
                self._critical_announced = True
                return DISK_ACTION_RAISE_CRITICAL
            return DISK_ACTION_RAISE_WARNING
        if severity == "critical" and not self._critical_announced:
            self._critical_announced = True
            return DISK_ACTION_ESCALATE_CRITICAL
        return DISK_ACTION_NONE


class BackupArtifactError(RuntimeError):
    """Raised when a backup artifact cannot be safely validated or published."""


class BackupChecksumMismatchError(BackupArtifactError):
    """Raised before publication when the writer output checksum is unexpected."""


@dataclass(frozen=True)
class BackupArtifactResult:
    """Secret-free description of a successfully published backup pair."""

    artifact_name: str
    metadata_name: str
    created_at: datetime
    size_bytes: int
    sha256: str

    def as_dict(self) -> dict[str, str | int]:
        return {
            "artifact_name": self.artifact_name,
            "metadata_name": self.metadata_name,
            "created_at": _isoformat_utc(self.created_at),
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class BackupVerificationReport:
    """Path-free verification result for a published artifact pair."""

    artifact_name: str
    metadata_name: str
    valid: bool
    reason: str
    size_bytes: int | None
    sha256: str | None


@dataclass(frozen=True)
class BackupRetentionSelection:
    """Deterministic names selected for retention and expiry."""

    retain: tuple[str, ...]
    expire: tuple[str, ...]


def create_atomic_backup_artifact(
    *,
    allowed_root: Path,
    artifact_name: str,
    writer: Callable[[Path], None],
    expected_sha256: str | None = None,
    created_at: datetime | None = None,
) -> BackupArtifactResult:
    """Publish an immutable backup pair, then atomically advance its validated index.

    ``writer`` receives a unique ``.partial`` path below ``allowed_root``. The
    requested artifact name must itself be unique: an existing artifact or
    metadata file is never replaced. The single validated index is advanced only
    after both immutable files pass checksum verification.
    """

    _validate_safe_filename(artifact_name)
    if len(artifact_name) > _MAX_BACKUP_ARTIFACT_NAME_LENGTH:
        raise ValueError("Backup artifact name exceeds the safe generated length.")
    if artifact_name == VALIDATED_BACKUP_INDEX_NAME or artifact_name.endswith(
        (".partial", ".metadata.json")
    ):
        raise ValueError("Backup artifact name uses a reserved name or suffix.")
    if expected_sha256 is not None:
        _validate_sha256(expected_sha256)
    root = _prepare_root(allowed_root)
    artifact_path = _contained_child(root, artifact_name)
    metadata_name = f"{artifact_name}.metadata.json"
    metadata_path = _contained_child(root, metadata_name)
    nonce = uuid4().hex
    partial_path = _contained_child(root, f".{artifact_name}.{nonce}.partial")
    partial_metadata = _contained_child(root, f".{artifact_name}.{nonce}.metadata.partial")
    timestamp = _aware_utc(created_at or datetime.now(timezone.utc))
    with _exclusive_backup_publication(root):
        artifact_exists = _path_exists(artifact_path)
        metadata_exists = _path_exists(metadata_path)
        if artifact_exists != metadata_exists:
            raise BackupArtifactError(
                "Existing immutable backup pair is incomplete; operator review is required."
            )
        if artifact_exists:
            raise BackupArtifactError(
                "Backup artifact name already exists and immutable files are never replaced."
            )
        try:
            try:
                writer(partial_path)
            except Exception:
                raise BackupArtifactError(
                    "Backup writer failed; no artifact was published."
                ) from None
            if (
                not partial_path.is_file()
                or partial_path.is_symlink()
                or partial_path.stat().st_size <= 0
            ):
                raise BackupArtifactError(
                    "Backup writer did not produce a non-empty regular artifact."
                )
            _sync_file(partial_path)
            checksum = _sha256_file(partial_path)
            if expected_sha256 is not None and not hmac.compare_digest(checksum, expected_sha256):
                raise BackupChecksumMismatchError(
                    "Backup checksum did not match; no artifact was published."
                )
            size_bytes = partial_path.stat().st_size
            metadata = {
                "artifact_name": artifact_name,
                "created_at": _isoformat_utc(timestamp),
                "manifest_version": _BACKUP_METADATA_VERSION,
                "sha256": checksum,
                "size_bytes": size_bytes,
                "status": "validated",
            }
            _write_json_file(partial_metadata, metadata)
            _publish_immutable_backup_pair(
                partial_path=partial_path,
                partial_metadata=partial_metadata,
                artifact_path=artifact_path,
                metadata_path=metadata_path,
            )
            result = BackupArtifactResult(
                artifact_name=artifact_name,
                metadata_name=metadata_name,
                created_at=timestamp,
                size_bytes=size_bytes,
                sha256=checksum,
            )
            verification = verify_backup_artifact(
                allowed_root=root,
                artifact_name=artifact_name,
            )
            if (
                not verification.valid
                or verification.size_bytes != size_bytes
                or verification.sha256 != checksum
            ):
                raise BackupArtifactError(
                    "Immutable backup pair failed validation; the index was not updated."
                )
            try:
                _publish_validated_backup_index(root=root, result=result)
            except BackupArtifactError:
                raise
            except OSError:
                raise BackupArtifactError(
                    "Validated backup index was not updated; the immutable pair "
                    "requires operator review."
                ) from None
            indexed = read_validated_backup_index(allowed_root=root)
            if indexed != result:
                raise BackupArtifactError(
                    "Validated backup index does not reference the published pair."
                )
            return result
        finally:
            _unlink_regular_file(partial_path)
            _unlink_regular_file(partial_metadata)


def verify_backup_artifact(
    *,
    allowed_root: Path,
    artifact_name: str,
) -> BackupVerificationReport:
    """Verify a published pair without returning its local path."""

    _validate_safe_filename(artifact_name)
    root = allowed_root.resolve()
    artifact_path = _contained_child(root, artifact_name)
    metadata_name = f"{artifact_name}.metadata.json"
    metadata_path = _contained_child(root, metadata_name)
    if not artifact_path.is_file() or not metadata_path.is_file():
        return BackupVerificationReport(
            artifact_name=artifact_name,
            metadata_name=metadata_name,
            valid=False,
            reason="incomplete_pair",
            size_bytes=None,
            sha256=None,
        )
    if artifact_path.is_symlink() or metadata_path.is_symlink():
        return BackupVerificationReport(
            artifact_name=artifact_name,
            metadata_name=metadata_name,
            valid=False,
            reason="non_regular_file",
            size_bytes=None,
            sha256=None,
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return BackupVerificationReport(
            artifact_name=artifact_name,
            metadata_name=metadata_name,
            valid=False,
            reason="invalid_metadata",
            size_bytes=None,
            sha256=None,
        )
    if not _valid_backup_metadata(metadata, artifact_name=artifact_name):
        return BackupVerificationReport(
            artifact_name=artifact_name,
            metadata_name=metadata_name,
            valid=False,
            reason="invalid_metadata",
            size_bytes=None,
            sha256=None,
        )
    try:
        actual_size = artifact_path.stat().st_size
        actual_checksum = _sha256_file(artifact_path)
    except OSError:
        return BackupVerificationReport(
            artifact_name=artifact_name,
            metadata_name=metadata_name,
            valid=False,
            reason="unreadable_artifact",
            size_bytes=None,
            sha256=None,
        )
    valid = actual_size == metadata["size_bytes"] and hmac.compare_digest(
        actual_checksum, metadata["sha256"]
    )
    return BackupVerificationReport(
        artifact_name=artifact_name,
        metadata_name=metadata_name,
        valid=valid,
        reason="validated" if valid else "checksum_mismatch",
        size_bytes=actual_size,
        sha256=actual_checksum,
    )


def read_validated_backup_index(
    *,
    allowed_root: Path,
) -> BackupArtifactResult | None:
    """Return the immutable pair referenced by the validated index.

    A missing index means no backup pair has been authoritatively published.
    A present but malformed, inconsistent, or corrupt index fails closed.
    """

    root = allowed_root.resolve()
    index_path = _contained_child(root, VALIDATED_BACKUP_INDEX_NAME)
    if not _path_exists(index_path):
        return None
    if not index_path.is_file() or index_path.is_symlink():
        raise BackupArtifactError("Validated backup index is not a regular file.")
    try:
        if index_path.stat().st_size > _MAX_BACKUP_INDEX_BYTES:
            raise BackupArtifactError("Validated backup index exceeds the bounded size.")
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except BackupArtifactError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BackupArtifactError("Validated backup index is unreadable or malformed.") from None
    if not _valid_backup_index(payload):
        raise BackupArtifactError("Validated backup index contract is invalid.")
    artifact_name = payload["artifact_name"]
    verification = verify_backup_artifact(
        allowed_root=root,
        artifact_name=artifact_name,
    )
    if (
        not verification.valid
        or verification.metadata_name != payload["metadata_name"]
        or verification.size_bytes != payload["size_bytes"]
        or verification.sha256 != payload["sha256"]
    ):
        raise BackupArtifactError(
            "Validated backup index references an invalid immutable backup pair."
        )
    metadata_path = _contained_child(root, payload["metadata_name"])
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BackupArtifactError("Validated backup index metadata became unreadable.") from None
    if not isinstance(metadata, dict) or metadata.get("created_at") != payload["created_at"]:
        raise BackupArtifactError(
            "Validated backup index does not match immutable backup metadata."
        )
    try:
        created_at = _parse_utc_timestamp(payload["created_at"])
    except ValueError:
        raise BackupArtifactError("Validated backup index timestamp is invalid.") from None
    return BackupArtifactResult(
        artifact_name=artifact_name,
        metadata_name=payload["metadata_name"],
        created_at=created_at,
        size_bytes=payload["size_bytes"],
        sha256=payload["sha256"],
    )


def select_backup_retention(
    artifacts: Iterable[BackupArtifactResult],
    *,
    keep_count: int,
) -> BackupRetentionSelection:
    """Select older validated artifacts for expiry without deleting anything."""

    if isinstance(keep_count, bool) or not isinstance(keep_count, int) or keep_count < 1:
        raise ValueError("Backup retention must keep at least one validated artifact.")
    records = list(artifacts)
    names = [record.artifact_name for record in records]
    if len(names) != len(set(names)):
        raise ValueError("Backup retention candidates contain duplicate names.")
    ordered = sorted(
        records,
        key=lambda record: (_aware_utc(record.created_at), record.artifact_name),
        reverse=True,
    )
    return BackupRetentionSelection(
        retain=tuple(record.artifact_name for record in ordered[:keep_count]),
        expire=tuple(record.artifact_name for record in ordered[keep_count:]),
    )


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


@contextmanager
def _exclusive_backup_publication(root: Path) -> Iterator[None]:
    """Hold a fail-closed cross-process publication lock below ``root``."""

    lock_path = _contained_child(root, _BACKUP_PUBLICATION_LOCK_NAME)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except FileExistsError:
        raise BackupArtifactError(
            "Backup publication is already in progress or a stale lock requires operator review."
        ) from None
    except OSError:
        raise BackupArtifactError("Backup publication lock could not be acquired.") from None
    cleanup_error: OSError | None = None
    try:
        try:
            os.write(descriptor, b"exclusive-backup-publication\n")
            _sync_descriptor(descriptor)
            _sync_directory(root)
        except OSError:
            raise BackupArtifactError(
                "Backup publication lock could not be durably established."
            ) from None
        yield
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            cleanup_error = exc
        try:
            lock_path.unlink()
            _sync_directory(root)
        except FileNotFoundError:
            pass
        except OSError as exc:
            cleanup_error = cleanup_error or exc
        if cleanup_error is not None:
            raise BackupArtifactError(
                "Backup publication lock cleanup requires operator review."
            ) from cleanup_error


def _publish_immutable_backup_pair(
    *,
    partial_path: Path,
    partial_metadata: Path,
    artifact_path: Path,
    metadata_path: Path,
) -> None:
    """Move two new files into immutable names without advancing the index."""

    if _path_exists(artifact_path) or _path_exists(metadata_path):
        raise BackupArtifactError("Immutable backup publication refused an existing destination.")
    try:
        os.rename(partial_path, artifact_path)
        _sync_directory(artifact_path.parent)
        if _path_exists(metadata_path):
            raise BackupArtifactError("Immutable metadata destination appeared during publication.")
        os.rename(partial_metadata, metadata_path)
        _sync_directory(metadata_path.parent)
    except BackupArtifactError:
        raise
    except OSError:
        raise BackupArtifactError(
            "Immutable backup publication was interrupted; the validated index "
            "was not updated and operator review is required."
        ) from None


def _publish_validated_backup_index(
    *,
    root: Path,
    result: BackupArtifactResult,
) -> None:
    """Atomically advance the pointer after revalidating both immutable files."""

    verification = verify_backup_artifact(
        allowed_root=root,
        artifact_name=result.artifact_name,
    )
    if (
        not verification.valid
        or verification.metadata_name != result.metadata_name
        or verification.size_bytes != result.size_bytes
        or verification.sha256 != result.sha256
    ):
        raise BackupArtifactError(
            "Immutable backup pair is invalid; the validated index was not updated."
        )
    payload = {
        "artifact_name": result.artifact_name,
        "created_at": _isoformat_utc(result.created_at),
        "index_version": _BACKUP_INDEX_VERSION,
        "metadata_name": result.metadata_name,
        "sha256": result.sha256,
        "size_bytes": result.size_bytes,
        "status": "validated",
    }
    if not _valid_backup_index(payload):
        raise BackupArtifactError("Validated backup index payload is invalid.")
    index_path = _contained_child(root, VALIDATED_BACKUP_INDEX_NAME)
    partial_index = _contained_child(
        root,
        f".{VALIDATED_BACKUP_INDEX_NAME}.{uuid4().hex}.partial",
    )
    try:
        _write_json_file(partial_index, payload)
        os.replace(partial_index, index_path)
        _sync_directory(root)
    except OSError:
        raise BackupArtifactError(
            "Validated backup index publication could not be durably confirmed; "
            "operator review is required."
        ) from None
    finally:
        _unlink_regular_file(partial_index)


def _valid_backup_metadata(value: object, *, artifact_name: str) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "artifact_name",
            "created_at",
            "manifest_version",
            "sha256",
            "size_bytes",
            "status",
        }
        or value.get("artifact_name") != artifact_name
        or value.get("manifest_version") != _BACKUP_METADATA_VERSION
        or value.get("status") != "validated"
        or not isinstance(value.get("created_at"), str)
        or not isinstance(value.get("sha256"), str)
        or isinstance(value.get("size_bytes"), bool)
        or not isinstance(value.get("size_bytes"), int)
        or value["size_bytes"] <= 0
    ):
        return False
    return bool(
        _SHA256_PATTERN.fullmatch(value["sha256"]) and _valid_utc_timestamp(value["created_at"])
    )


def _valid_backup_index(value: object) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "artifact_name",
            "created_at",
            "index_version",
            "metadata_name",
            "sha256",
            "size_bytes",
            "status",
        }
        or value.get("index_version") != _BACKUP_INDEX_VERSION
        or value.get("status") != "validated"
        or not isinstance(value.get("artifact_name"), str)
        or not isinstance(value.get("metadata_name"), str)
        or value["metadata_name"] != f"{value['artifact_name']}.metadata.json"
        or not isinstance(value.get("created_at"), str)
        or not isinstance(value.get("sha256"), str)
        or isinstance(value.get("size_bytes"), bool)
        or not isinstance(value.get("size_bytes"), int)
        or value["size_bytes"] <= 0
    ):
        return False
    try:
        _validate_safe_filename(value["artifact_name"])
        _validate_safe_filename(value["metadata_name"])
        _validate_sha256(value["sha256"])
    except ValueError:
        return False
    return _valid_utc_timestamp(value["created_at"])


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


def _prepare_root(root: Path) -> Path:
    resolved = root.resolve()
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("Configured allowed root must be a directory.")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _contained_child(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Generated artifact is outside the configured allowed root.")
    return target


def _path_exists(path: Path) -> bool:
    """Return true for regular entries, including dangling symbolic links."""

    return path.exists() or path.is_symlink()


def _validate_safe_filename(value: str) -> None:
    if not _SAFE_FILENAME_PATTERN.fullmatch(value) or value in {".", ".."}:
        raise ValueError("Artifact name must be a safe generated filename.")


def _validate_attachment_key(value: str) -> None:
    if not _ATTACHMENT_KEY_PATTERN.fullmatch(value):
        raise ValueError("Attachment storage key is not a generated supported key.")


def _validate_sha256(value: str) -> None:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError("SHA-256 value must contain 64 lowercase hexadecimal characters.")


def _validate_opaque_label(value: str) -> None:
    if not _OPAQUE_LABEL_PATTERN.fullmatch(value):
        raise ValueError("Target label must be an opaque lowercase identifier.")


def _validate_disk_thresholds(
    *,
    warning_free_percent: float,
    critical_free_percent: float,
) -> None:
    values = (warning_free_percent, critical_free_percent)
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in values
    ):
        raise ValueError("Disk thresholds must be finite percentages.")
    if not 0 <= critical_free_percent < warning_free_percent <= 100:
        raise ValueError(
            "Disk critical threshold must be below the warning threshold within 0-100."
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _sync_file(path: Path) -> None:
    # Windows requires a writable descriptor for FlushFileBuffers/os.fsync.
    with path.open("rb+") as source:
        _sync_descriptor(source.fileno())


def _sync_descriptor(descriptor: int) -> None:
    unsupported = {
        errno.EINVAL,
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno not in unsupported:
            raise


def _sync_directory(path: Path) -> None:
    """Persist directory entries where the host filesystem supports it."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        unsupported_open = {
            errno.EACCES,
            errno.EINVAL,
            errno.EPERM,
            getattr(errno, "ENOTSUP", errno.EINVAL),
            getattr(errno, "EOPNOTSUPP", errno.EINVAL),
        }
        if os.name == "nt" or exc.errno in unsupported_open:
            return
        raise
    try:
        _sync_descriptor(descriptor)
    finally:
        os.close(descriptor)


def _write_json_file(path: Path, payload: dict[str, object]) -> None:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    with path.open("xb") as output:
        output.write(encoded)
        output.flush()
        _sync_descriptor(output.fileno())


def _unlink_regular_file(path: Path) -> None:
    try:
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
    except OSError:
        pass


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _parse_utc_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Timestamp must be an ISO-8601 UTC value.")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    normalized = _aware_utc(parsed)
    if _isoformat_utc(normalized) != value:
        raise ValueError("Timestamp must use the canonical ISO-8601 UTC form.")
    return normalized


def _valid_utc_timestamp(value: str) -> bool:
    try:
        _parse_utc_timestamp(value)
    except (TypeError, ValueError):
        return False
    return True


def _isoformat_utc(value: datetime) -> str:
    return _aware_utc(value).isoformat().replace("+00:00", "Z")
