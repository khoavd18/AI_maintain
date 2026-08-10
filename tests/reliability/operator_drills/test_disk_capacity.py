"""Behavior contract for injected PM9 disk-capacity drills."""

from dataclasses import FrozenInstanceError
from inspect import signature
import math

import pytest

from src.reliability import drills
from src.reliability.drills import (
    DISK_ACTION_ESCALATE_CRITICAL,
    DISK_ACTION_NONE,
    DISK_ACTION_RAISE_CRITICAL,
    DISK_ACTION_RAISE_WARNING,
    DISK_ACTION_RECOVER,
    DiskAlertCycle,
    DiskCapacity,
    DiskCapacityReport,
)


def test_disk_capacity_public_signatures_and_historical_bindings_are_stable() -> None:
    assert list(signature(DiskCapacity).parameters) == ["total_bytes", "free_bytes"]
    assert list(signature(DiskCapacityReport).parameters) == [
        "target_label",
        "free_percent",
        "used_percent",
        "severity",
        "runbook_action",
    ]
    assert list(signature(DiskAlertCycle).parameters) == [
        "target_label",
        "warning_free_percent",
        "critical_free_percent",
    ]
    assert list(signature(DiskAlertCycle.evaluate).parameters) == [
        "self",
        "capacity_provider",
    ]
    assert drills.DiskCapacity is DiskCapacity
    assert drills.DiskCapacityReport is DiskCapacityReport
    assert drills.DiskAlertCycle is DiskAlertCycle


@pytest.mark.parametrize(
    ("total_bytes", "free_bytes", "message"),
    [
        (True, 0, "Total bytes must be a positive integer."),
        (0, 0, "Total bytes must be a positive integer."),
        (1.5, 0, "Total bytes must be a positive integer."),
        (10, True, "Free bytes must be between zero and total bytes."),
        (10, -1, "Free bytes must be between zero and total bytes."),
        (10, 11, "Free bytes must be between zero and total bytes."),
    ],
)
def test_disk_capacity_rejects_invalid_integer_boundaries(
    total_bytes: object,
    free_bytes: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        DiskCapacity(total_bytes=total_bytes, free_bytes=free_bytes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("warning", "critical", "message"),
    [
        (True, 10, "Disk thresholds must be finite percentages."),
        (math.inf, 10, "Disk thresholds must be finite percentages."),
        (20, math.nan, "Disk thresholds must be finite percentages."),
        (10, 10, "Disk critical threshold must be below the warning threshold within 0-100."),
        (101, 10, "Disk critical threshold must be below the warning threshold within 0-100."),
        (10, -1, "Disk critical threshold must be below the warning threshold within 0-100."),
    ],
)
def test_disk_cycle_rejects_invalid_thresholds(
    warning: object,
    critical: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        DiskAlertCycle(
            target_label="pilot_data",
            warning_free_percent=warning,  # type: ignore[arg-type]
            critical_free_percent=critical,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("label", ["", "Pilot", "pilot data", "-pilot", "a" * 65])
def test_disk_cycle_preserves_strict_opaque_label_contract(label: str) -> None:
    with pytest.raises(
        ValueError,
        match="^Target label must be an opaque lowercase identifier[.]$",
    ):
        DiskAlertCycle(
            target_label=label,
            warning_free_percent=20,
            critical_free_percent=10,
        )

    with pytest.raises(TypeError):
        DiskAlertCycle(  # type: ignore[arg-type]
            target_label=None,
            warning_free_percent=20,
            critical_free_percent=10,
        )


def test_disk_cycle_transition_order_and_report_serialization_are_exact() -> None:
    cycle = DiskAlertCycle(
        target_label="pilot_data",
        warning_free_percent=20,
        critical_free_percent=10,
    )
    capacities = iter((150, 140, 90, 80, 300, 100, 250))

    reports = [
        cycle.evaluate(lambda: DiskCapacity(total_bytes=1_000, free_bytes=next(capacities)))
        for _ in range(7)
    ]

    assert [report.runbook_action for report in reports] == [
        DISK_ACTION_RAISE_WARNING,
        DISK_ACTION_NONE,
        DISK_ACTION_ESCALATE_CRITICAL,
        DISK_ACTION_NONE,
        DISK_ACTION_RECOVER,
        DISK_ACTION_RAISE_CRITICAL,
        DISK_ACTION_RECOVER,
    ]
    assert reports[0].as_dict() == {
        "target_label": "pilot_data",
        "free_percent": 15.0,
        "used_percent": 85.0,
        "severity": "warning",
        "runbook_action": DISK_ACTION_RAISE_WARNING,
    }


def test_disk_cycle_calls_provider_once_and_propagates_provider_failures() -> None:
    cycle = DiskAlertCycle(
        target_label="pilot_data",
        warning_free_percent=20,
        critical_free_percent=10,
    )
    calls = 0

    def provider() -> DiskCapacity:
        nonlocal calls
        calls += 1
        return DiskCapacity(total_bytes=3, free_bytes=1)

    assert cycle.evaluate(provider).severity == "healthy"
    assert calls == 1

    failure = RuntimeError("provider failed")

    def failing_provider() -> DiskCapacity:
        raise failure

    with pytest.raises(RuntimeError) as raised:
        cycle.evaluate(failing_provider)
    assert raised.value is failure


def test_disk_cycle_rejects_unexpected_provider_type_without_state_transition() -> None:
    cycle = DiskAlertCycle(
        target_label="pilot_data",
        warning_free_percent=20,
        critical_free_percent=10,
    )
    with pytest.raises(TypeError, match="^Capacity provider must return DiskCapacity[.]$"):
        cycle.evaluate(lambda: {"total_bytes": 100, "free_bytes": 5})  # type: ignore[arg-type]

    assert cycle.evaluate(lambda: DiskCapacity(total_bytes=100, free_bytes=5)).runbook_action == (
        DISK_ACTION_RAISE_CRITICAL
    )


def test_disk_capacity_reports_are_frozen_value_objects() -> None:
    capacity = DiskCapacity(total_bytes=100, free_bytes=25)
    report = DiskCapacityReport(
        target_label="pilot_data",
        free_percent=25.0,
        used_percent=75.0,
        severity="healthy",
        runbook_action=DISK_ACTION_NONE,
    )

    with pytest.raises(FrozenInstanceError):
        capacity.free_bytes = 10  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        report.severity = "critical"  # type: ignore[misc]
