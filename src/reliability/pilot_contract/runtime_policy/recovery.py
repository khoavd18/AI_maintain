"""Restore prerequisites and rollback policy validation."""

from __future__ import annotations

from typing import Any

from ..constants import _COMMIT_RE
from ..document_shapes import _mapping, _require_keys
from ..findings import _add
from ..schemas import Finding


def _validate_recovery_policy(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
    restore = _mapping(document.get("restore_prerequisites"))
    for key in (
        "separate_restore_database_required",
        "validated_checksum_required",
        "backup_metadata_required",
        "compatible_postgresql_tools_required",
        "attachment_snapshot_required_when_metadata_is_nonempty",
        "owner_approval_required",
    ):
        if restore.get(key) is not True:
            _add(
                findings,
                "restore_prerequisite_missing",
                f"manifest.restore_prerequisites.{key}",
                "Restore prerequisite bắt buộc phải được khai báo true.",
            )
    if restore.get("restore_database_name_suffix") != "_restore":
        _add(
            findings,
            "unsafe_restore_database_suffix",
            "manifest.restore_prerequisites.restore_database_name_suffix",
            "Database restore rehearsal phải có tên kết thúc bằng _restore.",
        )
    if restore.get("postgresql_integration_test_database_name_suffix") != "_test":
        _add(
            findings,
            "unsafe_postgresql_test_database_suffix",
            "manifest.restore_prerequisites.postgresql_integration_test_database_name_suffix",
            "PostgreSQL integration test database phải có tên kết thúc bằng _test.",
        )

    rollback = _mapping(document.get("rollback"))
    _require_keys(
        rollback,
        {
            "target_release_id",
            "target_git_tag",
            "target_git_commit",
            "target_alembic_revision",
            "mode",
            "database_downgrade_allowed",
            "validated_backup_required",
            "rehearsal_status",
        },
        "manifest.rollback",
        findings,
    )
    if not _COMMIT_RE.fullmatch(str(rollback.get("target_git_commit", ""))):
        _add(
            findings,
            "rollback_commit_invalid",
            "manifest.rollback.target_git_commit",
            "Rollback target phải dùng full Git SHA.",
        )
    if rollback.get("database_downgrade_allowed") is not False:
        _add(
            findings,
            "unsafe_database_downgrade",
            "manifest.rollback.database_downgrade_allowed",
            "PM9 không xác nhận migration downgrade an toàn; phải dùng validated restore.",
        )
    if rollback.get("validated_backup_required") is not True:
        _add(
            findings,
            "rollback_backup_not_required",
            "manifest.rollback.validated_backup_required",
            "Rollback restore phải yêu cầu validated backup.",
        )
    if rollback.get("rehearsal_status") != "passed":
        _add(
            findings,
            "rollback_rehearsal_unverified",
            "manifest.rollback.rehearsal_status",
            "Rollback rehearsal chưa có bằng chứng passed.",
        )
