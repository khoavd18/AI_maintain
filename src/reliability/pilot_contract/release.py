"""Release observations and release-record validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .constants import ServiceProbe, _COMMIT_RE
from .document_shapes import _list_of_mappings, _mapping
from .document_values import _git_identity_matches
from .findings import _add

from .schemas import Finding
from .release_record.evidence import _validate_release_record_evidence
from .release_record.gates import _validate_release_record_gates
from .release_record.governance import _validate_release_record_governance
from .release_record.identity import _validate_release_record_identity
from .release_record.risks import _validate_release_record_risks


def _validate_release_observations(
    manifest: dict[str, Any],
    *,
    environment: Mapping[str, str] | None,
    actual_commit: str | None,
    actual_tag: str | None,
    actual_tag_target_commit: str | None,
    actual_migration_revision: str | None,
    findings: list[Finding],
) -> None:
    release = _mapping(manifest.get("release"))
    if actual_commit is not None and not _COMMIT_RE.fullmatch(actual_commit):
        _add(
            findings,
            "release_commit_observation_invalid",
            "release_observation.commit",
            "Observed Git commit phải là full 40-character SHA.",
        )
    environment_commit = environment.get("RELEASE_GIT_COMMIT") if environment is not None else None
    if (
        actual_commit is not None
        and environment_commit is not None
        and not _git_identity_matches(environment_commit, actual_commit)
    ):
        _add(
            findings,
            "release_environment_commit_mismatch",
            "release_observation.commit",
            "Runtime release commit không khớp exact tagged checkout.",
        )
    if actual_tag is not None and actual_tag != release.get("tag_recommendation"):
        _add(
            findings,
            "release_tag_mismatch",
            "release_observation.tag",
            "Deployed Git tag không khớp tag recommendation.",
        )
    if actual_tag_target_commit is not None and not _COMMIT_RE.fullmatch(actual_tag_target_commit):
        _add(
            findings,
            "release_tag_target_observation_invalid",
            "release_observation.tag_target_commit",
            "Observed Git tag target phải là full 40-character SHA.",
        )
    if (
        actual_commit is not None
        and actual_tag_target_commit is not None
        and not _git_identity_matches(actual_tag_target_commit, actual_commit)
    ):
        _add(
            findings,
            "release_tag_target_commit_mismatch",
            "release_observation.tag_target_commit",
            "Observed exact tag target không khớp checkout commit.",
        )
    if actual_migration_revision is not None and actual_migration_revision != release.get(
        "alembic_revision"
    ):
        _add(
            findings,
            "migration_revision_mismatch",
            "release_observation.migration",
            "Alembic revision đang chạy không khớp release contract.",
        )


def _validate_service_reachability(
    manifest: dict[str, Any],
    probe: ServiceProbe,
    findings: list[Finding],
) -> None:
    for service in _list_of_mappings(manifest.get("services")):
        if service.get("required") is not True:
            continue
        name = str(service.get("name", "unknown"))
        try:
            reachable = probe(service) is True
        except Exception:  # The report must not echo probe exception or connection data.
            reachable = False
        if not reachable:
            _add(
                findings,
                "required_service_unreachable",
                f"service_probe.{name}",
                f"Service bắt buộc chưa reachable: {name}.",
            )


def _validate_release_record(
    record: dict[str, Any],
    manifest: dict[str, Any],
    ownership: dict[str, Any],
    limitations: dict[str, Any],
    digest: str,
    actual_commit: str | None,
    findings: list[Finding],
) -> None:
    _validate_release_record_identity(record, manifest, digest, actual_commit, findings)
    _validate_release_record_evidence(record, findings)
    _validate_release_record_gates(record, findings)
    _validate_release_record_risks(record, findings)
    _validate_release_record_governance(record, manifest, ownership, limitations, findings)


def _validate_final_release_observation_presence(
    *,
    environment: Mapping[str, str] | None,
    actual_tag: str | None,
    actual_tag_target_commit: str | None,
    actual_migration_revision: str | None,
    findings: list[Finding],
) -> None:
    if environment is None:
        _add(
            findings,
            "release_environment_observation_missing",
            "release_observation.environment",
            "Final release validation cần protected environment observation.",
        )
    if actual_tag is None:
        _add(
            findings,
            "release_tag_observation_missing",
            "release_observation.tag",
            "Final release validation cần observed exact Git tag.",
        )
    if actual_tag_target_commit is None:
        _add(
            findings,
            "release_tag_target_observation_missing",
            "release_observation.tag_target_commit",
            "Final release validation cần observed exact Git tag-target commit.",
        )
    if actual_migration_revision is None:
        _add(
            findings,
            "migration_observation_missing",
            "release_observation.migration",
            "Final release validation cần observed Alembic revision.",
        )
