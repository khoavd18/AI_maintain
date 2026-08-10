"""Repository-binding tests grouped by checked-in surface."""

from __future__ import annotations

from ._repository_contract_scenarios import (
    Any,
    COMPOSE_NAME,
    Path,
    REPOSITORY_ROOT,
    _finding,
    _findings,
    _valid_document,
    _validate_repository_contract,
    _write_repository,
    deepcopy,
    json,
    pilot_contract_main,
    pytest,
    validate_deployment_manifest,
    validate_pilot_contract,
)


def test_unknown_fields_and_duplicate_declarations_are_ignored(tmp_path: Path) -> None:
    _write_repository(tmp_path)
    document = _valid_document()
    document["unknown"] = {"nested": True}
    document["release"]["unknown"] = True
    document["versions"]["unknown"] = True
    document["images"]["unknown"] = True
    document["required_environment_variables"].append(
        {"name": "DECLARED_ENV", "secret": True, "unknown": "ignored here"}
    )

    assert _findings(document, tmp_path)[1] == []


def test_checked_in_source_read_order_is_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_repository(tmp_path)
    original_read_text = Path.read_text
    reads: list[str] = []

    def recording_read(self: Path, *args: Any, **kwargs: Any) -> str:
        reads.append(self.relative_to(tmp_path).as_posix())
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", recording_read)

    assert _findings(_valid_document(), tmp_path)[1] == []
    assert reads == [
        COMPOSE_NAME,
        "Dockerfile",
        "frontend/Dockerfile",
        COMPOSE_NAME,
        COMPOSE_NAME,
        "frontend/package.json",
    ]


def test_preexisting_findings_are_preserved_and_new_findings_append(tmp_path: Path) -> None:
    _write_repository(tmp_path)
    existing = _finding("existing", "before", "Existing finding.")
    findings = [existing]
    document = _valid_document()
    document["versions"]["application"] = "wrong"

    result = _validate_repository_contract(document, tmp_path, findings)

    assert result is None
    assert findings == [
        existing,
        _finding(
            "application_version_mismatch",
            "manifest.versions.application",
            "Application version trong manifest không khớp runtime.",
        ),
    ]


@pytest.mark.parametrize("document", [None, [], "manifest", 1, True])
def test_unexpected_top_level_input_types_keep_attribute_error_boundary(
    tmp_path: Path,
    document: object,
) -> None:
    _write_repository(tmp_path)

    with pytest.raises(AttributeError):
        _validate_repository_contract(document, tmp_path, [])  # type: ignore[arg-type]


def test_public_facades_preserve_repository_findings_order_and_serialization() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / "deployment" / "pilot_manifest.json").read_text(encoding="utf-8")
    )
    manifest["versions"]["application"] = "wrong"
    manifest["release"]["alembic_revision"] = "wrong"
    original = deepcopy(manifest)
    ownership = REPOSITORY_ROOT / "deployment" / "operational_ownership.json"
    limitations = REPOSITORY_ROOT / "deployment" / "known_limitations.json"
    release_record = REPOSITORY_ROOT / "deployment" / "pilot_release_record.json"

    manifest_report = validate_deployment_manifest(manifest, repository_root=REPOSITORY_ROOT)
    contract_report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        release_record,
        repository_root=REPOSITORY_ROOT,
    )

    for report in (manifest_report, contract_report):
        repository_findings = tuple(
            finding
            for finding in report.findings
            if finding.code
            in {"application_version_mismatch", "canonical_migration_revision_mismatch"}
        )
        assert [finding.code for finding in repository_findings] == [
            "application_version_mismatch",
            "canonical_migration_revision_mismatch",
        ]
        assert repository_findings[0].as_dict() == {
            "code": "application_version_mismatch",
            "scope": "manifest.versions.application",
            "message": "Application version trong manifest không khớp runtime.",
            "severity": "blocker",
        }
    assert manifest == original


def test_manifest_only_cli_keeps_current_repository_root_and_ascii_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = pilot_contract_main(
        [
            "--manifest",
            str(REPOSITORY_ROOT / "deployment" / "pilot_manifest.json"),
            "--manifest-only",
            "--skip-environment",
        ]
    )
    output = capsys.readouterr().out
    report = json.loads(output)

    assert result == 2
    assert "compose_file_missing" in {finding["code"] for finding in report["findings"]}
    assert output.isascii()


def test_repository_contract_module_has_no_runtime_or_transaction_dependency() -> None:
    source = (
        REPOSITORY_ROOT
        / "src"
        / "reliability"
        / "pilot_contract"
        / "deployment_manifest"
        / "repository.py"
    ).read_text(encoding="utf-8")
    lowered = source.lower()

    assert "sqlalchemy" not in lowered
    assert "subprocess" not in lowered
    assert "os.environ" not in source
    assert "src.api" not in source
    assert "src.operations" not in source
    assert "src.repositories" not in source
    assert "src.reliability.pilot_contract.manifest" not in source
