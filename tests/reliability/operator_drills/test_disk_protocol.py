"""Operator-drill tests grouped by atomic protocol."""

from __future__ import annotations

from ._protocol_scenarios import (
    DISK_ACTION_ESCALATE_CRITICAL,
    DISK_ACTION_NONE,
    DISK_ACTION_RAISE_WARNING,
    DISK_ACTION_RECOVER,
    DiskAlertCycle,
    DiskCapacity,
    json,
    pytest,
)


def test_disk_drill_uses_injected_capacity_and_deduplicates_cycle() -> None:
    observations = iter(
        (
            DiskCapacity(total_bytes=1_000, free_bytes=150),
            DiskCapacity(total_bytes=1_000, free_bytes=140),
            DiskCapacity(total_bytes=1_000, free_bytes=90),
            DiskCapacity(total_bytes=1_000, free_bytes=80),
            DiskCapacity(total_bytes=1_000, free_bytes=300),
            DiskCapacity(total_bytes=1_000, free_bytes=150),
        )
    )
    provider_calls = 0

    def controlled_provider() -> DiskCapacity:
        nonlocal provider_calls
        provider_calls += 1
        return next(observations)

    cycle = DiskAlertCycle(
        target_label="pilot_storage",
        warning_free_percent=20,
        critical_free_percent=10,
    )
    reports = [cycle.evaluate(controlled_provider) for _ in range(6)]

    assert [report.severity for report in reports] == [
        "warning",
        "warning",
        "critical",
        "critical",
        "healthy",
        "warning",
    ]
    assert [report.runbook_action for report in reports] == [
        DISK_ACTION_RAISE_WARNING,
        DISK_ACTION_NONE,
        DISK_ACTION_ESCALATE_CRITICAL,
        DISK_ACTION_NONE,
        DISK_ACTION_RECOVER,
        DISK_ACTION_RAISE_WARNING,
    ]
    assert provider_calls == 6
    assert reports[0].as_dict() == {
        "target_label": "pilot_storage",
        "free_percent": 15.0,
        "used_percent": 85.0,
        "severity": "warning",
        "runbook_action": DISK_ACTION_RAISE_WARNING,
    }
    assert all("\\" not in json.dumps(report.as_dict()) for report in reports)
    assert all(":/" not in json.dumps(report.as_dict()) for report in reports)


def test_disk_drill_classifies_direct_critical_without_real_disk_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_disk_usage(*_args, **_kwargs):
        raise AssertionError("real disk usage must not be queried")

    monkeypatch.setattr("shutil.disk_usage", forbidden_disk_usage)
    cycle = DiskAlertCycle(
        target_label="backup_volume",
        warning_free_percent=25,
        critical_free_percent=10,
    )
    report = cycle.evaluate(lambda: DiskCapacity(total_bytes=2_000, free_bytes=100))
    assert report.severity == "critical"
    assert report.free_percent == 5.0
    assert report.runbook_action != DISK_ACTION_NONE

    with pytest.raises(ValueError, match="opaque"):
        DiskAlertCycle(
            target_label=r"C:\private\backup",
            warning_free_percent=25,
            critical_free_percent=10,
        )
