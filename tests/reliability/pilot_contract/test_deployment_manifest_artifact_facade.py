"""Artifact-declaration tests grouped by contract dimension."""

# ruff: noqa: F811 - imported pytest fixture is named by test parameters

from __future__ import annotations

from ._artifact_scenarios import (
    ARTIFACT_CODES,
    Path,
    REPOSITORY_ROOT,
    _ready_manifest,
    deepcopy,
    isolate_downstream,  # noqa: F401 - registers the split-suite fixture
    json,
    manifest_module,
    pilot_contract_main,
    pytest,
    validate_deployment_manifest,
    validate_pilot_contract,
)


@pytest.mark.parametrize("document", [None, 1, True])
def test_non_iterable_top_level_types_keep_type_error_boundary(
    isolate_downstream: None,
    document: object,
) -> None:
    with pytest.raises(TypeError):
        manifest_module._validate_manifest_structure(  # type: ignore[arg-type]
            document,
            REPOSITORY_ROOT,
            [],
        )


@pytest.mark.parametrize("document", [[], "manifest"])
def test_iterable_non_mapping_top_level_types_keep_attribute_error_boundary(
    isolate_downstream: None,
    document: object,
) -> None:
    with pytest.raises(AttributeError):
        manifest_module._validate_manifest_structure(  # type: ignore[arg-type]
            document,
            REPOSITORY_ROOT,
            [],
        )


def test_public_facades_keep_artifact_finding_order_and_serialization() -> None:
    manifest = _ready_manifest()
    manifest["manifest_kind"] = "wrong"
    manifest["production_readiness_claim"] = True
    original = deepcopy(manifest)
    ownership = REPOSITORY_ROOT / "deployment" / "operational_ownership.json"
    limitations = REPOSITORY_ROOT / "deployment" / "known_limitations.json"
    release_record = REPOSITORY_ROOT / "deployment" / "pilot_release_record.json"

    reports = (
        validate_deployment_manifest(manifest, repository_root=REPOSITORY_ROOT),
        validate_pilot_contract(
            manifest,
            ownership,
            limitations,
            release_record,
            repository_root=REPOSITORY_ROOT,
        ),
    )

    for report in reports:
        owned = tuple(finding for finding in report.findings if finding.code in ARTIFACT_CODES)
        assert [finding.code for finding in owned] == [
            "invalid_manifest_kind",
            "production_readiness_claim_forbidden",
        ]
        assert owned[0].as_dict() == {
            "code": "invalid_manifest_kind",
            "scope": "manifest",
            "message": "Deployment manifest không đúng loại internal pilot.",
            "severity": "blocker",
        }
    assert manifest == original


def test_cli_preserves_artifact_finding_and_ascii_serialization(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = _ready_manifest()
    manifest["manifest_kind"] = "wrong"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = pilot_contract_main(
        [
            "--manifest",
            str(manifest_path),
            "--manifest-only",
            "--skip-environment",
        ]
    )
    output = capsys.readouterr().out
    report = json.loads(output)

    assert result == 2
    assert "invalid_manifest_kind" in {finding["code"] for finding in report["findings"]}
    assert output.isascii()


def test_artifact_declaration_module_has_no_runtime_or_side_effect_dependency() -> None:
    source = (
        REPOSITORY_ROOT
        / "src"
        / "reliability"
        / "pilot_contract"
        / "deployment_manifest"
        / "artifacts.py"
    ).read_text(encoding="utf-8")
    lowered = source.lower()

    assert "sqlalchemy" not in lowered
    assert "subprocess" not in lowered
    assert "os.environ" not in source
    assert "pathlib" not in lowered
    assert "src.api" not in source
    assert "src.operations" not in source
    assert "src.repositories" not in source
    assert "src.reliability.pilot_contract.manifest" not in source
