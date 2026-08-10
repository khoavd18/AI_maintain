"""Deployment-storage tests grouped by storage contract dimension."""

from __future__ import annotations

from ._storage_scenarios import (
    Any,
    REPOSITORY_ROOT,
    REQUIRED_STORAGE_PATHS,
    _finding,
    _findings,
    _missing_path_finding,
    _valid_document,
    _validate_storage,
    deepcopy,
    json,
    manifest_module,
    pytest,
    validate_deployment_manifest,
    validate_pilot_contract,
)


@pytest.mark.parametrize("retention", [None, True, False, 0, 366, 7.0, "7"])
def test_backup_retention_requires_a_strict_integer_in_range(retention: object) -> None:
    document = _valid_document()
    document["storage"]["paths"]["backups"]["retention_keep_count"] = retention

    assert _findings(document)[1] == [
        _finding(
            "invalid_backup_retention",
            "manifest.storage.paths.backups.retention_keep_count",
            "Số bản backup giữ lại phải nằm trong khoảng 1..365.",
        )
    ]


@pytest.mark.parametrize("retention", [1, 365])
def test_backup_retention_boundaries_are_inclusive(retention: int) -> None:
    document = _valid_document()
    document["storage"]["paths"]["backups"]["retention_keep_count"] = retention

    assert _findings(document)[1] == []


def test_path_findings_follow_required_path_order_and_keep_blocker_serialization() -> None:
    document = _valid_document()
    for name in ("attachments", "analytics_source", "analytics_output"):
        document["storage"]["paths"][name]["container_path"] = "relative"
    document["storage"]["paths"]["backups"]["retention_keep_count"] = 0

    findings = _findings(document)[1]

    assert [finding.scope for finding in findings] == [
        "manifest.storage.paths.attachments",
        "manifest.storage.paths.analytics_source",
        "manifest.storage.paths.analytics_output",
        "manifest.storage.paths.backups.retention_keep_count",
    ]
    assert all(finding.severity == "blocker" for finding in findings)
    assert findings[-1].as_dict() == {
        "code": "invalid_backup_retention",
        "scope": "manifest.storage.paths.backups.retention_keep_count",
        "message": "Số bản backup giữ lại phải nằm trong khoảng 1..365.",
        "severity": "blocker",
    }


def test_preexisting_findings_are_preserved_and_new_findings_append() -> None:
    existing = _finding("existing", "before", "Existing finding.")
    findings = [existing]

    result = _validate_storage({}, REPOSITORY_ROOT, findings)

    assert result is None
    assert findings[0] is existing
    assert findings[1:] == [
        _finding(
            "allowed_roots_missing",
            "manifest.storage",
            "Storage contract phải khai báo allowed_roots.",
        ),
        *[_missing_path_finding(name) for name in REQUIRED_STORAGE_PATHS],
    ]


@pytest.mark.parametrize("document", [None, [], "manifest", 1, True])
def test_unexpected_top_level_input_types_keep_the_attribute_error_boundary(
    document: object,
) -> None:
    with pytest.raises(AttributeError):
        _validate_storage(document, REPOSITORY_ROOT, [])  # type: ignore[arg-type]


def test_public_facades_preserve_storage_findings_and_input_immutability() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / "deployment" / "pilot_manifest.json").read_text(encoding="utf-8")
    )
    manifest["storage"]["paths"]["attachments"]["relative_path"] = "../escape"
    manifest["storage"]["paths"]["backups"]["retention_keep_count"] = 0
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
        storage_findings = tuple(
            finding
            for finding in report.findings
            if finding.code in {"path_containment_violation", "invalid_backup_retention"}
        )
        assert [finding.code for finding in storage_findings] == [
            "invalid_backup_retention",
            "path_containment_violation",
        ]
        assert [finding.as_dict() for finding in storage_findings] == [
            {
                "code": "invalid_backup_retention",
                "scope": "manifest.storage.paths.backups.retention_keep_count",
                "message": "Số bản backup giữ lại phải nằm trong khoảng 1..365.",
                "severity": "blocker",
            },
            {
                "code": "path_containment_violation",
                "scope": "manifest.storage.paths.attachments",
                "message": "Storage path phải là đường dẫn tương đối nằm trong allowed root.",
                "severity": "blocker",
            },
        ]
    assert manifest == original


def test_storage_validator_remains_first_in_manifest_capability_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = json.loads(
        (REPOSITORY_ROOT / "deployment" / "pilot_manifest.json").read_text(encoding="utf-8")
    )
    calls: list[str] = []

    def recorder(name: str):
        def record(*args: Any, **kwargs: Any) -> None:
            calls.append(name)

        return record

    for name in (
        "_validate_storage",
        "_validate_environment_declarations",
        "_validate_repository_contract",
        "_validate_health_endpoints",
        "_validate_job_catalog",
        "_validate_runtime_settings",
    ):
        monkeypatch.setattr(manifest_module, name, recorder(name))

    manifest_module._validate_manifest_structure(document, REPOSITORY_ROOT, [])

    assert calls == [
        "_validate_storage",
        "_validate_environment_declarations",
        "_validate_repository_contract",
        "_validate_health_endpoints",
        "_validate_job_catalog",
        "_validate_runtime_settings",
    ]


def test_storage_declaration_module_has_no_runtime_or_transaction_dependency() -> None:
    source = (
        REPOSITORY_ROOT
        / "src"
        / "reliability"
        / "pilot_contract"
        / "deployment_manifest"
        / "storage.py"
    ).read_text(encoding="utf-8")
    lowered = source.lower()

    assert "sqlalchemy" not in lowered
    assert "subprocess" not in lowered
    assert "os.environ" not in source
    assert "src.api" not in source
    assert "src.operations" not in source
    assert "src.repositories" not in source
    assert "src.reliability.pilot_contract.manifest" not in source
