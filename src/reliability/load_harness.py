"""Historical import and CLI facade for bounded load-rehearsal workflows."""

# ruff: noqa: F401 - compatibility re-exports intentionally remain module attributes

from src.reliability.load.cli import main
from src.reliability.load.contracts import MonitorSnapshot, SafetyThresholds, Sample
from src.reliability.load.http_sampling import _consume_request_futures, _login, _sample_request
from src.reliability.load.metrics import (
    _counter_growth,
    _database_pool_metrics,
    _finite_number,
    _maximum_supplied,
    _nonnegative_int,
    _outbox_count_from_report,
    _outbox_metric_count,
    _pending_outbox_from_report,
    _percentile,
    _unexpected_error_rate,
)
from src.reliability.load.profiles import (
    PM9_STEP_LOAD_PROFILES,
    PROFILES,
    ReliabilityProfile,
    StepLoadProfile,
)
from src.reliability.load.profile_reporting import _summarize
from src.reliability.load.profile_workflow import run_profile
from src.reliability.load.report_storage import _validated_report_directory, _write_report
from src.reliability.load.reporting import (
    _allowlisted_outbox_summary,
    _allowlisted_runtime_safety_reason_codes,
    _allowlisted_step_metrics,
    _allowlisted_stop_observation_phase,
    _allowlisted_stop_reason,
    _degradation_point,
    _mandatory_stage_telemetry_complete,
    _merge_monitor_snapshots,
    _ordered_unique,
    _report_workload_started,
    _step_report_entry,
    _valid_outbox_summary,
)
from src.reliability.load.request_contracts import (
    DEFAULT_READS,
    RequestSpec,
    _load_mutations,
    _select_spec,
    _validated_base_url,
    _validated_request_path,
)
from src.reliability.load.safety import (
    _evaluate_safety,
    _runtime_performance_safety_reasons,
    _runtime_telemetry_safety_reasons,
)
from src.reliability.load.step_workflow import StepMonitor, StepRunner, run_step_load
from src.reliability.load.telemetry import (
    _ApiTelemetry,
    _collect_api_telemetry,
    _execution_status_counts,
    _outbox_metrics,
    _readiness_status,
    _record_telemetry_checks,
    _response_json,
    _safe_json,
    _telemetry_response,
    _valid_operations_metrics_payload,
    _worker_ready_status,
    _worker_stale_status,
)

__all__ = [
    "DEFAULT_READS",
    "MonitorSnapshot",
    "PM9_STEP_LOAD_PROFILES",
    "PROFILES",
    "RequestSpec",
    "ReliabilityProfile",
    "SafetyThresholds",
    "Sample",
    "StepMonitor",
    "StepLoadProfile",
    "StepRunner",
    "main",
    "run_profile",
    "run_step_load",
]


if __name__ == "__main__":
    main()
