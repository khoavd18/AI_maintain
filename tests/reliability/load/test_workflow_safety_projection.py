"""Load tests grouped by stateful workflow dimension."""

from __future__ import annotations

from ._workflow_scenarios import (
    MonitorSnapshot,
    SafetyThresholds,
    _evaluate_safety,
    _healthy_stage_report,
    pytest,
)


@pytest.mark.parametrize(
    ("report", "before", "after", "expected_reason"),
    [
        (
            {**_healthy_stage_report(), "unexpected_error_rate": 0.021},
            MonitorSnapshot(),
            MonitorSnapshot(),
            "unexpected_error_rate",
        ),
        (
            {**_healthy_stage_report(), "timeouts": 2},
            MonitorSnapshot(),
            MonitorSnapshot(),
            "repeated_timeouts",
        ),
        (
            _healthy_stage_report(),
            MonitorSnapshot(readiness=False),
            MonitorSnapshot(readiness=False),
            "readiness_unhealthy",
        ),
        (
            _healthy_stage_report(),
            MonitorSnapshot(worker_stale=False),
            MonitorSnapshot(worker_stale=True),
            "worker_stale",
        ),
        (
            _healthy_stage_report(),
            MonitorSnapshot(pending_outbox_count=2),
            MonitorSnapshot(pending_outbox_count=3),
            "unrecovered_outbox_growth",
        ),
        (
            _healthy_stage_report(),
            MonitorSnapshot(host_cpu_percent=50.0),
            MonitorSnapshot(host_cpu_percent=90.1),
            "host_cpu_threshold",
        ),
        (
            _healthy_stage_report(),
            MonitorSnapshot(host_memory_percent=50.0),
            MonitorSnapshot(host_memory_percent=90.1),
            "host_memory_threshold",
        ),
        (
            _healthy_stage_report(),
            MonitorSnapshot(database_pool_timeout_count=3),
            MonitorSnapshot(database_pool_timeout_count=5),
            "repeated_timeouts",
        ),
    ],
)
def test_automatic_stop_thresholds(
    report: dict[str, object],
    before: MonitorSnapshot,
    after: MonitorSnapshot,
    expected_reason: str,
) -> None:
    reasons = _evaluate_safety(
        report=report,
        before=before,
        after=after,
        thresholds=SafetyThresholds(),
    )
    assert expected_reason in reasons
