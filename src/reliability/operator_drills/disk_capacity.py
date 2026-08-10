"""Injected disk-capacity classification and per-cycle alert deduplication."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
from typing import Literal

from src.reliability.operator_drills.contracts import _validate_opaque_label


DiskSeverity = Literal["healthy", "warning", "critical"]

DISK_ACTION_NONE = "none"
DISK_ACTION_RAISE_WARNING = "raise_warning_and_follow_disk_capacity_runbook"
DISK_ACTION_RAISE_CRITICAL = "raise_critical_and_follow_disk_capacity_runbook"
DISK_ACTION_ESCALATE_CRITICAL = "escalate_critical_via_disk_capacity_runbook"
DISK_ACTION_RECOVER = "record_recovery_after_capacity_is_verified"


@dataclass(frozen=True)
class DiskCapacity:
    """A capacity observation supplied by a controlled provider."""

    total_bytes: int
    free_bytes: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.total_bytes, bool)
            or not isinstance(self.total_bytes, int)
            or self.total_bytes <= 0
        ):
            raise ValueError("Total bytes must be a positive integer.")
        if (
            isinstance(self.free_bytes, bool)
            or not isinstance(self.free_bytes, int)
            or not 0 <= self.free_bytes <= self.total_bytes
        ):
            raise ValueError("Free bytes must be between zero and total bytes.")


@dataclass(frozen=True)
class DiskCapacityReport:
    """Path-free result from one injected disk-capacity observation."""

    target_label: str
    free_percent: float
    used_percent: float
    severity: DiskSeverity
    runbook_action: str

    def as_dict(self) -> dict[str, str | float]:
        return {
            "target_label": self.target_label,
            "free_percent": self.free_percent,
            "used_percent": self.used_percent,
            "severity": self.severity,
            "runbook_action": self.runbook_action,
        }


class DiskAlertCycle:
    """Deduplicate disk warning, escalation, and recovery actions per cycle."""

    def __init__(
        self,
        *,
        target_label: str,
        warning_free_percent: float,
        critical_free_percent: float,
    ) -> None:
        _validate_opaque_label(target_label)
        _validate_disk_thresholds(
            warning_free_percent=warning_free_percent,
            critical_free_percent=critical_free_percent,
        )
        self.target_label = target_label
        self.warning_free_percent = float(warning_free_percent)
        self.critical_free_percent = float(critical_free_percent)
        self._alert_active = False
        self._critical_announced = False

    def evaluate(
        self,
        capacity_provider: Callable[[], DiskCapacity],
    ) -> DiskCapacityReport:
        """Evaluate one supplied observation without querying the real filesystem."""

        capacity = capacity_provider()
        if not isinstance(capacity, DiskCapacity):
            raise TypeError("Capacity provider must return DiskCapacity.")
        free_percent = capacity.free_bytes * 100.0 / capacity.total_bytes
        severity = self._classify(free_percent)
        action = self._transition(severity)
        rounded_free = round(free_percent, 2)
        return DiskCapacityReport(
            target_label=self.target_label,
            free_percent=rounded_free,
            used_percent=round(100.0 - rounded_free, 2),
            severity=severity,
            runbook_action=action,
        )

    def _classify(self, free_percent: float) -> DiskSeverity:
        if free_percent <= self.critical_free_percent:
            return "critical"
        if free_percent <= self.warning_free_percent:
            return "warning"
        return "healthy"

    def _transition(self, severity: DiskSeverity) -> str:
        if severity == "healthy":
            if not self._alert_active:
                return DISK_ACTION_NONE
            self._alert_active = False
            self._critical_announced = False
            return DISK_ACTION_RECOVER
        if not self._alert_active:
            self._alert_active = True
            if severity == "critical":
                self._critical_announced = True
                return DISK_ACTION_RAISE_CRITICAL
            return DISK_ACTION_RAISE_WARNING
        if severity == "critical" and not self._critical_announced:
            self._critical_announced = True
            return DISK_ACTION_ESCALATE_CRITICAL
        return DISK_ACTION_NONE


def _validate_disk_thresholds(
    *,
    warning_free_percent: float,
    critical_free_percent: float,
) -> None:
    values = (warning_free_percent, critical_free_percent)
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in values
    ):
        raise ValueError("Disk thresholds must be finite percentages.")
    if not 0 <= critical_free_percent < warning_free_percent <= 100:
        raise ValueError(
            "Disk critical threshold must be below the warning threshold within 0-100."
        )
