"""Bounded step-load workflow, stage timing, monitoring, and cancellation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import threading
import time
from typing import Any

import httpx

from .contracts import MonitorSnapshot, SafetyThresholds
from .execution_limits import (
    DEFAULT_MONITOR_INTERVAL_SECONDS as _DEFAULT_MONITOR_INTERVAL_SECONDS,
    DEFAULT_SHUTDOWN_GRACE_SECONDS as _DEFAULT_SHUTDOWN_GRACE_SECONDS,
    DEFAULT_TELEMETRY_INTERVAL_SECONDS as _DEFAULT_TELEMETRY_INTERVAL_SECONDS,
    MIN_REQUEST_TIMEOUT_SECONDS as _MIN_REQUEST_TIMEOUT_SECONDS,
    MUTATION_FLAG as _MUTATION_FLAG,
    STEP_LOAD_FLAG as _STEP_LOAD_FLAG,
)
from .profile_workflow import run_profile
from .profiles import PM9_STEP_LOAD_PROFILES, ReliabilityProfile, StepLoadProfile
from .report_storage import _validated_report_directory, _write_report
from .reporting import (
    _OBSERVED_STAGE_STOP_REASONS,
    _allowlisted_runtime_safety_reason_codes,
    _allowlisted_stop_observation_phase,
    _allowlisted_stop_reason,
    _degradation_point,
    _mandatory_stage_telemetry_complete,
    _merge_monitor_snapshots,
    _ordered_unique,
    _report_workload_started,
    _step_report_entry,
)
from .request_contracts import (
    DEFAULT_READS,
    RequestSpec,
    _validated_base_url,
    _validated_request_path,
)
from .safety import _evaluate_safety

_STAGE_CONTROL_REQUEST_COUNT = 8
_STAGE_CONTROL_FIXED_ALLOWANCE_SECONDS = 1.0


StepRunner = Callable[[ReliabilityProfile], Mapping[str, Any]]
StepMonitor = Callable[
    [str, ReliabilityProfile],
    MonitorSnapshot | Mapping[str, Any],
]


@dataclass(frozen=True)
class _StageExecution:
    """Bounded result from invoking one stage runner in a daemon thread."""

    report: Mapping[str, Any] | None
    monitor_snapshot: MonitorSnapshot
    during_reason_codes: tuple[str, ...]
    failure_reason: str | None


def run_step_load(
    *,
    profile: StepLoadProfile = PM9_STEP_LOAD_PROFILES["capacity"],
    base_url: str = "http://127.0.0.1:8000",
    username: str | None = None,
    password: str | None = None,
    output_dir: Path | None = None,
    mutation_specs: tuple[RequestSpec, ...] = (),
    timeout_seconds: float = 10.0,
    thresholds: SafetyThresholds | None = None,
    runner: StepRunner | None = None,
    monitor: StepMonitor | None = None,
    shutdown_grace_seconds: float = _DEFAULT_SHUTDOWN_GRACE_SECONDS,
    telemetry_interval_seconds: float = _DEFAULT_TELEMETRY_INTERVAL_SECONDS,
    monitor_interval_seconds: float = _DEFAULT_MONITOR_INTERVAL_SECONDS,
    cancellation_event: threading.Event | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run an explicitly enabled, bounded step load and classify the evidence."""

    if os.getenv(_STEP_LOAD_FLAG) != "true":
        raise RuntimeError(f"PM9 step load requires {_STEP_LOAD_FLAG}=true on an approved host.")
    if mutation_specs and os.getenv(_MUTATION_FLAG) != "true":
        raise RuntimeError(
            f"Mutation scenarios require {_MUTATION_FLAG}=true and isolated records."
        )
    normalized_base = _validated_base_url(base_url)
    for spec in (*DEFAULT_READS, *mutation_specs):
        _validated_request_path(spec.path)
    report_dir = _validated_report_directory(output_dir)
    active_thresholds = thresholds or SafetyThresholds()
    if (
        isinstance(shutdown_grace_seconds, bool)
        or not isinstance(shutdown_grace_seconds, (int, float))
        or not math.isfinite(shutdown_grace_seconds)
        or not 0.05 <= shutdown_grace_seconds <= 10
    ):
        raise ValueError("Shutdown grace must be between 0.05 and 10 seconds.")
    if (
        isinstance(telemetry_interval_seconds, bool)
        or not isinstance(telemetry_interval_seconds, (int, float))
        or not math.isfinite(telemetry_interval_seconds)
        or not 0.05 <= telemetry_interval_seconds <= 30
    ):
        raise ValueError("Telemetry interval must be between 0.05 and 30 seconds.")
    if (
        isinstance(monitor_interval_seconds, bool)
        or not isinstance(monitor_interval_seconds, (int, float))
        or not math.isfinite(monitor_interval_seconds)
        or not 0.05 <= monitor_interval_seconds <= 5
    ):
        raise ValueError("Monitor interval must be between 0.05 and 5 seconds.")
    if runner is None and (not username or not password):
        raise RuntimeError("Username and password are required for the HTTP step-load runner.")

    evidence_mode = (
        "synthetic_test_double"
        if runner is not None
        else "synthetic_http_transport"
        if transport is not None
        else "live_http"
    )

    stages: list[dict[str, Any]] = []
    degradation: dict[str, Any] | None = None
    capacity_status = "completed_no_boundary_observed"
    capacity_stop_reasons: tuple[str, ...] = ()
    automatic_safety_stop = False
    for sequence, configured_stage in enumerate(profile.stages, start=1):
        stage_profile = profile.stage_profile(configured_stage)
        try:
            before = _call_monitor(monitor, "before", stage_profile)
        except Exception:  # noqa: BLE001 - report only an allow-listed failure code
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report={},
                before=MonitorSnapshot(),
                after=MonitorSnapshot(),
                reason_codes=("monitor_failure",),
                executed=False,
                workload_started=False,
                stop_phase="before_stage",
                outcome="harness_failure",
            )
            stages.append(entry)
            capacity_status = "harness_failure"
            capacity_stop_reasons = ("monitor_failure",)
            break

        preflight_reasons = _evaluate_safety(
            report={},
            before=before,
            after=before,
            thresholds=active_thresholds,
        )
        if cancellation_event is not None and cancellation_event.is_set():
            preflight_reasons = _ordered_unique((*preflight_reasons, "operator_cancelled"))
        if preflight_reasons:
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report={},
                before=before,
                after=before,
                reason_codes=preflight_reasons,
                executed=False,
                workload_started=False,
                stop_phase="before_stage",
                outcome="preflight_safety_stop",
            )
            stages.append(entry)
            capacity_status = "preflight_safety_stop"
            capacity_stop_reasons = preflight_reasons
            automatic_safety_stop = True
            break

        stage_cancellation = threading.Event()

        def invoke_stage() -> Mapping[str, Any]:
            if runner is not None:
                return runner(stage_profile)
            stage_report, _ = run_profile(
                base_url=normalized_base,
                username=str(username),
                password=str(password),
                profile=stage_profile,
                output_dir=report_dir,
                mutation_specs=mutation_specs,
                timeout_seconds=timeout_seconds,
                shutdown_grace_seconds=shutdown_grace_seconds,
                telemetry_interval_seconds=telemetry_interval_seconds,
                safety_thresholds=active_thresholds,
                cancellation_event=stage_cancellation,
                transport=transport,
            )
            return stage_report

        execution = _execute_stage(
            invoke=invoke_stage,
            stage_profile=stage_profile,
            before=before,
            monitor=monitor,
            thresholds=active_thresholds,
            stage_cancellation=stage_cancellation,
            external_cancellation=cancellation_event,
            shutdown_grace_seconds=shutdown_grace_seconds,
            monitor_interval_seconds=monitor_interval_seconds,
            stage_timeout_seconds=_stage_timeout_seconds(
                stage_profile=stage_profile,
                injected_runner=runner is not None,
                request_timeout_seconds=timeout_seconds,
                shutdown_grace_seconds=shutdown_grace_seconds,
            ),
        )
        if execution.failure_reason is not None or execution.report is None:
            failure_reasons = _ordered_unique(
                (
                    *execution.during_reason_codes,
                    execution.failure_reason or "runner_failure",
                )
            )
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report={},
                before=before,
                after=execution.monitor_snapshot,
                reason_codes=failure_reasons,
                executed=True,
                workload_started=False,
                stop_phase="during_stage",
                outcome="harness_failure",
            )
            stages.append(entry)
            capacity_status = "harness_failure"
            capacity_stop_reasons = failure_reasons
            break

        stage_result = execution.report
        workload_started = _report_workload_started(stage_result)
        after = execution.monitor_snapshot
        if not execution.during_reason_codes:
            try:
                after = _merge_monitor_snapshots(
                    after,
                    _call_monitor(monitor, "after", stage_profile),
                )
            except Exception:  # noqa: BLE001 - never serialize monitor exception text
                entry = _step_report_entry(
                    sequence=sequence,
                    stage_profile=stage_profile,
                    report=stage_result,
                    before=before,
                    after=after,
                    reason_codes=("monitor_failure",),
                    executed=True,
                    workload_started=workload_started,
                    stop_phase="after_stage",
                    outcome="harness_failure",
                )
                stages.append(entry)
                capacity_status = "harness_failure"
                capacity_stop_reasons = ("monitor_failure",)
                break

        if not _mandatory_stage_telemetry_complete(stage_result):
            reason_codes = ("mandatory_api_telemetry_missing",)
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report=stage_result,
                before=before,
                after=after,
                reason_codes=reason_codes,
                executed=True,
                workload_started=workload_started,
                stop_phase="during_stage" if workload_started else "before_stage",
                outcome="inconclusive",
            )
            stages.append(entry)
            capacity_status = "inconclusive"
            capacity_stop_reasons = reason_codes
            automatic_safety_stop = True
            break

        reason_codes = _evaluate_safety(
            report=stage_result,
            before=before,
            after=after,
            thresholds=active_thresholds,
        )
        runtime_reason_codes = _allowlisted_runtime_safety_reason_codes(
            stage_result.get("runtime_safety_reason_codes")
        )
        reason_codes = _ordered_unique(
            (
                *execution.during_reason_codes,
                *runtime_reason_codes,
                *reason_codes,
            )
        )
        reported_stop_reason = _allowlisted_stop_reason(stage_result.get("stop_reason"))
        if stage_result.get("stop_reason") is not None and reported_stop_reason is None:
            reported_stop_reason = "runner_failure"
        if reported_stop_reason in _OBSERVED_STAGE_STOP_REASONS:
            reason_codes = _ordered_unique((*reason_codes, reported_stop_reason))
        if reported_stop_reason in {"request_task_failure", "runner_failure"}:
            failure_reasons = _ordered_unique((*reason_codes, reported_stop_reason))
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report=stage_result,
                before=before,
                after=after,
                reason_codes=failure_reasons,
                executed=True,
                workload_started=workload_started,
                stop_phase="during_stage",
                outcome="harness_failure",
            )
            stages.append(entry)
            capacity_status = "harness_failure"
            capacity_stop_reasons = failure_reasons
            break

        safety_cancellation = "operator_cancelled" in reason_codes
        if (
            stage_result.get("target_request_count_reached") is False
            and not safety_cancellation
            and reported_stop_reason not in _OBSERVED_STAGE_STOP_REASONS
        ):
            reason_codes = _ordered_unique((*reason_codes, "target_rate_not_achieved"))

        if safety_cancellation:
            if not reason_codes:
                reason_codes = ("external_safety_stop",)
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report=stage_result,
                before=before,
                after=after,
                reason_codes=reason_codes,
                executed=True,
                workload_started=workload_started,
                stop_phase="during_stage",
                outcome="inconclusive",
            )
            stages.append(entry)
            capacity_status = "inconclusive"
            capacity_stop_reasons = reason_codes
            automatic_safety_stop = True
            break

        if reason_codes and not workload_started:
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report=stage_result,
                before=before,
                after=after,
                reason_codes=reason_codes,
                executed=True,
                workload_started=False,
                stop_phase="before_stage",
                outcome="preflight_safety_stop",
            )
            stages.append(entry)
            capacity_status = "preflight_safety_stop"
            capacity_stop_reasons = reason_codes
            automatic_safety_stop = True
            break

        degradation_stop_phase = (
            "during_stage"
            if execution.during_reason_codes
            or (
                (reported_stop_reason in _OBSERVED_STAGE_STOP_REASONS or bool(runtime_reason_codes))
                and _allowlisted_stop_observation_phase(stage_result.get("stop_observation_phase"))
                == "during_workload"
            )
            else "after_stage"
        )
        entry = _step_report_entry(
            sequence=sequence,
            stage_profile=stage_profile,
            report=stage_result,
            before=before,
            after=after,
            reason_codes=reason_codes,
            executed=True,
            workload_started=workload_started,
            stop_phase=degradation_stop_phase if reason_codes else None,
            outcome="observed_degradation" if reason_codes else "completed",
        )
        stages.append(entry)
        if reason_codes:
            degradation = _degradation_point(entry)
            capacity_status = "observed_degradation"
            capacity_stop_reasons = reason_codes
            automatic_safety_stop = True
            break

    completed_all_stages = (
        len(stages) == len(profile.stages) and capacity_status == "completed_no_boundary_observed"
    )
    host_capacity_evidence_eligible = (
        evidence_mode == "live_http"
        and capacity_status in {"completed_no_boundary_observed", "observed_degradation"}
        and all(
            stage["metrics"]["mandatory_api_telemetry_complete"] is True
            for stage in stages
            if stage["executed"]
        )
    )
    report = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "internal-pilot-host-rehearsal",
        "base_url": normalized_base,
        "profile": asdict(profile),
        "thresholds": asdict(active_thresholds),
        "test_assumption_notice": (
            "Profile and stop values are rehearsal assumptions, not measured demand or an SLA."
        ),
        "observed_boundary_only": True,
        "sla_claim": False,
        "production_readiness_claim": False,
        "evidence_mode": evidence_mode,
        "host_capacity_evidence_eligible": host_capacity_evidence_eligible,
        "capacity_evidence_status": capacity_status,
        "capacity_stop_reason_codes": list(capacity_stop_reasons),
        "result_interpretation": (
            "Observed boundary only for this tested host and profile; this is not an "
            "SLA, production-readiness result, or production capacity guarantee."
        ),
        "completed_all_stages": completed_all_stages,
        "automatic_safety_stop": automatic_safety_stop,
        "first_observed_degradation_point": degradation,
        "stages": stages,
    }
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = report_dir / f"pm9-step-load-{profile.name}-{timestamp}.json"
    _write_report(report_path, report)
    return report, report_path


