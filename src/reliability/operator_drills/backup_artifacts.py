"""Immutable, checksummed backup-artifact publication and retention selection."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hmac
import json
import os
from pathlib import Path
from uuid import uuid4

from src.reliability.operator_drills.artifact_io import (
    _SHA256_PATTERN,
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


_BACKUP_METADATA_VERSION = 1
_BACKUP_INDEX_VERSION = 1
VALIDATED_BACKUP_INDEX_NAME = "latest-validated-backup.json"
_BACKUP_PUBLICATION_LOCK_NAME = ".backup-publication.lock"
_MAX_BACKUP_INDEX_BYTES = 16 * 1024
_MAX_BACKUP_ARTIFACT_NAME_LENGTH = 160


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


def _create_atomic_backup_artifact(
    *,
    allowed_root: Path,
    artifact_name: str,
    writer: Callable[[Path], None],
    expected_sha256: str | None = None,
    created_at: datetime | None = None,
    publish_validated_backup_index: Callable[..., None],
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
                publish_validated_backup_index(root=root, result=result)
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


def create_atomic_backup_artifact(
    *,
    allowed_root: Path,
    artifact_name: str,
    writer: Callable[[Path], None],
    expected_sha256: str | None = None,
    created_at: datetime | None = None,
) -> BackupArtifactResult:
    """Publish through the canonical backup implementation and publication seam."""

    return _create_atomic_backup_artifact(
        allowed_root=allowed_root,
        artifact_name=artifact_name,
        writer=writer,
        expected_sha256=expected_sha256,
        created_at=created_at,
        publish_validated_backup_index=_publish_validated_backup_index,
    )


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


def _path_exists(path: Path) -> bool:
    """Return true for regular entries, including dangling symbolic links."""

    return path.exists() or path.is_symlink()


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
