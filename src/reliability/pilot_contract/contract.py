"""Public contract validation orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .constants import (
    GO,
    NO_GO,
    EXTERNAL_PILOT_NO_GO,
    ALLOWED_DECISIONS,
    JsonSource,
    ServiceProbe,
)

from .decision import evaluate_pilot_decision, _has_external_pilot_blocked_classification
from .documents import load_json_document, manifest_sha256
from .environment import _validate_environment
from .manifest import _validate_manifest_structure
from .ownership import _validate_limitations, _validate_ownership
from .release import (
    _validate_final_release_observation_presence,
    _validate_release_observations,
    _validate_release_record,
    _validate_service_reachability,
)
from .schemas import Finding, ValidationReport
from .support import (
    _validate_safe_document,
    _add,
    _has_blocker,
    _ordered_findings,
)


def validate_deployment_manifest(
    manifest: JsonSource,
    *,
    environment: Mapping[str, str] | None = None,
    actual_commit: str | None = None,
    actual_tag: str | None = None,
    actual_tag_target_commit: str | None = None,
    actual_migration_revision: str | None = None,
    service_probe: ServiceProbe | None = None,
    repository_root: str | Path | None = None,
) -> ValidationReport:
    """Validate deployment structure and any supplied runtime observations."""

    document = load_json_document(manifest)
    findings: list[Finding] = []
    root = Path(repository_root or Path.cwd()).resolve()
    _validate_safe_document(document, "manifest", findings)
    _validate_manifest_structure(document, root, findings)
    if environment is not None:
        _validate_environment(document, environment, root, findings)
    _validate_release_observations(
        document,
        environment=environment,
        actual_commit=actual_commit,
        actual_tag=actual_tag,
        actual_tag_target_commit=actual_tag_target_commit,
        actual_migration_revision=actual_migration_revision,
        findings=findings,
    )
    if service_probe is not None:
        _validate_service_reachability(document, service_probe, findings)
    ordered = _ordered_findings(findings)
    decision = NO_GO if _has_blocker(ordered) else GO
    return ValidationReport(decision, manifest_sha256(document), ordered)


def validate_pilot_contract(
    manifest: JsonSource,
    ownership: JsonSource,
    limitations: JsonSource,
    release_record: JsonSource,
    *,
    environment: Mapping[str, str] | None = None,
    actual_commit: str | None = None,
    actual_tag: str | None = None,
    actual_tag_target_commit: str | None = None,
    actual_migration_revision: str | None = None,
    service_probe: ServiceProbe | None = None,
    repository_root: str | Path | None = None,
) -> ValidationReport:
    """Validate the complete PM9 contract and calculate the pilot decision."""

    manifest_document = load_json_document(manifest)
    ownership_document = load_json_document(ownership)
    limitation_document = load_json_document(limitations)
    release_document = load_json_document(release_record)
    root = Path(repository_root or Path.cwd()).resolve()
    findings: list[Finding] = []

    for scope, document in (
        ("manifest", manifest_document),
        ("ownership", ownership_document),
        ("limitations", limitation_document),
        ("release_record", release_document),
    ):
        _validate_safe_document(document, scope, findings)

    _validate_manifest_structure(manifest_document, root, findings)
    if environment is not None:
        _validate_environment(manifest_document, environment, root, findings)
    _validate_release_observations(
        manifest_document,
        environment=environment,
        actual_commit=actual_commit,
        actual_tag=actual_tag,
        actual_tag_target_commit=actual_tag_target_commit,
        actual_migration_revision=actual_migration_revision,
        findings=findings,
    )
    if service_probe is not None:
        _validate_service_reachability(manifest_document, service_probe, findings)
    _validate_ownership(ownership_document, findings)
    _validate_limitations(limitation_document, findings)
    digest = manifest_sha256(manifest_document)
    _validate_release_record(
        release_document,
        manifest_document,
        ownership_document,
        limitation_document,
        digest,
        actual_commit,
        findings,
    )
    if release_document.get("record_status") == "final":
        _validate_final_release_observation_presence(
            environment=environment,
            actual_tag=actual_tag,
            actual_tag_target_commit=actual_tag_target_commit,
            actual_migration_revision=actual_migration_revision,
            findings=findings,
        )

    semantic_decision = evaluate_pilot_decision(
        release_document,
        ownership_document,
        limitation_document,
    )
    preliminary = NO_GO if _has_blocker(findings) else semantic_decision
    external_pilot_blocked = _has_external_pilot_blocked_classification(release_document)
    expected_declared = (
        EXTERNAL_PILOT_NO_GO if preliminary == NO_GO and external_pilot_blocked else preliminary
    )
    declared = release_document.get("final_decision")
    if declared not in ALLOWED_DECISIONS:
        _add(
            findings,
            "invalid_final_decision",
            "release_record",
            "Quyết định phải dùng đúng một giá trị trong danh sách cho phép.",
        )
    elif declared != expected_declared:
        _add(
            findings,
            "declared_decision_mismatch",
            "release_record",
            "Quyết định đã ghi không khớp kết quả tất định của contract.",
        )

    ordered = _ordered_findings(findings)
    decision = (
        EXTERNAL_PILOT_NO_GO
        if _has_blocker(ordered) and external_pilot_blocked
        else NO_GO
        if _has_blocker(ordered)
        else semantic_decision
    )
    return ValidationReport(decision, digest, ordered)

