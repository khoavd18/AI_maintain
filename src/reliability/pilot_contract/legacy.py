"""Compatibility façade for the historical pilot-contract module."""

from __future__ import annotations

from .cli import main
from .constants import (
    ALLOWED_DECISIONS,
    CONDITIONAL_GO,
    CRITICAL_GATES,
    EXTERNAL_PILOT_NO_GO,
    GO,
    NO_GO,
    REQUIRED_LIMITATIONS,
    REQUIRED_OWNERS,
    REQUIRED_PILOT_ENVIRONMENT,
    REQUIRED_SERVICES,
    SECRET_ENVIRONMENT_NAMES,
    SUPPORTED_JOBS,
)
from .contract import validate_deployment_manifest, validate_pilot_contract
from .decision import evaluate_pilot_decision, generate_release_record
from .documents import load_json_document, manifest_sha256
from .redaction import redact_release_record
from .schemas import Finding, ValidationReport

__all__ = [
    "ALLOWED_DECISIONS",
    "CONDITIONAL_GO",
    "CRITICAL_GATES",
    "EXTERNAL_PILOT_NO_GO",
    "Finding",
    "GO",
    "NO_GO",
    "REQUIRED_LIMITATIONS",
    "REQUIRED_OWNERS",
    "REQUIRED_PILOT_ENVIRONMENT",
    "REQUIRED_SERVICES",
    "SECRET_ENVIRONMENT_NAMES",
    "SUPPORTED_JOBS",
    "ValidationReport",
    "evaluate_pilot_decision",
    "generate_release_record",
    "load_json_document",
    "main",
    "manifest_sha256",
    "redact_release_record",
    "validate_deployment_manifest",
    "validate_pilot_contract",
]

if __name__ == "__main__":
    raise SystemExit(main())

