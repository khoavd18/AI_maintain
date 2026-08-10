"""Characterize ordered internal-pilot release-record validation."""

# ruff: noqa: F401 - split suites import their explicit scenario dependencies

from __future__ import annotations

from copy import deepcopy

from inspect import signature

import json

from pathlib import Path

from typing import Any

import pytest

import src.reliability.pilot_contract.release as release_module

from src.reliability.pilot_contract import (
    CRITICAL_GATES,
    generate_release_record,
    manifest_sha256,
    validate_pilot_contract,
)

from src.reliability.pilot_contract.cli import main as pilot_contract_main

from src.reliability.pilot_contract.contract import (
    _validate_release_record as contract_release_record_validator,
)

from src.reliability.pilot_contract.release import _validate_release_record

from src.reliability.pilot_contract.release_record.evidence import (
    _validate_release_record_evidence,
)

from src.reliability.pilot_contract.release_record.gates import _validate_release_record_gates

from src.reliability.pilot_contract.release_record.governance import (
    _validate_release_record_governance,
)

from src.reliability.pilot_contract.release_record.identity import (
    _validate_release_record_identity,
)

from src.reliability.pilot_contract.release_record.risks import _validate_release_record_risks

from src.reliability.pilot_contract.schemas import Finding

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

DEPLOYMENT_ROOT = REPOSITORY_ROOT / "deployment"

OBSERVED_COMMIT = "a" * 40


def _load(name: str) -> dict[str, Any]:
    return json.loads((DEPLOYMENT_ROOT / name).read_text(encoding="utf-8"))


def _ready_manifest() -> dict[str, Any]:
    manifest = _load("pilot_manifest.json")
    manifest["release"]["tag_status"] = "verified"
    manifest["rollback"]["rehearsal_status"] = "passed"
    return manifest


def _ready_ownership() -> dict[str, Any]:
    ownership = _load("operational_ownership.json")
    ownership["record_status"] = "approved"
    for key, assignment in ownership["assignments"].items():
        assignment.update(
            {
                "assigned_role": f"internal_pilot_{key}_role",
                "approved_internal_channel": "approved-internal-operations-channel",
                "status": "assigned",
                "approval_evidence_links": [f"evidence/ownership/{key}.json"],
            }
        )
    ownership["incident_communication"].update(
        {
            "status": "configured",
            "primary_internal_channel": "approved-internal-incident-channel",
            "fallback_internal_channel": "approved-internal-escalation-channel",
            "approval_evidence_links": ["evidence/ownership/incident-path.json"],
        }
    )
    ownership["support_coverage"].update(
        {
            "status": "confirmed",
            "support_hours": "business-hours-in-declared-timezone",
            "after_hours_assumption": "pilot-paused-until-support-window",
            "approval_evidence_links": ["evidence/ownership/coverage.json"],
        }
    )
    ownership["escalation_path"].update(
        {"status": "configured", "approval_evidence_links": ["evidence/ownership/path.json"]}
    )
    return ownership


def _ready_limitations() -> dict[str, Any]:
    limitations = _load("known_limitations.json")
    limitations["record_status"] = "accepted"
    for limitation in limitations["limitations"]:
        limitation.update(
            {
                "owner_role": "internal_pilot_governance_role",
                "acceptance_status": "accepted",
                "accepted_by_role": "internal_pilot_business_owner_role",
                "accepted_at_utc": "2026-07-26T12:00:00Z",
                "acceptance_evidence_links": [f"evidence/limitations/{limitation['id']}.json"],
            }
        )
    return limitations


def _ready_documents() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = _ready_manifest()
    ownership = _ready_ownership()
    limitations = _ready_limitations()
    record = generate_release_record(
        manifest,
        ownership,
        limitations,
        gate_results={
            gate_id: {
                "status": "passed",
                "evidence_links": [f"evidence/gates/{gate_id}.json"],
            }
            for gate_id in CRITICAL_GATES
        },
        evidence_links=["evidence/releases/pm9.json"],
        generated_at_utc="2026-07-26T12:00:00Z",
        release_commit=OBSERVED_COMMIT,
    )
    record["record_status"] = "final"
    for section_name in (
        "backup_validation",
        "restore_validation",
        "attachment_restore",
        "secret_rotation",
    ):
        record[section_name] = {
            "status": "passed",
            "validated_at_utc": "2026-07-26T12:00:00Z",
            "evidence_links": [f"evidence/gates/{section_name}.json"],
        }
    record["load_and_soak_profiles"] = {
        "status": "passed",
        "summaries": [{"scope": "approved-pilot-equivalent-host"}],
        "evidence_links": ["evidence/gates/load-and-soak.json"],
    }
    return manifest, ownership, limitations, record


def _findings(
    *,
    record: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    ownership: dict[str, Any] | None = None,
    limitations: dict[str, Any] | None = None,
    digest: str | None = None,
    actual_commit: str | None = OBSERVED_COMMIT,
) -> tuple[None, list[Finding]]:
    ready_manifest, ready_ownership, ready_limitations, ready_record = _ready_documents()
    selected_manifest = manifest or ready_manifest
    findings: list[Finding] = []
    result = _validate_release_record(
        record or ready_record,
        selected_manifest,
        ownership or ready_ownership,
        limitations or ready_limitations,
        digest or manifest_sha256(selected_manifest),
        actual_commit,
        findings,
    )
    return result, findings


def _finding(code: str, scope: str, message: str) -> Finding:
    return Finding(code=code, scope=scope, message=message)


def _only(findings: list[Finding], codes: set[str]) -> list[Finding]:
    return [finding for finding in findings if finding.code in codes]