def _execute_stage(
    *,
    invoke: Callable[[], Mapping[str, Any]],
    stage_profile: ReliabilityProfile,
    before: MonitorSnapshot,
    monitor: StepMonitor | None,
    thresholds: SafetyThresholds,
    stage_cancellation: threading.Event,
    external_cancellation: threading.Event | None,
    shutdown_grace_seconds: float,
    monitor_interval_seconds: float,
    stage_timeout_seconds: float,
) -> _StageExecution:
    """Invoke a stage without allowing a non-returning test double to hang the CLI."""

    completed = threading.Event()
    holder: dict[str, Any] = {}

    def target() -> None:
        try:
            holder["report"] = invoke()
        except BaseException:  # noqa: BLE001 - only a fixed failure code is retained
            holder["failed"] = True
        finally:
            completed.set()

    thread = threading.Thread(
        target=target,
        name=f"pm9-load-stage-{stage_profile.name}",
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + stage_timeout_seconds
    observed = before
    during_reasons: tuple[str, ...] = ()
    failure_reason: str | None = None

    while not completed.is_set():
        if external_cancellation is not None and external_cancellation.is_set():
            during_reasons = _ordered_unique((*during_reasons, "operator_cancelled"))
            stage_cancellation.set()
            if not completed.wait(shutdown_grace_seconds):
                failure_reason = "runner_deadline_exceeded"
            break

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            stage_cancellation.set()
            if not completed.wait(shutdown_grace_seconds):
                failure_reason = "runner_deadline_exceeded"
            break
        if completed.wait(min(monitor_interval_seconds, remaining)):
            break
        if monitor is None:
            continue
        try:
            current = _call_monitor(monitor, "during", stage_profile)
        except Exception:  # noqa: BLE001 - never retain external monitor text
            stage_cancellation.set()
            completed.wait(shutdown_grace_seconds)
            failure_reason = "monitor_failure"
            break
        observed = _merge_monitor_snapshots(observed, current)
        current_reasons = _evaluate_safety(
            report={},
            before=before,
            after=observed,
            thresholds=thresholds,
        )
        if current_reasons:
            during_reasons = current_reasons
            stage_cancellation.set()
            if not completed.wait(shutdown_grace_seconds):
                failure_reason = "runner_deadline_exceeded"
            break

    if failure_reason is None and holder.get("failed") is True:
        failure_reason = "runner_failure"
    report = holder.get("report")
    if failure_reason is None and not isinstance(report, Mapping):
        failure_reason = "runner_failure"
        report = None
    return _StageExecution(
        report=report,
        monitor_snapshot=observed,
        during_reason_codes=during_reasons,
        failure_reason=failure_reason,
    )


def _stage_timeout_seconds(
    *,
    stage_profile: ReliabilityProfile,
    injected_runner: bool,
    request_timeout_seconds: float,
    shutdown_grace_seconds: float,
) -> float:
    """Reserve bounded control-plane time without shortening the workload window."""

    if injected_runner:
        return float(stage_profile.duration_seconds)
    telemetry_timeout = min(
        request_timeout_seconds,
        max(_MIN_REQUEST_TIMEOUT_SECONDS, shutdown_grace_seconds / 3),
    )
    return (
        stage_profile.duration_seconds
        + request_timeout_seconds
        + (_STAGE_CONTROL_REQUEST_COUNT * telemetry_timeout)
        + _STAGE_CONTROL_FIXED_ALLOWANCE_SECONDS
    )


def _call_monitor(
    monitor: StepMonitor | None,
    phase: str,
    profile: ReliabilityProfile,
) -> MonitorSnapshot:
    if monitor is None:
        return MonitorSnapshot()
    value = monitor(phase, profile)
    if isinstance(value, MonitorSnapshot):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("Step monitor must return MonitorSnapshot or a mapping.")
    allowed = {
        field: value[field]
        for field in (
            "readiness",
            "worker_stale",
            "pending_outbox_count",
            "database_pool_timeout_count",
            "host_cpu_percent",
            "host_memory_percent",
            "operator_cancelled",
        )
        if field in value
    }
    return MonitorSnapshot(**allowed)
