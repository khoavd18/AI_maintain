"""Release-record tests grouped by validation capability."""

from __future__ import annotations

from ._release_record_scenarios import (
    Any,
    OBSERVED_COMMIT,
    Path,
    REPOSITORY_ROOT,
    _findings,
    _ready_documents,
    _ready_limitations,
    _ready_manifest,
    _ready_ownership,
    _validate_release_record,
    _validate_release_record_evidence,
    _validate_release_record_gates,
    _validate_release_record_governance,
    _validate_release_record_identity,
    _validate_release_record_risks,
    json,
    manifest_sha256,
    pilot_contract_main,
    pytest,
    release_module,
    signature,
    validate_pilot_contract,
)


def test_unknown_record_fields_are_ignored() -> None:
    *_, record = _ready_documents()
    record["unknown"] = True
    record["release"]["unknown"] = True
    record["gates"][0]["unknown"] = True
    record["open_risks"].append(
        {"id": "R", "status": "open", "severity": "low", "category": "usability", "unknown": True}
    )

    assert _findings(record=record)[1] == []


@pytest.mark.parametrize("record", [None, 1, True])
def test_non_iterable_record_types_keep_type_error_boundary(record: object) -> None:
    with pytest.raises(TypeError):
        _validate_release_record(  # type: ignore[arg-type]
            record,
            _ready_manifest(),
            _ready_ownership(),
            _ready_limitations(),
            "digest",
            OBSERVED_COMMIT,
            [],
        )


@pytest.mark.parametrize("record", [[], "record"])
def test_iterable_non_mapping_record_types_keep_attribute_error_boundary(record: object) -> None:
    with pytest.raises(AttributeError):
        _validate_release_record(  # type: ignore[arg-type]
            record,
            _ready_manifest(),
            _ready_ownership(),
            _ready_limitations(),
            "digest",
            OBSERVED_COMMIT,
            [],
        )


def test_public_facade_preserves_release_finding_order_and_serialization() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    record["record_kind"] = "wrong"
    record["production_readiness_claim"] = True

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        actual_commit=OBSERVED_COMMIT,
        repository_root=REPOSITORY_ROOT,
    )
    owned = tuple(
        finding
        for finding in report.findings
        if finding.code in {"invalid_release_record_kind", "production_readiness_claim_forbidden"}
    )

    assert [finding.code for finding in owned] == [
        "invalid_release_record_kind",
        "production_readiness_claim_forbidden",
    ]
    assert owned[0].as_dict() == {
        "code": "invalid_release_record_kind",
        "scope": "release_record.record_kind",
        "message": "Release record kind không khớp internal-pilot contract.",
        "severity": "blocker",
    }


def test_cli_preserves_release_finding_and_ascii_serialization(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest, ownership, limitations, record = _ready_documents()
    record["record_kind"] = "wrong"
    paths = []
    for name, document in (
        ("manifest.json", manifest),
        ("ownership.json", ownership),
        ("limitations.json", limitations),
        ("release.json", record),
    ):
        path = tmp_path / name
        path.write_text(json.dumps(document), encoding="utf-8")
        paths.append(path)

    result = pilot_contract_main(
        [
            "--manifest",
            str(paths[0]),
            "--ownership",
            str(paths[1]),
            "--limitations",
            str(paths[2]),
            "--release-record",
            str(paths[3]),
            "--actual-commit",
            OBSERVED_COMMIT,
            "--skip-environment",
        ]
    )
    output = capsys.readouterr().out

    assert result == 2
    assert "invalid_release_record_kind" in {
        finding["code"] for finding in json.loads(output)["findings"]
    }
    assert output.isascii()


def test_release_record_orchestration_order_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def recorder(name: str):
        def record(*args: Any, **kwargs: Any) -> None:
            calls.append(name)

        return record

    for name in (
        "_validate_release_record_identity",
        "_validate_release_record_evidence",
        "_validate_release_record_gates",
        "_validate_release_record_risks",
        "_validate_release_record_governance",
    ):
        monkeypatch.setattr(release_module, name, recorder(name))
    manifest, ownership, limitations, record = _ready_documents()

    release_module._validate_release_record(
        record,
        manifest,
        ownership,
        limitations,
        manifest_sha256(manifest),
        OBSERVED_COMMIT,
        [],
    )

    assert calls == [
        "_validate_release_record_identity",
        "_validate_release_record_evidence",
        "_validate_release_record_gates",
        "_validate_release_record_risks",
        "_validate_release_record_governance",
    ]


def test_release_record_capability_signatures_and_facade_bindings_are_stable() -> None:
    assert list(signature(_validate_release_record_identity).parameters) == [
        "record",
        "manifest",
        "digest",
        "actual_commit",
        "findings",
    ]
    for function in (
        _validate_release_record_evidence,
        _validate_release_record_gates,
        _validate_release_record_risks,
    ):
        assert list(signature(function).parameters) == ["record", "findings"]
    assert list(signature(_validate_release_record_governance).parameters) == [
        "record",
        "manifest",
        "ownership",
        "limitations",
        "findings",
    ]
    assert release_module._validate_release_record_identity is _validate_release_record_identity
    assert release_module._validate_release_record_evidence is _validate_release_record_evidence
    assert release_module._validate_release_record_gates is _validate_release_record_gates
    assert release_module._validate_release_record_risks is _validate_release_record_risks
    assert release_module._validate_release_record_governance is _validate_release_record_governance


@pytest.mark.parametrize(
    "module_name",
    [
        "identity.py",
        "evidence.py",
        "gates.py",
        "risks.py",
        "governance.py",
    ],
)
def test_release_record_modules_have_no_side_effect_or_reverse_dependency(
    module_name: str,
) -> None:
    source = (
        REPOSITORY_ROOT / "src" / "reliability" / "pilot_contract" / "release_record" / module_name
    ).read_text(encoding="utf-8")
    lowered = source.lower()

    assert "sqlalchemy" not in lowered
    assert "subprocess" not in lowered
    assert "os.environ" not in source
    assert "pathlib" not in lowered
    assert "src.api" not in source
    assert "src.operations" not in source
    assert "src.repositories" not in source
    assert "src.reliability.pilot_contract.release" not in source
