"""Validate deployment manifest identity, release, version, and image declarations."""

from __future__ import annotations

from typing import Any

from ..constants import _EXACT_TAG_TARGET_COMMIT_RESOLUTION
from ..document_shapes import _mapping, _require_keys, _versioned
from ..document_values import _non_placeholder_text
from ..findings import _add
from ..schemas import Finding


def _validate_artifact_declarations(
    document: dict[str, Any],
    findings: list[Finding],
) -> dict[str, Any]:
    _require_keys(
        document,
        {
            "schema_version",
            "manifest_kind",
            "compose_file",
            "release",
            "versions",
            "images",
            "services",
            "ports",
            "volumes",
            "storage",
            "required_environment_variables",
            "health_endpoints",
            "scheduled_jobs",
            "worker",
            "retry_and_dead_letter",
            "operational_alerts",
            "database",
            "restore_prerequisites",
            "rollback",
            "production_readiness_claim",
        },
        "manifest",
        findings,
    )
    if not _versioned(document):
        _add(
            findings,
            "invalid_schema_version",
            "manifest",
            "Deployment manifest phải có schema_version rõ ràng.",
        )
    if document.get("manifest_kind") != "ai_maintenance_copilot_internal_pilot":
        _add(
            findings,
            "invalid_manifest_kind",
            "manifest",
            "Deployment manifest không đúng loại internal pilot.",
        )
    if document.get("production_readiness_claim") is not False:
        _add(
            findings,
            "production_readiness_claim_forbidden",
            "manifest",
            "Contract internal pilot không được tuyên bố production readiness.",
        )

    release = _mapping(document.get("release"))
    _require_keys(
        release,
        {
            "release_id",
            "commit_resolution",
            "tag_recommendation",
            "tag_status",
            "alembic_revision",
        },
        "manifest.release",
        findings,
    )
    commit_resolution = release.get("commit_resolution")
    if commit_resolution != _EXACT_TAG_TARGET_COMMIT_RESOLUTION:
        code = "invalid_commit_resolution"
        _add(
            findings,
            code,
            "manifest.release.commit_resolution",
            "Release commit phải được resolve từ exact Git tag target.",
        )
    if release.get("tag_status") not in {"checkpointed", "verified"}:
        _add(
            findings,
            "release_tag_pending",
            "manifest.release",
            "Git tag recommendation chưa được xác nhận tại checkpoint.",
        )
    for key in ("release_id", "tag_recommendation", "alembic_revision"):
        if not _non_placeholder_text(release.get(key)):
            _add(
                findings,
                "missing_release_identity",
                f"manifest.release.{key}",
                "Release identity còn thiếu hoặc đang là placeholder.",
            )

    versions = _mapping(document.get("versions"))
    required_versions = {
        "application",
        "frontend",
        "python",
        "node",
        "postgresql",
        "qdrant",
    }
    _require_keys(versions, required_versions, "manifest.versions", findings)
    for name in required_versions:
        if not _non_placeholder_text(versions.get(name)):
            _add(
                findings,
                "missing_component_version",
                f"manifest.versions.{name}",
                "Mọi runtime bắt buộc phải có version không phải placeholder.",
            )

    images = _mapping(document.get("images"))
    required_images = {
        "application",
        "frontend",
        "python_base",
        "node_base",
        "postgresql",
        "qdrant",
    }
    _require_keys(images, required_images, "manifest.images", findings)
    for name in required_images:
        value = images.get(name)
        invalid_digest = (
            isinstance(value, str)
            and "@sha256:" in value
            and len(value.rsplit("@sha256:", 1)[1]) != 64
        )
        if not _non_placeholder_text(value) or str(value).endswith(":latest") or invalid_digest:
            _add(
                findings,
                "invalid_image_reference",
                f"manifest.images.{name}",
                "Image reference phải rõ ràng và không được dùng thẻ latest.",
            )
    return versions
