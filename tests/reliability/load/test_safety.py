"""Behavior contract for pure load observation and safety policy."""

from dataclasses import FrozenInstanceError
from inspect import signature
import math

import pytest

from src.reliability import load_harness
from src.reliability.load import contracts as load_contracts
from src.reliability.load import metrics as load_metrics
from src.reliability.load import safety as load_safety
from src.reliability.load_harness import (
    MonitorSnapshot,
    SafetyThresholds,
    Sample,
    _counter_growth,
    _evaluate_safety,
    _finite_number,
    _maximum_supplied,
    _nonnegative_int,
    _outbox_count_from_report,
    _outbox_metric_count,
    _pending_outbox_from_report,
    _percentile,
    _runtime_performance_safety_reasons,
    _runtime_telemetry_safety_reasons,
    _unexpected_error_rate,
)


def test_load_safety_signatures_and_historical_bindings_are_stable() -> None:
    assert list(signature(Sample).parameters) == [
        "name",
        "status_code",
        "elapsed_ms",
        "outcome",
        "idempotent_replay",
    ]
    assert list(signature(SafetyThresholds).parameters) == [
        "max_unexpected_error_rate",
        "max_p95_latency_ms",
        "repeated_timeout_limit",
        "repeated_readiness_failure_limit",
        "max_worker_stale_observations",
        "max_unrecovered_outbox_growth",
        "max_host_cpu_percent",
        "max_host_memory_percent",
    ]
    assert list(signature(MonitorSnapshot).parameters) == [
        "readiness",
        "worker_stale",
        "pending_outbox_count",
        "database_pool_timeout_count",
        "host_cpu_percent",
        "host_memory_percent",
        "operator_cancelled",
    ]
    assert list(signature(_runtime_performance_safety_reasons).parameters) == [
        "samples",
        "thresholds",
    ]
    assert list(signature(_runtime_telemetry_safety_reasons).parameters) == [
        "baseline_metrics",
        "current_metrics",
        "thresholds",
        "prior_outbox_breach_streak",
    ]
    assert list(signature(_evaluate_safety).parameters) == [
        "report",
        "before",
        "after",
        "thresholds",
    ]
    for name, value in (
        ("Sample", Sample),
        ("SafetyThresholds", SafetyThresholds),
        ("MonitorSnapshot", MonitorSnapshot),
        ("_runtime_performance_safety_reasons", _runtime_performance_safety_reasons),
        ("_runtime_telemetry_safety_reasons", _runtime_telemetry_safety_reasons),
        ("_evaluate_safety", _evaluate_safety),
    ):
        assert getattr(load_harness, name) is value


