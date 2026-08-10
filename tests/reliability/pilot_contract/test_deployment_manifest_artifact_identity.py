"""Artifact-declaration tests grouped by contract dimension."""

# ruff: noqa: F811 - imported pytest fixture is named by test parameters

from __future__ import annotations

from ._artifact_scenarios import (
    Finding,
    REQUIRED_RELEASE,
    REQUIRED_TOP_LEVEL,
    _artifact_findings,
    _finding,
    _findings,
    _ready_manifest,
    _validate_artifact_declarations,
    deepcopy,
    isolate_downstream,  # noqa: F401 - registers the split-suite fixture
    manifest_artifact_validator,
    pytest,
    signature,
)


def test_valid_artifact_declarations_are_deterministic_and_immutable(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    original = deepcopy(document)

    first_result, first = _findings(document)
    second_result, second = _findings(document)

    assert first_result is None
    assert second_result is None
    assert first == []
    assert second == first
    assert document == original

    direct_findings: list[Finding] = []
    versions = _validate_artifact_declarations(document, direct_findings)
    assert direct_findings == []
    assert versions == document["versions"]
    assert versions is not document["versions"]
    assert list(signature(_validate_artifact_declarations).parameters) == [
        "document",
        "findings",
    ]
    assert manifest_artifact_validator is _validate_artifact_declarations


def test_top_level_required_keys_are_sorted_before_identity_findings(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    for key in ("worker", "rollback", "database"):
        document.pop(key)

    assert _artifact_findings(document) == [
        _finding(
            "required_key_missing",
            f"manifest.{key}",
            f"Thiếu required key: {key}.",
        )
        for key in ("database", "rollback", "worker")
    ]


def test_required_top_level_contract_matches_the_current_closed_shape(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    for key in REQUIRED_TOP_LEVEL:
        document.setdefault(key, None)

    assert not {
        finding.scope
        for finding in _artifact_findings(document)
        if finding.code == "required_key_missing" and finding.scope.startswith("manifest.")
    }


@pytest.mark.parametrize("schema_version", [None, "", " ", True, False, 1.0, [], {}])
def test_schema_version_type_and_whitespace_behavior_is_strict(
    isolate_downstream: None,
    schema_version: object,
) -> None:
    document = _ready_manifest()
    document["schema_version"] = schema_version

    assert _artifact_findings(document) == [
        _finding(
            "invalid_schema_version",
            "manifest",
            "Deployment manifest phải có schema_version rõ ràng.",
        )
    ]


@pytest.mark.parametrize("schema_version", [0, 1, "1", " 1 "])
def test_current_schema_version_accepts_non_boolean_ints_and_trimmed_nonempty_text(
    isolate_downstream: None,
    schema_version: object,
) -> None:
    document = _ready_manifest()
    document["schema_version"] = schema_version

    assert _artifact_findings(document) == []


@pytest.mark.parametrize(
    "manifest_kind",
    [None, "", "AI_MAINTENANCE_COPILOT_INTERNAL_PILOT", " ai_maintenance_copilot_internal_pilot"],
)
def test_manifest_kind_is_exact_without_case_or_whitespace_normalization(
    isolate_downstream: None,
    manifest_kind: object,
) -> None:
    document = _ready_manifest()
    document["manifest_kind"] = manifest_kind

    assert _artifact_findings(document) == [
        _finding(
            "invalid_manifest_kind",
            "manifest",
            "Deployment manifest không đúng loại internal pilot.",
        )
    ]


@pytest.mark.parametrize("claim", [None, True, 0, 1, "false", ""])
def test_production_readiness_claim_requires_the_false_singleton(
    isolate_downstream: None,
    claim: object,
) -> None:
    document = _ready_manifest()
    document["production_readiness_claim"] = claim

    assert _artifact_findings(document) == [
        _finding(
            "production_readiness_claim_forbidden",
            "manifest",
            "Contract internal pilot không được tuyên bố production readiness.",
        )
    ]


@pytest.mark.parametrize("release", [None, [], "release", 1, True, {}])
def test_missing_or_non_mapping_release_accumulates_exact_findings(
    isolate_downstream: None,
    release: object,
) -> None:
    document = _ready_manifest()
    document["release"] = release

    expected = [
        _finding(
            "required_key_missing",
            f"manifest.release.{key}",
            f"Thiếu required key: {key}.",
        )
        for key in sorted(REQUIRED_RELEASE)
    ]
    expected.extend(
        [
            _finding(
                "invalid_commit_resolution",
                "manifest.release.commit_resolution",
                "Release commit phải được resolve từ exact Git tag target.",
            ),
            _finding(
                "release_tag_pending",
                "manifest.release",
                "Git tag recommendation chưa được xác nhận tại checkpoint.",
            ),
        ]
    )
    expected.extend(
        _finding(
            "missing_release_identity",
            f"manifest.release.{key}",
            "Release identity còn thiếu hoặc đang là placeholder.",
        )
        for key in ("release_id", "tag_recommendation", "alembic_revision")
    )
    assert _artifact_findings(document) == expected


@pytest.mark.parametrize(
    "commit_resolution",
    [None, "", "EXACT_TAG_TARGET", " exact_tag_target", "exact_tag_target "],
)
def test_commit_resolution_is_exact(
    isolate_downstream: None,
    commit_resolution: object,
) -> None:
    document = _ready_manifest()
    document["release"]["commit_resolution"] = commit_resolution

    assert _artifact_findings(document) == [
        _finding(
            "invalid_commit_resolution",
            "manifest.release.commit_resolution",
            "Release commit phải được resolve từ exact Git tag target.",
        )
    ]


@pytest.mark.parametrize("tag_status", [None, "", "pending", "VERIFIED", " verified"])
def test_release_tag_status_accepts_only_two_exact_values(
    isolate_downstream: None,
    tag_status: object,
) -> None:
    document = _ready_manifest()
    document["release"]["tag_status"] = tag_status

    assert _artifact_findings(document) == [
        _finding(
            "release_tag_pending",
            "manifest.release",
            "Git tag recommendation chưa được xác nhận tại checkpoint.",
        )
    ]


@pytest.mark.parametrize("tag_status", ["checkpointed", "verified"])
def test_release_tag_status_valid_values_are_accepted(
    isolate_downstream: None,
    tag_status: str,
) -> None:
    document = _ready_manifest()
    document["release"]["tag_status"] = tag_status

    assert _artifact_findings(document) == []
