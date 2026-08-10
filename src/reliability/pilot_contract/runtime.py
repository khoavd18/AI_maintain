"""Ordered facade for deployment runtime policy validation."""

from __future__ import annotations

from typing import Any

from .runtime_policy.recovery import _validate_recovery_policy
from .runtime_policy.retry import _validate_retry_and_dead_letter
from .runtime_policy.settings import _validate_operating_settings
from .schemas import Finding


def _validate_runtime_settings(
    document: dict[str, Any],
    findings: list[Finding],
) -> None:
    """Validate runtime policy dimensions in their historical finding order."""

    _validate_operating_settings(document, findings)
    _validate_retry_and_dead_letter(document, findings)
    _validate_recovery_policy(document, findings)
