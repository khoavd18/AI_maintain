"""Characterize deployment-manifest environment declarations and ordering."""

from __future__ import annotations

from copy import deepcopy
from inspect import signature
import json
from pathlib import Path
from typing import Any

import pytest

import src.reliability.pilot_contract.manifest as manifest_module
from src.reliability.pilot_contract import (
    REQUIRED_PILOT_ENVIRONMENT,
    SECRET_ENVIRONMENT_NAMES,
    validate_deployment_manifest,
    validate_pilot_contract,
)
from src.reliability.pilot_contract.deployment_manifest.environment import (
    _validate_environment_declarations,
)
from src.reliability.pilot_contract.manifest import (
    _validate_environment_declarations as manifest_environment_declaration_validator,
)
from src.reliability.pilot_contract.schemas import Finding


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _valid_document() -> dict[str, Any]:
    return {
        "required_environment_variables": [
            {"name": name, "secret": name in SECRET_ENVIRONMENT_NAMES}
            for name in sorted(REQUIRED_PILOT_ENVIRONMENT)
        ]
    }


def _findings(document: dict[str, Any]) -> tuple[None, list[Finding]]:
    findings: list[Finding] = []
    result = _validate_environment_declarations(document, findings)
    return result, findings


def _replace_declaration(document: dict[str, Any], target_name: str, **updates: Any) -> None:
    row = next(
        row for row in document["required_environment_variables"] if row["name"] == target_name
    )
    row.update(updates)


def _missing_findings(*, include_invalid_contract: bool) -> list[Finding]:
    findings: list[Finding] = []
    if include_invalid_contract:
        findings.append(
            Finding(
                code="invalid_environment_contract",
                scope="manifest.required_environment_variables",
                message=(
                    "required_environment_variables phải là list chỉ chứa tên và secret flag."
                ),
            )
        )
    findings.extend(
        Finding(
            code="required_environment_name_missing",
            scope=f"manifest.required_environment_variables.{name}",
            message=f"Thiếu tên environment variable bắt buộc: {name}.",
        )
        for name in sorted(REQUIRED_PILOT_ENVIRONMENT)
    )
    findings.extend(
        Finding(
            code="secret_environment_not_marked",
            scope=f"manifest.required_environment_variables.{name}",
            message=f"{name} phải được đánh dấu secret=true.",
        )
        for name in sorted(SECRET_ENVIRONMENT_NAMES)
    )
    return findings


def test_valid_environment_declarations_are_deterministic_and_not_mutated() -> None:
    document = _valid_document()
    original = deepcopy(document)

    first_result, first = _findings(document)
    second_result, second = _findings(document)

    assert first_result is None
    assert second_result is None
    assert first == []
    assert second == first
    assert document == original
    assert list(signature(_validate_environment_declarations).parameters) == [
        "document",
        "findings",
    ]
    assert manifest_environment_declaration_validator is _validate_environment_declarations


@pytest.mark.parametrize("raw", [None, {"name": "DATABASE_URL"}, "DATABASE_URL"])
def test_missing_or_non_list_contract_fails_closed_in_exact_order(raw: object) -> None:
    document = {} if raw is None else {"required_environment_variables": raw}

    assert _findings(document)[1] == _missing_findings(include_invalid_contract=True)


def test_empty_environment_list_omits_only_the_invalid_contract_finding() -> None:
    assert _findings({"required_environment_variables": []})[1] == _missing_findings(
        include_invalid_contract=False
    )


def test_scalar_declaration_keeps_indexed_scope_without_hiding_valid_rows() -> None:
    document = _valid_document()
    document["required_environment_variables"].insert(0, 42)

    assert _findings(document)[1] == [
        Finding(
            code="list_entry_not_object",
            scope="manifest.required_environment_variables.0",
            message="Mỗi phần tử trong danh sách contract phải là JSON object.",
        )
    ]


@pytest.mark.parametrize("name", ["A", "A1", "A_B", "CUSTOM_SETTING"])
def test_additional_uppercase_environment_names_are_allowed(name: str) -> None:
    document = _valid_document()
    document["required_environment_variables"].append({"name": name, "secret": False})

    assert _findings(document)[1] == []


@pytest.mark.parametrize(
    "name",
    [None, "", "database_url", " DATABASE_URL", "_DATABASE_URL", "1DATABASE_URL", "DATABASE-URL"],
)
def test_environment_names_are_case_sensitive_untrimmed_and_pattern_bounded(
    name: object,
) -> None:
    document = _valid_document()
    _replace_declaration(document, "DATABASE_URL", name=name)

    assert _findings(document)[1] == [
        Finding(
            code="invalid_environment_name",
            scope="manifest.required_environment_variables",
            message="Environment variable phải có tên uppercase hợp lệ.",
        ),
        Finding(
            code="required_environment_name_missing",
            scope="manifest.required_environment_variables.DATABASE_URL",
            message="Thiếu tên environment variable bắt buộc: DATABASE_URL.",
        ),
        Finding(
            code="secret_environment_not_marked",
            scope="manifest.required_environment_variables.DATABASE_URL",
            message="DATABASE_URL phải được đánh dấu secret=true.",
        ),
    ]


