"""Validate injected host and container storage paths for the pilot."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..document_shapes import _mapping
from ..findings import _add
from ..path_contracts import _safe_relative_path
from ..schemas import Finding
from .integers import _validate_integer_environment_match


def _validate_storage_environment(
    manifest: dict[str, Any],
    environment: Mapping[str, str],
    repository_root: Path,
    findings: list[Finding],
) -> None:
    storage = _mapping(manifest.get("storage"))
    roots = _mapping(storage.get("allowed_roots"))
    paths = _mapping(storage.get("paths"))
    resolved_roots: dict[str, Path] = {}
    for root_name, root_value in roots.items():
        root_contract = _mapping(root_value)
        environment_name = root_contract.get("environment_variable")
        value = environment.get(str(environment_name), "")
        if not value:
            continue
        candidate = Path(value)
        try:
            resolved = candidate.resolve()
            valid = candidate.is_absolute() and not (
                resolved == repository_root or resolved.is_relative_to(repository_root)
            )
        except (OSError, RuntimeError):
            valid = False
            resolved = candidate
        if not valid:
            _add(
                findings,
                "environment_root_containment_violation",
                f"environment.{environment_name}",
                f"{environment_name} phải là absolute root nằm ngoài repository.",
            )
            continue
        resolved_roots[str(root_name)] = resolved

    data_root = resolved_roots.get("data")
    backup_root = resolved_roots.get("backup")
    if (
        data_root is not None
        and backup_root is not None
        and (
            data_root == backup_root
            or data_root.is_relative_to(backup_root)
            or backup_root.is_relative_to(data_root)
        )
    ):
        _add(
            findings,
            "storage_roots_overlap",
            "environment.PILOT_BACKUP_ROOT",
            "Pilot data root và backup root phải tách biệt, không lồng nhau.",
        )

    for path_name, path_value in paths.items():
        row = _mapping(path_value)
        root = resolved_roots.get(str(row.get("root")))
        relative_path = row.get("relative_path")
        if root is not None and _safe_relative_path(relative_path):
            target = (root / str(relative_path)).resolve()
            if not target.is_relative_to(root):
                _add(
                    findings,
                    "environment_path_containment_violation",
                    f"manifest.storage.paths.{path_name}",
                    "Configured host path thoát khỏi allowed root.",
                )
        configuration_name = row.get("configuration_environment")
        if isinstance(configuration_name, str):
            configured_path = environment.get(configuration_name)
            if configured_path and configured_path != row.get("container_path"):
                _add(
                    findings,
                    "container_path_environment_mismatch",
                    f"environment.{configuration_name}",
                    f"{configuration_name} không khớp container storage path.",
                )
    backup_row = _mapping(paths.get("backups"))
    _validate_integer_environment_match(
        environment,
        "PILOT_BACKUP_RETENTION_COUNT",
        backup_row.get("retention_keep_count"),
        findings,
    )