def test_load_safety_capability_owners_are_the_historical_facade_bindings() -> None:
    for name in ("Sample", "SafetyThresholds", "MonitorSnapshot"):
        assert getattr(load_harness, name) is getattr(load_contracts, name)
    for name in (
        "_unexpected_error_rate",
        "_counter_growth",
        "_pending_outbox_from_report",
        "_outbox_count_from_report",
        "_outbox_metric_count",
        "_maximum_supplied",
        "_finite_number",
        "_nonnegative_int",
        "_percentile",
    ):
        assert getattr(load_harness, name) is getattr(load_metrics, name)
    for name in (
        "_runtime_performance_safety_reasons",
        "_runtime_telemetry_safety_reasons",
        "_evaluate_safety",
    ):
        assert getattr(load_harness, name) is getattr(load_safety, name)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"max_unexpected_error_rate": True},
            "Unexpected-error threshold must be between 0 and 1.",
        ),
        (
            {"max_unexpected_error_rate": math.nan},
            "Unexpected-error threshold must be between 0 and 1.",
        ),
        ({"max_p95_latency_ms": 0}, "The p95 latency ceiling must be positive."),
        ({"repeated_timeout_limit": True}, "Timeout stop limit must be positive."),
        ({"repeated_readiness_failure_limit": 0}, "Readiness-failure stop limit must be positive."),
        ({"max_worker_stale_observations": -1}, "Worker-stale allowance cannot be negative."),
        ({"max_unrecovered_outbox_growth": -1}, "Outbox-growth allowance cannot be negative."),
        ({"max_host_cpu_percent": math.inf}, "Host CPU threshold must be between 0 and 100."),
        ({"max_host_memory_percent": 101}, "Host memory threshold must be between 0 and 100."),
    ],
)
def test_safety_thresholds_preserve_exact_validation_boundaries(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        SafetyThresholds(**changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"readiness": 1}, "Readiness observation must be boolean."),
        ({"worker_stale": "false"}, "Worker Stale observation must be boolean."),
        ({"operator_cancelled": 0}, "Operator-cancelled observation must be boolean."),
        ({"pending_outbox_count": True}, "Pending Outbox count cannot be negative."),
        ({"database_pool_timeout_count": -1}, "Database Pool Timeout count cannot be negative."),
        ({"host_cpu_percent": math.nan}, "Host CPU observation must be between 0 and 100."),
        ({"host_memory_percent": 101}, "Host memory observation must be between 0 and 100."),
    ],
)
def test_monitor_snapshots_preserve_allow_list_validation(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        MonitorSnapshot(**changes)  # type: ignore[arg-type]


def test_load_safety_value_objects_are_frozen() -> None:
    sample = Sample("read", 200, 1.0, "success")
    thresholds = SafetyThresholds()
    snapshot = MonitorSnapshot()
    with pytest.raises(FrozenInstanceError):
        sample.outcome = "timeout"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        thresholds.repeated_timeout_limit = 3  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        snapshot.readiness = False  # type: ignore[misc]


@pytest.mark.parametrize(
    ("value", "finite", "nonnegative"),
    [
        (True, None, None),
        (-1, -1.0, None),
        (0, 0.0, 0),
        (1.5, 1.5, None),
        (math.nan, None, None),
        (math.inf, None, None),
        ("1", None, None),
    ],
)
def test_load_metric_normalization_is_fail_closed(
    value: object,
    finite: float | None,
    nonnegative: int | None,
) -> None:
    assert _finite_number(value) == finite
    assert _nonnegative_int(value) == nonnegative


def test_percentile_counter_and_maximum_helpers_preserve_exact_boundaries() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert _percentile([], 95) is None
    assert _percentile(values, 0) == 1.0
    assert _percentile(values, 50) == 2.0
    assert _percentile(values, 95) == 4.0
    assert _percentile(values, 101) == 4.0
    assert _counter_growth(None, 2) == 0
    assert _counter_growth(3, 2) == 0
    assert _counter_growth(2, 5) == 3
    assert _maximum_supplied(None, None) is None
    assert _maximum_supplied(None, 10.0, 5.0) == 10.0


def test_outbox_metric_projection_rejects_malformed_values_without_mutation() -> None:
    report: dict[str, object] = {
        "outbox_before": {"pending_outbox_count": 2, "dead_letter_outbox_count": True},
        "outbox_after": "invalid",
    }
    original = {
        "outbox_before": {"pending_outbox_count": 2, "dead_letter_outbox_count": True},
        "outbox_after": "invalid",
    }

    assert _pending_outbox_from_report(report, "outbox_before") == 2
    assert _outbox_count_from_report(report, "outbox_before", "dead_letter_outbox_count") is None
    assert _outbox_count_from_report(report, "outbox_after", "pending_outbox_count") is None
    assert _outbox_metric_count(None, "pending_outbox_count") is None
    assert report == original


def test_unexpected_error_rate_prefers_clamped_explicit_value_then_derives() -> None:
    assert _unexpected_error_rate({"unexpected_error_rate": 2.0, "total_requests": 10}) == 1.0
    assert _unexpected_error_rate({"unexpected_error_rate": -1.0, "total_requests": 10}) == 0.0
    assert _unexpected_error_rate({"total_requests": 0, "timeouts": 9}) == 0.0
    assert (
        _unexpected_error_rate(
            {
                "total_requests": 4,
                "unexpected_failures": 1,
                "timeouts": 1,
                "connection_failures": True,
                "database_connection_failures": -1,
            }
        )
        == 0.5
    )


def test_runtime_performance_reasons_preserve_order_and_input_values() -> None:
    samples = [
        Sample("read", None, 3_000.0, "timeout"),
        Sample("read", 500, 2_500.0, "unexpected_failure"),
    ]
    original = list(samples)
    reasons = _runtime_performance_safety_reasons(
        samples=samples,
        thresholds=SafetyThresholds(
            max_unexpected_error_rate=0.1,
            max_p95_latency_ms=2_000,
            repeated_timeout_limit=1,
        ),
    )

    assert reasons == (
        "unexpected_error_rate",
        "p95_latency_ceiling",
        "repeated_timeouts",
    )
    assert samples == original
    assert (
        _runtime_performance_safety_reasons(
            samples=[],
            thresholds=SafetyThresholds(),
        )
        == ()
    )


def test_runtime_telemetry_reasons_preserve_streak_and_reason_order() -> None:
    thresholds = SafetyThresholds(max_unrecovered_outbox_growth=0)
    baseline = {"pending_outbox_count": 1, "dead_letter_outbox_count": 0}
    current = {"pending_outbox_count": 2, "dead_letter_outbox_count": 1}

    first_reasons, first_streak = _runtime_telemetry_safety_reasons(
        baseline_metrics=baseline,
        current_metrics=current,
        thresholds=thresholds,
        prior_outbox_breach_streak=0,
    )
    second_reasons, second_streak = _runtime_telemetry_safety_reasons(
        baseline_metrics=baseline,
        current_metrics=current,
        thresholds=thresholds,
        prior_outbox_breach_streak=first_streak,
    )

    assert first_reasons == ("dead_letter_growth",)
    assert first_streak == 1
    assert second_reasons == ("dead_letter_growth", "unrecovered_outbox_growth")
    assert second_streak == 2
    assert _runtime_telemetry_safety_reasons(
        baseline_metrics=None,
        current_metrics=current,
        thresholds=thresholds,
        prior_outbox_breach_streak=8,
    ) == ((), 0)


def test_evaluate_safety_preserves_complete_reason_order_without_mutation() -> None:
    report: dict[str, object] = {
        "unexpected_error_rate": 0.5,
        "latency_ms": {"p95": 3_000.0},
        "timeouts": 2,
        "readiness_false_count": 1,
        "worker_stale_observations": 1,
        "outbox_before": {"pending_outbox_count": 0, "dead_letter_outbox_count": 0},
        "outbox_after": {"pending_outbox_count": 2, "dead_letter_outbox_count": 1},
    }
    original = {
        "unexpected_error_rate": 0.5,
        "latency_ms": {"p95": 3_000.0},
        "timeouts": 2,
        "readiness_false_count": 1,
        "worker_stale_observations": 1,
        "outbox_before": {"pending_outbox_count": 0, "dead_letter_outbox_count": 0},
        "outbox_after": {"pending_outbox_count": 2, "dead_letter_outbox_count": 1},
    }
    before = MonitorSnapshot(host_cpu_percent=91.0)
    after = MonitorSnapshot(host_memory_percent=92.0, operator_cancelled=True)

    assert _evaluate_safety(
        report=report,
        before=before,
        after=after,
        thresholds=SafetyThresholds(),
    ) == (
        "unexpected_error_rate",
        "p95_latency_ceiling",
        "repeated_timeouts",
        "readiness_unhealthy",
        "worker_stale",
        "dead_letter_growth",
        "unrecovered_outbox_growth",
        "host_cpu_threshold",
        "host_memory_threshold",
        "operator_cancelled",
    )
    assert report == original