def test_invalid_name_short_circuits_shape_and_secret_checks_for_that_row() -> None:
    document = _valid_document()
    document["required_environment_variables"].append(
        {"name": None, "secret": "true", "value": "ignored-by-current-contract"}
    )

    assert _findings(document)[1] == [
        Finding(
            code="invalid_environment_name",
            scope="manifest.required_environment_variables",
            message="Environment variable phải có tên uppercase hợp lệ.",
        )
    ]


def test_duplicate_secret_declaration_uses_the_last_flag_for_secret_marking() -> None:
    document = _valid_document()
    document["required_environment_variables"].append({"name": "DATABASE_URL", "secret": False})

    assert _findings(document)[1] == [
        Finding(
            code="duplicate_environment_name",
            scope="manifest.required_environment_variables.DATABASE_URL",
            message="Environment variable bị khai báo trùng.",
        ),
        Finding(
            code="secret_environment_not_marked",
            scope="manifest.required_environment_variables.DATABASE_URL",
            message="DATABASE_URL phải được đánh dấu secret=true.",
        ),
    ]


@pytest.mark.parametrize("secret", [None, 0, 1, "false", "true"])
def test_non_secret_declarations_require_a_real_boolean_flag(secret: object) -> None:
    document = _valid_document()
    _replace_declaration(document, "APP_ENVIRONMENT", secret=secret)

    assert _findings(document)[1] == [
        Finding(
            code="environment_secret_flag_missing",
            scope="manifest.required_environment_variables.APP_ENVIRONMENT",
            message="Mỗi environment variable phải có secret flag kiểu boolean.",
        )
    ]


@pytest.mark.parametrize("secret", [None, 0, 1, "true"])
def test_required_secrets_reject_boolean_like_values_before_marking_check(
    secret: object,
) -> None:
    document = _valid_document()
    _replace_declaration(document, "DATABASE_URL", secret=secret)

    assert _findings(document)[1] == [
        Finding(
            code="environment_secret_flag_missing",
            scope="manifest.required_environment_variables.DATABASE_URL",
            message="Mỗi environment variable phải có secret flag kiểu boolean.",
        ),
        Finding(
            code="secret_environment_not_marked",
            scope="manifest.required_environment_variables.DATABASE_URL",
            message="DATABASE_URL phải được đánh dấu secret=true.",
        ),
    ]


def test_required_secret_may_be_explicit_boolean_false_but_is_not_marked() -> None:
    document = _valid_document()
    _replace_declaration(document, "DATABASE_URL", secret=False)

    assert _findings(document)[1] == [
        Finding(
            code="secret_environment_not_marked",
            scope="manifest.required_environment_variables.DATABASE_URL",
            message="DATABASE_URL phải được đánh dấu secret=true.",
        )
    ]


def test_unknown_fields_produce_one_closed_shape_finding() -> None:
    document = _valid_document()
    _replace_declaration(
        document,
        "APP_ENVIRONMENT",
        value="pilot",
        source="deployment",
    )

    assert _findings(document)[1] == [
        Finding(
            code="environment_value_in_manifest",
            scope="manifest.required_environment_variables.APP_ENVIRONMENT",
            message="Manifest chỉ được ghi tên environment variable và secret flag.",
        )
    ]


def test_public_facades_preserve_serialized_secret_marking_finding() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / "deployment" / "pilot_manifest.json").read_text(encoding="utf-8")
    )
    _replace_declaration(manifest, "DATABASE_URL", secret=False)
    expected = _findings(manifest)[1]
    ownership = REPOSITORY_ROOT / "deployment" / "operational_ownership.json"
    limitations = REPOSITORY_ROOT / "deployment" / "known_limitations.json"
    release_record = REPOSITORY_ROOT / "deployment" / "pilot_release_record.json"

    manifest_report = validate_deployment_manifest(
        manifest,
        repository_root=REPOSITORY_ROOT,
    )
    contract_report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        release_record,
        repository_root=REPOSITORY_ROOT,
    )

    for report in (manifest_report, contract_report):
        environment_findings = tuple(
            finding
            for finding in report.findings
            if finding.scope == "manifest.required_environment_variables.DATABASE_URL"
            and finding.code == "secret_environment_not_marked"
        )
        assert environment_findings == tuple(expected)
        assert environment_findings[0].as_dict() == {
            "code": "secret_environment_not_marked",
            "scope": "manifest.required_environment_variables.DATABASE_URL",
            "message": "DATABASE_URL phải được đánh dấu secret=true.",
            "severity": "blocker",
        }


def test_manifest_keeps_environment_declaration_validator_order(
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


def test_environment_declaration_module_has_no_runtime_or_side_effect_dependency() -> None:
    source = (
        REPOSITORY_ROOT
        / "src"
        / "reliability"
        / "pilot_contract"
        / "deployment_manifest"
        / "environment.py"
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
