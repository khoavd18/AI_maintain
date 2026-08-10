"""Artifact-declaration tests grouped by contract dimension."""

# ruff: noqa: F811 - imported pytest fixture is named by test parameters

from __future__ import annotations

from ._artifact_scenarios import (
    REQUIRED_IMAGES,
    REQUIRED_VERSIONS,
    _artifact_findings,
    _finding,
    _ready_manifest,
    isolate_downstream,  # noqa: F401 - registers the split-suite fixture
    pytest,
)


@pytest.mark.parametrize("value", [None, "", " ", "TBD", "replace-with-tag", 1, True])
def test_release_identity_values_use_non_placeholder_text_contract(
    isolate_downstream: None,
    value: object,
) -> None:
    document = _ready_manifest()
    document["release"]["release_id"] = value

    assert _artifact_findings(document) == [
        _finding(
            "missing_release_identity",
            "manifest.release.release_id",
            "Release identity còn thiếu hoặc đang là placeholder.",
        )
    ]


@pytest.mark.parametrize("versions", [None, [], "versions", 1, True, {}])
def test_missing_or_non_mapping_versions_preserve_required_and_set_iteration_order(
    isolate_downstream: None,
    versions: object,
) -> None:
    document = _ready_manifest()
    document["versions"] = versions

    expected = [
        _finding(
            "required_key_missing",
            f"manifest.versions.{name}",
            f"Thiếu required key: {name}.",
        )
        for name in sorted(REQUIRED_VERSIONS)
    ]
    expected.extend(
        _finding(
            "missing_component_version",
            f"manifest.versions.{name}",
            "Mọi runtime bắt buộc phải có version không phải placeholder.",
        )
        for name in REQUIRED_VERSIONS
    )
    assert _artifact_findings(document) == expected


@pytest.mark.parametrize("value", [None, "", " ", "TODO", "replace_with_version", 1, True])
def test_component_versions_require_non_placeholder_text(
    isolate_downstream: None,
    value: object,
) -> None:
    document = _ready_manifest()
    document["versions"]["python"] = value

    assert _artifact_findings(document) == [
        _finding(
            "missing_component_version",
            "manifest.versions.python",
            "Mọi runtime bắt buộc phải có version không phải placeholder.",
        )
    ]


@pytest.mark.parametrize("images", [None, [], "images", 1, True, {}])
def test_missing_or_non_mapping_images_preserve_required_and_set_iteration_order(
    isolate_downstream: None,
    images: object,
) -> None:
    document = _ready_manifest()
    document["images"] = images

    expected = [
        _finding(
            "required_key_missing",
            f"manifest.images.{name}",
            f"Thiếu required key: {name}.",
        )
        for name in sorted(REQUIRED_IMAGES)
    ]
    expected.extend(
        _finding(
            "invalid_image_reference",
            f"manifest.images.{name}",
            "Image reference phải rõ ràng và không được dùng thẻ latest.",
        )
        for name in REQUIRED_IMAGES
    )
    assert _artifact_findings(document) == expected


@pytest.mark.parametrize(
    "value",
    [None, "", " ", "TBD", "repo/image:latest", "repo/image@sha256:abc", 1, True],
)
def test_image_references_keep_exact_placeholder_latest_and_digest_rules(
    isolate_downstream: None,
    value: object,
) -> None:
    document = _ready_manifest()
    document["images"]["application"] = value

    assert _artifact_findings(document) == [
        _finding(
            "invalid_image_reference",
            "manifest.images.application",
            "Image reference phải rõ ràng và không được dùng thẻ latest.",
        )
    ]


@pytest.mark.parametrize(
    "value",
    ["repo/image:LATEST", "repo/image@sha256:" + "z" * 64, "repo/image:v1"],
)
def test_image_reference_legacy_case_and_digest_content_are_preserved(
    isolate_downstream: None,
    value: str,
) -> None:
    document = _ready_manifest()
    document["images"]["application"] = value

    assert _artifact_findings(document) == []


def test_unknown_artifact_fields_are_ignored(isolate_downstream: None) -> None:
    document = _ready_manifest()
    document["unknown"] = True
    document["release"]["unknown"] = True
    document["versions"]["unknown"] = "value"
    document["images"]["unknown"] = "value"

    assert _artifact_findings(document) == []
