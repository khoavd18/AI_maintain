"""Validate injected release and image identity against the manifest."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..constants import _COMMIT_RE
from ..document_shapes import _mapping
from ..findings import _add
from ..schemas import Finding


def _validate_identity_environment(
    manifest: dict[str, Any],
    environment: Mapping[str, str],
    findings: list[Finding],
) -> None:
    release = _mapping(manifest.get("release"))
    release_environment = {
        "RELEASE_IDENTIFIER": release.get("release_id"),
        "RELEASE_GIT_TAG": release.get("tag_recommendation"),
        "RELEASE_ALEMBIC_REVISION": release.get("alembic_revision"),
    }
    for name, expected in release_environment.items():
        if environment.get(name) and environment.get(name) != expected:
            _add(
                findings,
                "release_environment_mismatch",
                f"environment.{name}",
                f"{name} không khớp release manifest.",
            )
    release_commit = environment.get("RELEASE_GIT_COMMIT")
    if release_commit and not _COMMIT_RE.fullmatch(release_commit):
        _add(
            findings,
            "release_environment_commit_invalid",
            "environment.RELEASE_GIT_COMMIT",
            "RELEASE_GIT_COMMIT phải là full 40-character Git SHA.",
        )

    images = _mapping(manifest.get("images"))
    for name, expected in {
        "PILOT_APP_IMAGE": images.get("application"),
        "PILOT_FRONTEND_IMAGE": images.get("frontend"),
    }.items():
        if environment.get(name) and environment.get(name) != expected:
            _add(
                findings,
                "image_environment_mismatch",
                f"environment.{name}",
                f"{name} không khớp image reference trong manifest.",
            )
