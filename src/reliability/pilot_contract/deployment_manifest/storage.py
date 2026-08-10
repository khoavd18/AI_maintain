"""Validate deployment-manifest storage roots and logical paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..constants import _ENV_NAME_RE
from ..document_shapes import _mapping
from ..findings import _add
from ..path_contracts import _safe_container_path, _safe_relative_path
from ..schemas import Finding


def _validate_storage(
    document: dict[str, Any],
    repository_root: Path,
    findings: list[Finding],
) -> None:
    storage = _mapping(document.get("storage"))
    roots = _mapping(storage.get("allowed_roots"))
    paths = _mapping(storage.get("paths"))
    if not roots:
        _add(
            findings,
            "allowed_roots_missing",
            "manifest.storage",
            "Storage contract phải khai báo allowed_roots.",
        )
    resolved_roots: dict[str, Path] = {}
    for name, root_value in roots.items():
        root_contract = _mapping(root_value)
        environment_name = root_contract.get("environment_variable")
        if (
            not isinstance(environment_name, str)
            or not _ENV_NAME_RE.fullmatch(environment_name)
            or root_contract.get("scope") != "host"
            or root_contract.get("outside_repository") is not True
            or set(root_contract) != {"environment_variable", "scope", "outside_repository"}
        ):
            _add(
                findings,
                "invalid_allowed_root",
                f"manifest.storage.allowed_roots.{name}",
                "Allowed root phải tham chiếu biến môi trường host nằm ngoài repository.",
            )
            continue
        resolved_roots[str(name)] = repository_root

    for required_path in ("attachments", "analytics_source", "analytics_output", "backups"):
        row = _mapping(paths.get(required_path))
        if not row:
            _add(
                findings,
                "required_storage_path_missing",
                f"manifest.storage.paths.{required_path}",
                "Thiếu storage path bắt buộc.",
            )
            continue
        root_name = row.get("root")
        relative_path = row.get("relative_path")
        if root_name not in resolved_roots:
            _add(
                findings,
                "storage_root_unknown",
                f"manifest.storage.paths.{required_path}",
                "Storage path tham chiếu allowed root không tồn tại.",
            )
            continue
        if not _safe_relative_path(relative_path):
            _add(
                findings,
                "path_containment_violation",
                f"manifest.storage.paths.{required_path}",
                "Storage path phải là đường dẫn tương đối nằm trong allowed root.",
            )
            continue
        target = (resolved_roots[str(root_name)] / str(relative_path)).resolve()
        if not target.is_relative_to(resolved_roots[str(root_name)]):
            _add(
                findings,
                "path_containment_violation",
                f"manifest.storage.paths.{required_path}",
                "Storage path thoát khỏi allowed root.",
            )
        if required_path != "backups":
            container_path = row.get("container_path")
            configuration_environment = row.get("configuration_environment")
            if (
                not _safe_container_path(container_path)
                or not isinstance(configuration_environment, str)
                or not _ENV_NAME_RE.fullmatch(configuration_environment)
            ):
                _add(
                    findings,
                    "invalid_container_storage_path",
                    f"manifest.storage.paths.{required_path}",
                    "Application storage phải có container path tuyệt đối và biến cấu hình.",
                )
        else:
            retention = row.get("retention_keep_count")
            if type(retention) is not int or not 1 <= retention <= 365:
                _add(
                    findings,
                    "invalid_backup_retention",
                    "manifest.storage.paths.backups.retention_keep_count",
                    "Số bản backup giữ lại phải nằm trong khoảng 1..365.",
                )
