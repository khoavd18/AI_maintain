"""Finding accumulation, blocker detection, and deterministic ordering."""

from __future__ import annotations

from collections.abc import Sequence

from .constants import Severity
from .schemas import Finding


def _add(
    findings: list[Finding],
    code: str,
    scope: str,
    message: str,
    severity: Severity = "blocker",
) -> None:
    findings.append(Finding(code=code, scope=scope, message=message, severity=severity))


def _has_blocker(findings: Sequence[Finding]) -> bool:
    return any(finding.severity == "blocker" for finding in findings)


def _ordered_findings(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    unique = {
        (finding.code, finding.scope, finding.message, finding.severity): finding
        for finding in findings
    }
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (item.severity, item.code, item.scope, item.message),
        )
    )
