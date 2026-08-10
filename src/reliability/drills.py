"""Historical compatibility facade for focused PM9 reliability drill modules."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import os as os
from pathlib import Path

from src.reliability.operator_drills.attachment_archives import (
    AttachmentArchiveEntry as AttachmentArchiveEntry,
    AttachmentArchiveError as AttachmentArchiveError,
    AttachmentArchiveIntegrityError as AttachmentArchiveIntegrityError,
    AttachmentArchiveReport as AttachmentArchiveReport,
    AttachmentIntegrityReport as AttachmentIntegrityReport,
    AttachmentRestoreReport as AttachmentRestoreReport,
    assess_attachment_bytes as assess_attachment_bytes,
    create_attachment_archive as create_attachment_archive,
    inspect_attachment_archive as inspect_attachment_archive,
    restore_attachment_archive as restore_attachment_archive,
)
from src.reliability.operator_drills.backup_artifacts import (
    VALIDATED_BACKUP_INDEX_NAME as VALIDATED_BACKUP_INDEX_NAME,
    BackupArtifactError as BackupArtifactError,
    BackupArtifactResult as BackupArtifactResult,
    BackupChecksumMismatchError as BackupChecksumMismatchError,
    BackupRetentionSelection as BackupRetentionSelection,
    BackupVerificationReport as BackupVerificationReport,
    _create_atomic_backup_artifact,
    _publish_validated_backup_index as _publish_validated_backup_index,
    read_validated_backup_index as read_validated_backup_index,
    select_backup_retention as select_backup_retention,
    verify_backup_artifact as verify_backup_artifact,
)
from src.reliability.operator_drills.disk_capacity import (
    DISK_ACTION_ESCALATE_CRITICAL as DISK_ACTION_ESCALATE_CRITICAL,
    DISK_ACTION_NONE as DISK_ACTION_NONE,
    DISK_ACTION_RAISE_CRITICAL as DISK_ACTION_RAISE_CRITICAL,
    DISK_ACTION_RAISE_WARNING as DISK_ACTION_RAISE_WARNING,
    DISK_ACTION_RECOVER as DISK_ACTION_RECOVER,
    DiskAlertCycle as DiskAlertCycle,
    DiskCapacity as DiskCapacity,
    DiskCapacityReport as DiskCapacityReport,
    DiskSeverity as DiskSeverity,
)


def create_atomic_backup_artifact(
    *,
    allowed_root: Path,
    artifact_name: str,
    writer: Callable[[Path], None],
    expected_sha256: str | None = None,
    created_at: datetime | None = None,
) -> BackupArtifactResult:
    """Preserve the historical failure-injection seam for backup publication."""

    return _create_atomic_backup_artifact(
        allowed_root=allowed_root,
        artifact_name=artifact_name,
        writer=writer,
        expected_sha256=expected_sha256,
        created_at=created_at,
        publish_validated_backup_index=_publish_validated_backup_index,
    )
