"""Bind deployment declarations to checked-in runtime source metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.release import APPLICATION_VERSION, CANONICAL_SCHEMA_REVISION

from ..constants import _COMPOSE_REQUIRED_ENV_RE
from ..document_shapes import _list_of_mappings, _mapping
from ..findings import _add
from ..path_contracts import _safe_relative_path
from ..schemas import Finding


def _validate_repository_contract(
    document: dict[str, Any],
    repository_root: Path,
    findings: list[Finding],
) -> None:
    """Bind the manifest to the checked-in Compose and runtime release sources."""

    compose_relative = document.get("compose_file")
    if not _safe_relative_path(compose_relative):
        _add(
            findings,
            "invalid_compose_file",
            "manifest.compose_file",
            "Compose file phải là đường dẫn tương đối nằm trong repository.",
        )
        return
    compose_path = (repository_root / str(compose_relative)).resolve()
    if not compose_path.is_relative_to(repository_root) or not compose_path.is_file():
        _add(
            findings,
            "compose_file_missing",
            "manifest.compose_file",
            "Không tìm thấy Compose file đã khai báo.",
        )
        return
    try:
        compose_text = compose_path.read_text(encoding="utf-8")
    except OSError:
        _add(
            findings,
            "compose_file_unreadable",
            "manifest.compose_file",
            "Không thể đọc Compose file đã khai báo.",
        )
        return

    declarations = _list_of_mappings(document.get("required_environment_variables"))
    declared_names = {row.get("name") for row in declarations if isinstance(row.get("name"), str)}
    compose_required = set(_COMPOSE_REQUIRED_ENV_RE.findall(compose_text))
    for name in sorted(compose_required - declared_names):
        _add(
            findings,
            "compose_environment_not_declared",
            f"manifest.required_environment_variables.{name}",
            f"Biến bắt buộc của Compose chưa có trong manifest: {name}.",
        )

    release = _mapping(document.get("release"))
    versions = _mapping(document.get("versions"))
    if versions.get("application") != APPLICATION_VERSION:
        _add(
            findings,
            "application_version_mismatch",
            "manifest.versions.application",
            "Application version trong manifest không khớp runtime.",
        )
    if release.get("alembic_revision") != CANONICAL_SCHEMA_REVISION:
        _add(
            findings,
            "canonical_migration_revision_mismatch",
            "manifest.release.alembic_revision",
            "Alembic revision trong manifest không khớp schema head của ứng dụng.",
        )

    images = _mapping(document.get("images"))
    source_expectations = (
        (
            repository_root / "Dockerfile",
            f"FROM {images.get('python_base', '')}",
            "manifest.images.python_base",
        ),
        (
            repository_root / "frontend" / "Dockerfile",
            f"FROM {images.get('node_base', '')}",
            "manifest.images.node_base",
        ),
        (
            compose_path,
            f"image: {images.get('postgresql', '')}",
            "manifest.images.postgresql",
        ),
        (
            compose_path,
            f"image: {images.get('qdrant', '')}",
            "manifest.images.qdrant",
        ),
    )
    for source_path, expected_text, scope in source_expectations:
        try:
            source_text = source_path.read_text(encoding="utf-8")
        except OSError:
            _add(
                findings,
                "runtime_source_unreadable",
                scope,
                "Không thể đọc runtime source để đối chiếu version.",
            )
            continue
        if not expected_text.strip() or expected_text not in source_text:
            _add(
                findings,
                "runtime_image_mismatch",
                scope,
                "Image trong manifest không khớp deployment source.",
            )

    package_path = repository_root / "frontend" / "package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _add(
            findings,
            "frontend_package_unreadable",
            "manifest.versions.frontend",
            "Không thể đọc frontend package metadata để đối chiếu version.",
        )
        return
    dependencies = _mapping(package.get("dependencies"))
    if package.get("version") != versions.get("frontend"):
        _add(
            findings,
            "frontend_version_mismatch",
            "manifest.versions.frontend",
            "Frontend version trong manifest không khớp package metadata.",
        )
    if dependencies.get("next") != versions.get("nextjs"):
        _add(
            findings,
            "nextjs_version_mismatch",
            "manifest.versions.nextjs",
            "Next.js version trong manifest không khớp package metadata.",
        )
