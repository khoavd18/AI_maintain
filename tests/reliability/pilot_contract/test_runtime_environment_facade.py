"""Runtime-environment tests grouped by validation capability."""

from __future__ import annotations

from ._runtime_environment_scenarios import (
    Any,
    DEPLOYMENT_ROOT,
    REPOSITORY_ROOT,
    _ready_environment,
    _ready_manifest,
    _validate_environment,
    _validate_identity_environment,
    _validate_network_environment,
    _validate_runtime_environment_settings,
    _validate_security_environment,
    _validate_storage_environment,
    environment_module,
    json,
    pilot_contract_main,
    pytest,
    signature,
    validate_deployment_manifest,
)


@pytest.mark.parametrize("manifest", [None, [], "manifest", 1, True])
def test_unexpected_manifest_types_keep_attribute_error_boundary(manifest: object) -> None:
    with pytest.raises(AttributeError):
        _validate_environment(  # type: ignore[arg-type]
            manifest,
            _ready_environment(),
            REPOSITORY_ROOT,
            [],
        )


@pytest.mark.parametrize("environment", [None, [], "environment", 1, True])
def test_unexpected_environment_types_keep_attribute_error_boundary(environment: object) -> None:
    with pytest.raises(AttributeError):
        _validate_environment(  # type: ignore[arg-type]
            _ready_manifest(),
            environment,
            REPOSITORY_ROOT,
            [],
        )


def test_public_facade_preserves_environment_order_and_serialization() -> None:
    manifest = _ready_manifest()
    environment = _ready_environment()
    environment["APP_ENVIRONMENT"] = "development"
    environment["STORAGE_BACKEND"] = "csv"
    original = dict(environment)

    report = validate_deployment_manifest(
        manifest,
        environment=environment,
        repository_root=REPOSITORY_ROOT,
    )
    owned = tuple(
        finding
        for finding in report.findings
        if finding.code in {"pilot_environment_required", "postgresql_storage_required"}
    )

    assert [finding.code for finding in owned] == [
        "pilot_environment_required",
        "postgresql_storage_required",
    ]
    assert owned[0].as_dict() == {
        "code": "pilot_environment_required",
        "scope": "environment.APP_ENVIRONMENT",
        "message": "APP_ENVIRONMENT phải là pilot.",
        "severity": "blocker",
    }
    assert environment == original


def test_cli_with_injected_environment_keeps_ascii_runtime_finding(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = _ready_environment()
    environment["APP_ENVIRONMENT"] = "development"
    monkeypatch.setattr("src.reliability.pilot_contract.cli.os.environ", environment)

    result = pilot_contract_main(
        [
            "--manifest",
            str(DEPLOYMENT_ROOT / "pilot_manifest.json"),
            "--manifest-only",
        ]
    )
    output = capsys.readouterr().out
    report = json.loads(output)

    assert result == 2
    assert "pilot_environment_required" in {finding["code"] for finding in report["findings"]}
    assert output.isascii()


def test_runtime_environment_orchestration_order_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def recorder(name: str):
        def record(*args: Any, **kwargs: Any) -> None:
            calls.append(name)

        return record

    for name in (
        "_validate_security_environment",
        "_validate_network_environment",
        "_validate_identity_environment",
        "_validate_runtime_environment_settings",
        "_validate_storage_environment",
    ):
        monkeypatch.setattr(environment_module, name, recorder(name))

    environment_module._validate_environment(
        _ready_manifest(),
        _ready_environment(),
        REPOSITORY_ROOT,
        [],
    )

    assert calls == [
        "_validate_security_environment",
        "_validate_network_environment",
        "_validate_identity_environment",
        "_validate_runtime_environment_settings",
        "_validate_storage_environment",
    ]


def test_runtime_environment_capability_signatures_and_facade_bindings_are_stable() -> None:
    assert list(signature(_validate_security_environment).parameters) == [
        "manifest",
        "environment",
        "findings",
    ]
    assert list(signature(_validate_network_environment).parameters) == [
        "manifest",
        "environment",
        "findings",
    ]
    assert list(signature(_validate_identity_environment).parameters) == [
        "manifest",
        "environment",
        "findings",
    ]
    assert list(signature(_validate_runtime_environment_settings).parameters) == [
        "manifest",
        "environment",
        "findings",
    ]
    assert list(signature(_validate_storage_environment).parameters) == [
        "manifest",
        "environment",
        "repository_root",
        "findings",
    ]
    assert environment_module._validate_security_environment is _validate_security_environment
    assert environment_module._validate_network_environment is _validate_network_environment
    assert environment_module._validate_identity_environment is _validate_identity_environment
    assert (
        environment_module._validate_runtime_environment_settings
        is _validate_runtime_environment_settings
    )
    assert environment_module._validate_storage_environment is _validate_storage_environment


@pytest.mark.parametrize(
    "module_name",
    [
        "security.py",
        "network.py",
        "identity.py",
        "settings.py",
        "storage.py",
    ],
)
def test_runtime_environment_modules_have_no_forbidden_side_effect_dependency(
    module_name: str,
) -> None:
    source = (
        REPOSITORY_ROOT
        / "src"
        / "reliability"
        / "pilot_contract"
        / "runtime_environment"
        / module_name
    ).read_text(encoding="utf-8")
    lowered = source.lower()

    assert "sqlalchemy" not in lowered
    assert "subprocess" not in lowered
    assert "os.environ" not in source
    assert "src.api" not in source
    assert "src.operations" not in source
    assert "src.repositories" not in source
    assert "src.reliability.pilot_contract.environment" not in source
