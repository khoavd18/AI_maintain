"""Public report and finding schemas for the internal-pilot contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .constants import Severity

@dataclass(frozen=True, slots=True)
class Finding:
    """One deterministic, value-free contract finding."""

    code: str
    scope: str
    message: str
    severity: Severity = "blocker"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "scope": self.scope,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Reviewable result of one contract validation."""

    decision: str
    manifest_sha256: str
    findings: tuple[Finding, ...]

    @property
    def is_valid(self) -> bool:
        return not any(finding.severity == "blocker" for finding in self.findings)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "is_valid": self.is_valid,
            "manifest_sha256": self.manifest_sha256,
            "findings": [finding.as_dict() for finding in self.findings],
        }

    def __getitem__(self, key: str) -> Any:
        """Allow concise dictionary-style use in small operator scripts."""

        return self.as_dict()[key]


