"""Deployment-topology tests grouped by topology dimension."""

from __future__ import annotations

from ._topology_scenarios import (
    Any,
    REPOSITORY_ROOT,
    REQUIRED_SERVICES,
    TOPOLOGY_CODES,
    _ready_manifest,
    deepcopy,
    manifest_module,
    pytest,
    validate_deployment_manifest,
    validate_pilot_contract,
)


def test_public_facades_preserve_topology_findings_and_serialization() -> None:
    manifest = _ready_manifest()
    manifest["services"][0]["required"] = False
    manifest["ports"][0]["protocol"] = "TCP"
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
        owned = tuple(finding for finding in report.findings if finding.code in TOPOLOGY_CODES)
        assert [finding.code for finding in owned] == [
            "invalid_port_protocol",
            "service_not_required",
        ]
        assert owned[0].as_dict() == {
            "code": "invalid_port_protocol",
            "scope": f"manifest.ports.{manifest['ports'][0]['name']}",
            "message": "Port protocol phải là tcp hoặc udp.",
            "severity": "blocker",
        }
    assert manifest == original


def test_manifest_orchestration_preserves_capability_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _ready_manifest()
    calls: list[str] = []

    def artifact(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append("_validate_artifact_declarations")
        return dict(document["versions"])

    def topology(*args: Any, **kwargs: Any) -> set[str]:
        calls.append("_validate_service_topology")
        return set(REQUIRED_SERVICES)

    def recorder(name: str):
        def record(*args: Any, **kwargs: Any) -> None:
            calls.append(name)

        return record

    monkeypatch.setattr(manifest_module, "_validate_artifact_declarations", artifact)
    monkeypatch.setattr(manifest_module, "_validate_service_topology", topology)
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
        "_validate_artifact_declarations",
        "_validate_service_topology",
        "_validate_storage",
        "_validate_environment_declarations",
        "_validate_repository_contract",
        "_validate_health_endpoints",
        "_validate_job_catalog",
        "_validate_runtime_settings",
    ]


def test_service_topology_module_has_no_runtime_or_side_effect_dependency() -> None:
    source = (
        REPOSITORY_ROOT
        / "src"
        / "reliability"
        / "pilot_contract"
        / "deployment_manifest"
        / "topology.py"
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
