"""Behavior contract for secret-free load report projection."""

from inspect import signature

from src.reliability import load_harness
from src.reliability.load import metrics as load_metrics
from src.reliability.load import reporting as load_reporting
from src.reliability.load_harness import (
    MonitorSnapshot,
    _allowlisted_outbox_summary,
    _allowlisted_runtime_safety_reason_codes,
    _allowlisted_step_metrics,
    _allowlisted_stop_observation_phase,
    _allowlisted_stop_reason,
    _database_pool_metrics,
    _degradation_point,
    _mandatory_stage_telemetry_complete,
    _merge_monitor_snapshots,
    _ordered_unique,
    _report_workload_started,
    _step_report_entry,
    _valid_outbox_summary,
)
from src.reliability.profiles import ReliabilityProfile


def _profile() -> ReliabilityProfile:
    return ReliabilityProfile(
        name="characterized",
        concurrent_users=2,
        requests_per_second=3.5,
        duration_seconds=4,
        mutation_share=0.0,
        analytics_trigger_frequency_seconds=None,
    )


def _outbox(*, pending: object = 0, dead: object = 0, oldest: object = None) -> dict[str, object]:
    return {
        "pending_outbox_count": pending,
        "dead_letter_outbox_count": dead,
        "oldest_pending_outbox_age_seconds": oldest,
        "secret": "must-not-survive",
    }


def test_load_reporting_signatures_and_historical_bindings_are_stable() -> None:
    expected = {
        "_report_workload_started": ["report"],
        "_mandatory_stage_telemetry_complete": ["report"],
        "_valid_outbox_summary": ["value"],
        "_allowlisted_outbox_summary": ["value"],
        "_allowlisted_stop_reason": ["value"],
        "_allowlisted_runtime_safety_reason_codes": ["value"],
        "_allowlisted_stop_observation_phase": ["value"],
        "_ordered_unique": ["values"],
        "_merge_monitor_snapshots": ["previous", "current"],
        "_degradation_point": ["entry"],
        "_allowlisted_step_metrics": ["report"],
        "_database_pool_metrics": ["value"],
    }
    for name, parameters in expected.items():
        value = globals()[name]
        assert list(signature(value).parameters) == parameters
        assert getattr(load_harness, name) is value
    assert list(signature(_step_report_entry).parameters) == [
        "sequence",
        "stage_profile",
        "report",
        "before",
        "after",
        "reason_codes",
        "executed",
        "workload_started",
        "stop_phase",
        "outcome",
    ]
    assert load_harness._step_report_entry is _step_report_entry


def test_load_reporting_owner_is_the_historical_facade_binding() -> None:
    for name in (
        "_report_workload_started",
        "_mandatory_stage_telemetry_complete",
        "_valid_outbox_summary",
        "_allowlisted_outbox_summary",
        "_allowlisted_stop_reason",
        "_allowlisted_runtime_safety_reason_codes",
        "_allowlisted_stop_observation_phase",
        "_ordered_unique",
        "_merge_monitor_snapshots",
        "_step_report_entry",
        "_degradation_point",
        "_allowlisted_step_metrics",
    ):
        assert getattr(load_harness, name) is getattr(load_reporting, name)
    assert load_harness._database_pool_metrics is load_metrics._database_pool_metrics


def test_workload_and_mandatory_telemetry_classification_is_fail_closed() -> None:
    assert _report_workload_started({"workload_started": False, "total_requests": 1}) is False
    assert _report_workload_started({"workload_started": True, "total_requests": 0}) is True
    assert _report_workload_started({"workload_started": "yes", "total_requests": 1}) is True
    assert _report_workload_started({"total_requests": True}) is False

    complete = {
        "mandatory_api_telemetry_complete": True,
        "database_pool_before": {"size": 5, "checked_out": 1, "overflow": 0},
        "database_pool_after": {"database_pool": {"size": 5, "checked_out": 2, "overflow": 0}},
        "outbox_before": _outbox(),
        "outbox_after": _outbox(pending=1, oldest=2),
    }
    assert _mandatory_stage_telemetry_complete(complete) is True
    for key in complete:
        malformed = dict(complete)
        malformed[key] = None
        assert _mandatory_stage_telemetry_complete(malformed) is False


def test_outbox_and_database_pool_projections_allow_only_valid_metrics() -> None:
    value = _outbox(pending=2, dead=1, oldest=3)
    assert _valid_outbox_summary(value) is True
    assert _allowlisted_outbox_summary(value) == {
        "pending_outbox_count": 2,
        "dead_letter_outbox_count": 1,
        "oldest_pending_outbox_age_seconds": 3,
    }
    assert _valid_outbox_summary(_outbox(pending=True)) is False
    assert _allowlisted_outbox_summary({"pending_outbox_count": 0}) is None
    assert _database_pool_metrics(
        {"database_pool": {"size": 5, "checked_out": 2, "overflow": 1, "secret": "x"}}
    ) == {"size": 5, "checked_out": 2, "overflow": 1}
    assert _database_pool_metrics({"size": 5, "checked_out": True, "overflow": 0}) is None


