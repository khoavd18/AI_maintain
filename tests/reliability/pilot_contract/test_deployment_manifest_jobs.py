"""Characterize the closed scheduled-job manifest contract."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from src.reliability.pilot_contract import SUPPORTED_JOBS, validate_deployment_manifest
from src.reliability.pilot_contract.deployment_manifest.jobs import _validate_job_catalog
from src.reliability.pilot_contract.manifest import (
    _validate_job_catalog as manifest_job_catalog_validator,
)
from src.reliability.pilot_contract.schemas import Finding


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _valid_document() -> dict[str, Any]:
    return {
        "scheduled_jobs": [{"job_type": name, "enabled": True} for name in sorted(SUPPORTED_JOBS)]
    }


def _findings(document: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    _validate_job_catalog(document, findings)
    return findings


def test_exact_supported_catalog_is_valid_deterministic_and_not_mutated() -> None:
    document = _valid_document()
    original = deepcopy(document)

    first = _findings(document)
    second = _findings(document)

    assert first == []
    assert second == first
    assert document == original
    assert manifest_job_catalog_validator is _validate_job_catalog


def test_missing_supported_job_keeps_exact_finding_contract() -> None:
    document = _valid_document()
    document["scheduled_jobs"] = [
        row for row in document["scheduled_jobs"] if row["job_type"] != "analytics_refresh"
    ]

    assert _findings(document) == [
        Finding(
            code="supported_job_missing",
            scope="manifest.scheduled_jobs.analytics_refresh",
            message=("Closed catalog phải khai báo job analytics_refresh với enabled rõ ràng."),
        )
    ]


def test_unsupported_job_keeps_closed_catalog_and_rejects_arbitrary_execution() -> None:
    document = _valid_document()
    document["scheduled_jobs"].append({"job_type": "arbitrary_shell", "enabled": True})

    assert _findings(document) == [
        Finding(
            code="unsupported_job",
            scope="manifest.scheduled_jobs.arbitrary_shell",
            message="Job ngoài closed catalog: arbitrary_shell.",
        )
    ]


def test_duplicate_job_keeps_exact_scope_and_message() -> None:
    document = _valid_document()
    document["scheduled_jobs"].append({"job_type": "preventive_generation", "enabled": False})

    assert _findings(document) == [
        Finding(
            code="duplicate_job",
            scope="manifest.scheduled_jobs.preventive_generation",
            message="Job bị khai báo trùng.",
        )
    ]


def test_job_enabled_and_configuration_must_be_explicit_and_closed() -> None:
    document = _valid_document()
    document["scheduled_jobs"][0] = {
        "job_type": document["scheduled_jobs"][0]["job_type"],
        "enabled": "yes",
        "command": "python -m arbitrary.module",
    }
    name = document["scheduled_jobs"][0]["job_type"]

    assert _findings(document) == [
        Finding(
            code="job_enabled_not_explicit",
            scope=f"manifest.scheduled_jobs.{name}",
            message="Mỗi job phải có enabled kiểu boolean.",
        ),
        Finding(
            code="job_configuration_not_closed",
            scope=f"manifest.scheduled_jobs.{name}",
            message=("Deployment manifest không được nhận cấu hình executable tùy ý."),
        ),
    ]


def test_scalar_and_missing_job_type_keep_indexed_and_catalog_scopes() -> None:
    document = _valid_document()
    document["scheduled_jobs"] = [42, {"enabled": True}, *document["scheduled_jobs"]]

    assert _findings(document) == [
        Finding(
            code="list_entry_not_object",
            scope="manifest.scheduled_jobs.0",
            message="Mỗi phần tử trong danh sách contract phải là JSON object.",
        ),
        Finding(
            code="invalid_job_type",
            scope="manifest.scheduled_jobs",
            message="Mỗi job phải có job_type.",
        ),
    ]


def test_non_list_catalog_fails_closed_and_reports_every_missing_job() -> None:
    findings = _findings({"scheduled_jobs": {"job_type": "preventive_generation"}})

    assert findings[0] == Finding(
        code="invalid_job_catalog",
        scope="manifest.scheduled_jobs",
        message="scheduled_jobs phải là list.",
    )
    assert [finding.scope for finding in findings[1:]] == [
        f"manifest.scheduled_jobs.{name}" for name in sorted(SUPPORTED_JOBS)
    ]
    assert {finding.code for finding in findings[1:]} == {"supported_job_missing"}


def test_public_manifest_validation_uses_the_extracted_catalog_validator() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / "deployment" / "pilot_manifest.json").read_text(encoding="utf-8")
    )
    manifest["scheduled_jobs"].append({"job_type": "arbitrary_shell", "enabled": True})
    direct = _findings(manifest)

    report = validate_deployment_manifest(
        manifest,
        repository_root=REPOSITORY_ROOT,
    )
    public_job_findings = {
        finding
        for finding in report.findings
        if finding.scope.startswith("manifest.scheduled_jobs")
    }

    assert public_job_findings == set(direct)
    assert "unsupported_job" in report.codes


def test_job_catalog_module_has_no_runtime_or_persistence_dependency() -> None:
    source = (
        REPOSITORY_ROOT
        / "src"
        / "reliability"
        / "pilot_contract"
        / "deployment_manifest"
        / "jobs.py"
    ).read_text(encoding="utf-8")
    lowered = source.lower()

    assert "sqlalchemy" not in lowered
    assert "subprocess" not in lowered
    assert "src.operations" not in source
    assert "src.repositories.postgres" not in source
