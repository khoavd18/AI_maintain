"""Characterize deployment-manifest health declarations and ordering."""

from __future__ import annotations

from copy import deepcopy
from inspect import signature
import json
from pathlib import Path
from typing import Any

import pytest

from src.reliability.pilot_contract import validate_deployment_manifest
from src.reliability.pilot_contract.deployment_manifest.health import (
    _validate_health_endpoints,
)
from src.reliability.pilot_contract.manifest import (
    _validate_health_endpoints as manifest_health_endpoint_validator,
)
from src.reliability.pilot_contract.schemas import Finding


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SERVICE_NAMES = {"api", "worker"}


def _endpoint(kind: str, path: str) -> dict[str, Any]:
    return {
        "service": "api",
        "kind": kind,
        "path": path,
        "expected_status": [200],
    }


def _valid_document() -> dict[str, Any]:
    return {
        "health_endpoints": [
            _endpoint("liveness", "/health/live"),
            _endpoint("readiness", "/health/ready"),
            _endpoint("worker_readiness", "/health/worker"),
        ]
    }


def _findings(
    document: dict[str, Any],
    service_names: set[str] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    _validate_health_endpoints(document, service_names or SERVICE_NAMES, findings)
    return findings


def test_valid_health_endpoints_are_deterministic_and_not_mutated() -> None:
    document = _valid_document()
    original = deepcopy(document)

    first = _findings(document)
    second = _findings(document)

    assert first == []
    assert second == first
    assert document == original
    assert list(signature(_validate_health_endpoints).parameters) == [
        "document",
        "service_names",
        "findings",
    ]
    assert manifest_health_endpoint_validator is _validate_health_endpoints


def test_empty_and_non_list_health_contracts_report_the_three_required_kinds() -> None:
    expected = {
        Finding(
            code="health_endpoint_missing",
            scope=f"manifest.health_endpoints.{kind}",
            message=f"Thiếu endpoint {kind}.",
        )
        for kind in {"liveness", "readiness", "worker_readiness"}
    }

    assert set(_findings({"health_endpoints": []})) == expected
    assert set(_findings({"health_endpoints": {"kind": "liveness"}})) == expected


def test_scalar_health_row_keeps_indexed_scope_and_does_not_hide_valid_rows() -> None:
    document = _valid_document()
    document["health_endpoints"].insert(0, 42)

    assert _findings(document) == [
        Finding(
            code="list_entry_not_object",
            scope="manifest.health_endpoints.0",
            message="Mỗi phần tử trong danh sách contract phải là JSON object.",
        )
    ]


def test_duplicate_health_endpoint_uses_service_and_path_identity() -> None:
    document = _valid_document()
    document["health_endpoints"].append(deepcopy(document["health_endpoints"][0]))

    assert _findings(document) == [
        Finding(
            code="duplicate_health_endpoint",
            scope="manifest.health_endpoints",
            message="Health endpoint bị khai báo trùng.",
        )
    ]


def test_endpoint_checks_keep_unknown_path_status_order_and_blocker_severity() -> None:
    document = _valid_document()
    document["health_endpoints"][0].update(
        {
            "service": "arbitrary_service",
            "path": "health/live",
            "expected_status": [True],
        }
    )

    assert _findings(document) == [
        Finding(
            code="health_service_unknown",
            scope="manifest.health_endpoints",
            message="Health endpoint tham chiếu service không tồn tại.",
            severity="blocker",
        ),
        Finding(
            code="invalid_health_path",
            scope="manifest.health_endpoints",
            message="Health endpoint phải là URL path tương đối theo host.",
            severity="blocker",
        ),
        Finding(
            code="invalid_health_status",
            scope="manifest.health_endpoints",
            message="Health endpoint phải khai báo expected HTTP status.",
            severity="blocker",
        ),
    ]


@pytest.mark.parametrize(
    "path",
    [None, "health/live", "https://example.test/health", "/health/../ready"],
)
def test_health_path_must_be_host_relative_and_contained(path: object) -> None:
    document = _valid_document()
    document["health_endpoints"][0]["path"] = path

    assert _findings(document) == [
        Finding(
            code="invalid_health_path",
            scope="manifest.health_endpoints",
            message="Health endpoint phải là URL path tương đối theo host.",
        )
    ]


@pytest.mark.parametrize(
    "statuses",
    [None, [], [True], [99], [600], ["200"]],
)
def test_health_statuses_require_non_empty_integer_http_codes(statuses: object) -> None:
    document = _valid_document()
    document["health_endpoints"][0]["expected_status"] = statuses

    assert _findings(document) == [
        Finding(
            code="invalid_health_status",
            scope="manifest.health_endpoints",
            message="Health endpoint phải khai báo expected HTTP status.",
        )
    ]


def test_public_manifest_report_preserves_health_findings_and_global_order() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / "deployment" / "pilot_manifest.json").read_text(encoding="utf-8")
    )
    manifest["health_endpoints"][0].update(
        {
            "service": "arbitrary_service",
            "path": "health/live",
            "expected_status": [True],
        }
    )
    service_names = {
        row["name"]
        for row in manifest["services"]
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    direct = _findings(manifest, service_names)

    report = validate_deployment_manifest(
        manifest,
        repository_root=REPOSITORY_ROOT,
    )
    public_health_findings = tuple(
        finding
        for finding in report.findings
        if finding.scope.startswith("manifest.health_endpoints")
    )

    assert set(public_health_findings) == set(direct)
    assert tuple(finding.code for finding in public_health_findings) == (
        "health_service_unknown",
        "invalid_health_path",
        "invalid_health_status",
    )


def test_health_endpoint_module_has_no_runtime_or_persistence_dependency() -> None:
    source = (
        REPOSITORY_ROOT
        / "src"
        / "reliability"
        / "pilot_contract"
        / "deployment_manifest"
        / "health.py"
    ).read_text(encoding="utf-8")
    lowered = source.lower()

    assert "sqlalchemy" not in lowered
    assert "subprocess" not in lowered
    assert "src.api" not in source
    assert "src.operations" not in source
    assert "src.repositories" not in source
    assert "src.reliability.pilot_contract.manifest" not in source
