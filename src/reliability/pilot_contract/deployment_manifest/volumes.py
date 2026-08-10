"""Validate persistent-volume purposes, services, mounts, and storage paths."""

from __future__ import annotations

from typing import Any

from ..document_shapes import _check_unique_names, _list_of_mappings, _mapping
from ..findings import _add
from ..schemas import Finding


def _validate_volumes(
    document: dict[str, Any],
    service_names: set[str],
    findings: list[Finding],
) -> None:
    volumes = _list_of_mappings(
        document.get("volumes"),
        findings=findings,
        scope="manifest.volumes",
    )
    if not isinstance(document.get("volumes"), list):
        _add(findings, "invalid_volumes", "manifest.volumes", "volumes phải là list.")
    _check_unique_names(volumes, "name", "volume", findings)
    purposes = {
        volume.get("purpose") for volume in volumes if isinstance(volume.get("purpose"), str)
    }
    for purpose in {
        "transactional_database",
        "rag_document_index",
        "local_attachment_bytes",
        "batch_analytics_contracts",
        "validated_backup_archives",
    } - purposes:
        _add(
            findings,
            "required_volume_missing",
            f"manifest.volumes.{purpose}",
            f"Thiếu persistent volume cho {purpose}.",
        )
    for volume in volumes:
        if volume.get("service") not in service_names:
            _add(
                findings,
                "volume_service_unknown",
                "manifest.volumes",
                "Volume tham chiếu service không tồn tại.",
            )
        kind = volume.get("kind")
        if kind not in {
            "compose_named_volume",
            "host_bind",
            "operator_managed_directory",
        }:
            _add(
                findings,
                "invalid_volume_kind",
                f"manifest.volumes.{volume.get('name')}",
                "Persistent storage phải khai báo loại volume được hỗ trợ.",
            )
        if kind in {"host_bind", "operator_managed_directory"}:
            storage_path_ref = volume.get("storage_path_ref")
            if storage_path_ref not in _mapping(_mapping(document.get("storage")).get("paths")):
                _add(
                    findings,
                    "volume_storage_path_unknown",
                    f"manifest.volumes.{volume.get('name')}",
                    "Host storage phải tham chiếu storage path đã khai báo.",
                )
        mounted_by = volume.get("mounted_by")
        if mounted_by is not None and (
            not isinstance(mounted_by, list)
            or not mounted_by
            or any(service not in service_names for service in mounted_by)
        ):
            _add(
                findings,
                "volume_mount_service_unknown",
                f"manifest.volumes.{volume.get('name')}",
                "mounted_by chỉ được tham chiếu service trong closed topology.",
            )
        if volume.get("persistent") is not True:
            _add(
                findings,
                "volume_not_persistent",
                "manifest.volumes",
                "Volume pilot phải được đánh dấu persistent=true.",
            )