def test_stop_reason_phase_and_runtime_reason_allow_lists_preserve_order() -> None:
    assert _allowlisted_stop_reason("repeated_timeouts") == "repeated_timeouts"
    assert _allowlisted_stop_reason("unknown") is None
    assert _allowlisted_stop_reason(1) is None
    assert _allowlisted_stop_observation_phase("during_workload") == "during_workload"
    assert _allowlisted_stop_observation_phase("after") is None
    assert _allowlisted_runtime_safety_reason_codes(
        [
            "repeated_timeouts",
            "secret-reason",
            "repeated_timeouts",
            "dead_letter_growth",
            1,
        ]
    ) == ("repeated_timeouts", "dead_letter_growth")
    assert _allowlisted_runtime_safety_reason_codes("repeated_timeouts") == ()
    assert _ordered_unique(("b", "a", "b", "c", "a")) == ("b", "a", "c")


def test_monitor_merge_preserves_fail_closed_precedence_and_inputs() -> None:
    previous = MonitorSnapshot(
        readiness=True,
        worker_stale=False,
        pending_outbox_count=1,
        database_pool_timeout_count=2,
        host_cpu_percent=50,
        host_memory_percent=60,
    )
    current = MonitorSnapshot(
        readiness=False,
        worker_stale=True,
        pending_outbox_count=3,
        host_cpu_percent=40,
        host_memory_percent=70,
        operator_cancelled=True,
    )

    assert _merge_monitor_snapshots(previous, current) == MonitorSnapshot(
        readiness=False,
        worker_stale=True,
        pending_outbox_count=3,
        database_pool_timeout_count=2,
        host_cpu_percent=50,
        host_memory_percent=70,
        operator_cancelled=True,
    )
    assert previous.readiness is True
    assert current.readiness is False


def test_allowlisted_step_metrics_elides_unknown_and_secret_fields_without_mutation() -> None:
    report: dict[str, object] = {
        "total_requests": 4,
        "throughput_requests_per_second": 2.5,
        "latency_ms": {"p50": 1.0, "p95": 2.0, "p99": 3.0, "raw": ["secret"]},
        "unexpected_failures": 1,
        "database_pool_before": {"size": 5, "checked_out": 1, "overflow": 0, "dsn": "secret"},
        "outbox_before": _outbox(pending=1),
        "stop_reason": "repeated_timeouts",
        "runtime_safety_reason_codes": ["repeated_timeouts", "secret"],
        "stop_observation_phase": "during_workload",
        "authorization": "Bearer secret",
    }
    original = dict(report)

    projected = _allowlisted_step_metrics(report)

    assert projected["total_requests"] == 4
    assert projected["latency_ms"] == {"p50": 1.0, "p95": 2.0, "p99": 3.0}
    assert projected["database_pool_before"] == {"size": 5, "checked_out": 1, "overflow": 0}
    assert projected["outbox_before"] == {
        "pending_outbox_count": 1,
        "dead_letter_outbox_count": 0,
        "oldest_pending_outbox_age_seconds": None,
    }
    assert projected["runtime_safety_reason_codes"] == ["repeated_timeouts"]
    assert "authorization" not in projected
    assert "secret" not in repr(projected)
    assert report == original


def test_step_report_and_degradation_projection_have_exact_order_and_fields() -> None:
    entry = _step_report_entry(
        sequence=2,
        stage_profile=_profile(),
        report={"total_requests": 4, "timeouts": 2},
        before=MonitorSnapshot(database_pool_timeout_count=1, pending_outbox_count=0),
        after=MonitorSnapshot(
            readiness=False,
            database_pool_timeout_count=3,
            pending_outbox_count=2,
        ),
        reason_codes=("repeated_timeouts",),
        executed=True,
        workload_started=True,
        stop_phase="stage_2",
        outcome="observed_degradation",
    )

    assert list(entry) == [
        "sequence",
        "target_requests_per_second",
        "concurrent_users",
        "duration_seconds",
        "executed",
        "workload_started",
        "outcome",
        "metrics",
        "monitor",
        "safety_threshold_crossed",
        "safety_reason_codes",
        "stop_phase",
    ]
    assert entry["monitor"] == {
        "readiness_false_observations": 1,
        "worker_stale_observations": 0,
        "pending_outbox_before": 0,
        "pending_outbox_after": 2,
        "database_pool_timeout_growth": 2,
        "host_cpu_percent_max": None,
        "host_memory_percent_max": None,
    }
    assert _degradation_point(entry) == {
        "target_requests_per_second": 3.5,
        "concurrent_users": 2,
        "reason_codes": ["repeated_timeouts"],
        "stop_phase": "stage_2",
    }
