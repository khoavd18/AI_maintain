"""Safe-default integration tests across PM9 operator-drill protocols."""

# ruff: noqa: F401 - split suites import their explicit scenario dependencies

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
