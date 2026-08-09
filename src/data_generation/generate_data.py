"""Generate deterministic synthetic data for the focused maintenance MVP."""

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.config.value_mappings import (
    ASSET_TYPE_CODE_TO_VI,
    ASSET_TYPE_VI_TO_CODE,
    CRITICALITY_CODE_TO_VI,
    DOCUMENT_TYPE_CODE_TO_VI,
    FAILURE_TYPE_CODE_TO_VI,
    MAINTENANCE_RESULT_CODE_TO_VI,
    MAINTENANCE_TYPE_CODE_TO_VI,
    PRIORITY_CODE_TO_VI,
    STATUS_CODE_TO_VI,
)

DEFAULT_SEED = 42
DEFAULT_ASSET_COUNT = 27
DEFAULT_DAYS = 120
DEFAULT_FREQUENCY = "hourly"
DATA_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
CONTROLLED_ANOMALY_DAYS = 14

DATASET_FILENAMES = {
    "assets": "assets.csv",
    "sensor_readings": "sensor_readings.csv",
    "maintenance_tickets": "maintenance_tickets.csv",
    "maintenance_logs": "maintenance_logs.csv",
    "documents": "documents.csv",
}
LEGACY_DATASET_FILENAMES = ("risk_scores.csv",)

ASSET_TYPE_COUNTS = {
    "hvac": 10,
    "pump": 9,
    "generator": 8,
}

ASSET_CONFIG = {
    "hvac": {
        "prefix": "HVAC",
        "label": ASSET_TYPE_CODE_TO_VI["hvac"],
        "maintenance_interval_days": 90,
        "criticality_codes": ["medium", "high", "critical"],
    },
    "pump": {
        "prefix": "PUMP",
        "label": ASSET_TYPE_CODE_TO_VI["pump"],
        "maintenance_interval_days": 60,
        "criticality_codes": ["medium", "high", "critical"],
    },
    "generator": {
        "prefix": "GENERATOR",
        "label": ASSET_TYPE_CODE_TO_VI["generator"],
        "maintenance_interval_days": 120,
        "criticality_codes": ["high", "critical"],
    },
}

SUPPORTED_ASSET_TYPES = frozenset(
    ASSET_TYPE_CODE_TO_VI[asset_type] for asset_type in ASSET_CONFIG
)
ASSET_STATUS_VALUES = frozenset(
    {STATUS_CODE_TO_VI["normal"], STATUS_CODE_TO_VI["warning"]}
)
ASSET_CRITICALITY_VALUES = frozenset(
    {
        CRITICALITY_CODE_TO_VI["medium"],
        CRITICALITY_CODE_TO_VI["high"],
        CRITICALITY_CODE_TO_VI["critical"],
    }
)
TICKET_STATUS_VALUES = frozenset(
    {
        STATUS_CODE_TO_VI["open"],
        STATUS_CODE_TO_VI["in_progress"],
        STATUS_CODE_TO_VI["resolved"],
    }
)
MAINTENANCE_RESULT_VALUES = frozenset(MAINTENANCE_RESULT_CODE_TO_VI.values())

LOCATIONS = [
    "Phòng máy khu Bắc",
    "Phòng máy khu Nam",
    "Sân thượng phía Đông",
    "Sân thượng phía Tây",
    "Tầng hầm kỹ thuật",
    "Khối đế thương mại",
]

TECHNICIAN_IDS = [f"TECH_{index:03d}" for index in range(1, 7)]


@dataclass(frozen=True)
class ControlledScenarioPlan:
    """Assets selected for reproducible anomalies and maintenance scenarios."""

    hvac_energy: frozenset[str]
    pump_vibration: frozenset[str]
    generator_runtime: frozenset[str]
    overdue_assets: frozenset[str]
    recurring_issue_assets: frozenset[str]

    @property
    def warning_assets(self) -> frozenset[str]:
        """Return assets with a controlled condition requiring attention."""

        return frozenset(
            self.hvac_energy
            | self.pump_vibration
            | self.generator_runtime
            | self.overdue_assets
        )


def generate_dataset(
    asset_count: int = DEFAULT_ASSET_COUNT,
    days: int = DEFAULT_DAYS,
    frequency: str = DEFAULT_FREQUENCY,
    seed: int = DEFAULT_SEED,
) -> dict[str, pd.DataFrame]:
    """Generate the focused CSV-first maintenance dataset."""

    if asset_count <= 0:
        raise ValueError("asset_count must be positive")
    if days <= 0:
        raise ValueError("days must be positive")
    if frequency not in {"hourly", "daily"}:
        raise ValueError("frequency must be 'hourly' or 'daily'")

    rng = np.random.default_rng(seed)
    assets = _generate_assets(asset_count=asset_count, rng=rng)
    scenario_plan = _build_scenario_plan(assets)
    assets = _apply_asset_status(assets, scenario_plan)
    sensor_readings = _generate_sensor_readings(
        assets=assets,
        scenario_plan=scenario_plan,
        days=days,
        frequency=frequency,
        rng=rng,
    )
    maintenance_tickets = _generate_maintenance_tickets(
        assets=assets,
        scenario_plan=scenario_plan,
        days=days,
        rng=rng,
    )
    maintenance_logs = _generate_maintenance_logs(
        assets=assets,
        maintenance_tickets=maintenance_tickets,
        scenario_plan=scenario_plan,
        days=days,
        rng=rng,
    )
    assets = _finalize_asset_maintenance_dates(
        assets=assets,
        maintenance_logs=maintenance_logs,
    )
    documents = _generate_documents()

    return {
        "assets": assets,
        "sensor_readings": sensor_readings,
        "maintenance_tickets": maintenance_tickets,
        "maintenance_logs": maintenance_logs,
        "documents": documents,
    }


def save_dataset(dataset: dict[str, pd.DataFrame], output_dir: Path) -> None:
    """Save generated datasets and remove obsolete generated risk snapshots."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for dataset_name, filename in DATASET_FILENAMES.items():
        dataset[dataset_name].to_csv(output_dir / filename, index=False)

    for filename in LEGACY_DATASET_FILENAMES:
        legacy_path = output_dir / filename
        if legacy_path.exists():
            legacy_path.unlink()


def _asset_type_sequence(asset_count: int) -> list[str]:
    asset_types = list(ASSET_TYPE_COUNTS)
    if asset_count < len(asset_types):
        return asset_types[:asset_count]

    weights = np.array(list(ASSET_TYPE_COUNTS.values()), dtype=float)
    raw_counts = weights / weights.sum() * asset_count
    counts = np.floor(raw_counts).astype(int)
    counts[counts == 0] = 1

    while int(counts.sum()) > asset_count:
        index = int(np.argmax(counts))
        if counts[index] > 1:
            counts[index] -= 1
    remainder = asset_count - int(counts.sum())
    for index in np.argsort(raw_counts - np.floor(raw_counts))[::-1]:
        if remainder <= 0:
            break
        counts[index] += 1
        remainder -= 1

    sequence: list[str] = []
    for asset_type, count in zip(asset_types, counts, strict=True):
        sequence.extend([asset_type] * int(count))
    return sequence


def _generate_assets(asset_count: int, rng: np.random.Generator) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    type_counters = {asset_type: 0 for asset_type in ASSET_CONFIG}

    for asset_type in _asset_type_sequence(asset_count):
        type_counters[asset_type] += 1
        sequence_number = type_counters[asset_type]
        config = ASSET_CONFIG[asset_type]
        interval_days = int(config["maintenance_interval_days"])
        asset_id = f"{config['prefix']}_{sequence_number:03d}"

        installation_date = DATA_START.date() - timedelta(
            days=int(rng.integers(365 * 2, 365 * 10))
        )
        if asset_type == "generator" and sequence_number <= 2:
            days_before_start = interval_days + 20 + sequence_number * 10
        else:
            days_before_start = int(rng.integers(10, min(interval_days, 45)))
        last_maintenance_date = DATA_START.date() - timedelta(days=days_before_start)
        next_maintenance_date = last_maintenance_date + timedelta(days=interval_days)
        criticality_code = str(rng.choice(config["criticality_codes"]))

        rows.append(
            {
                "asset_id": asset_id,
                "asset_name": f"{config['label']} {sequence_number:03d}",
                "asset_type": ASSET_TYPE_CODE_TO_VI[asset_type],
                "location": str(rng.choice(LOCATIONS)),
                "criticality": CRITICALITY_CODE_TO_VI[criticality_code],
                "status": STATUS_CODE_TO_VI["normal"],
                "installation_date": installation_date.isoformat(),
                "last_maintenance_date": last_maintenance_date.isoformat(),
                "maintenance_interval_days": interval_days,
                "next_maintenance_date": next_maintenance_date.isoformat(),
            }
        )

    return pd.DataFrame(rows)


def _build_scenario_plan(assets: pd.DataFrame) -> ControlledScenarioPlan:
    def select(asset_type_code: str, limit: int) -> frozenset[str]:
        label = ASSET_TYPE_CODE_TO_VI[asset_type_code]
        values = assets.loc[assets["asset_type"] == label, "asset_id"].head(limit)
        return frozenset(values.astype(str))

    hvac_assets = select("hvac", 2)
    pump_assets = select("pump", 2)
    generator_assets = select("generator", 2)
    return ControlledScenarioPlan(
        hvac_energy=hvac_assets,
        pump_vibration=pump_assets,
        generator_runtime=generator_assets,
        overdue_assets=generator_assets,
        recurring_issue_assets=frozenset(hvac_assets | pump_assets),
    )


def _apply_asset_status(
    assets: pd.DataFrame,
    scenario_plan: ControlledScenarioPlan,
) -> pd.DataFrame:
    updated = assets.copy()
    updated.loc[
        updated["asset_id"].isin(scenario_plan.warning_assets),
        "status",
    ] = STATUS_CODE_TO_VI["warning"]
    return updated


def _generate_sensor_readings(
    assets: pd.DataFrame,
    scenario_plan: ControlledScenarioPlan,
    days: int,
    frequency: str,
    rng: np.random.Generator,
) -> pd.DataFrame:
    periods = days * 24 if frequency == "hourly" else days
    pandas_frequency = "h" if frequency == "hourly" else "D"
    hours_per_period = 1 if frequency == "hourly" else 24
    timestamps = pd.date_range(DATA_START, periods=periods, freq=pandas_frequency)
    rows: list[dict[str, object]] = []
    reading_number = 1

    for asset in assets.itertuples(index=False):
        asset_type = ASSET_TYPE_VI_TO_CODE[str(asset.asset_type)]
        for timestamp in timestamps:
            values = _simulate_reading(
                asset_id=str(asset.asset_id),
                asset_type=asset_type,
                timestamp=timestamp.to_pydatetime(),
                scenario_plan=scenario_plan,
                days=days,
                hours_per_period=hours_per_period,
                rng=rng,
            )
            rows.append(
                {
                    "reading_id": f"READ-{reading_number:08d}",
                    "asset_id": asset.asset_id,
                    "timestamp": timestamp.isoformat(),
                    **values,
                }
            )
            reading_number += 1

    return pd.DataFrame(rows)


def _simulate_reading(
    asset_id: str,
    asset_type: str,
    timestamp: datetime,
    scenario_plan: ControlledScenarioPlan,
    days: int,
    hours_per_period: int,
    rng: np.random.Generator,
) -> dict[str, object]:
    weekday = timestamp.weekday()
    business_hours = weekday < 5 and 7 <= timestamp.hour <= 19
    anomaly_start = DATA_START + timedelta(days=max(days - CONTROLLED_ANOMALY_DAYS, 0))
    is_daily = hours_per_period == 24

    if asset_type == "hvac":
        runtime_fraction = 0.55 if is_daily else (0.78 if business_hours else 0.28)
        runtime_fraction = _clamp(float(rng.normal(runtime_fraction, 0.06)))
        energy = (2.2 + 7.5 * runtime_fraction + rng.normal(0.0, 0.35)) * hours_per_period
        temperature = 23.0 + 4.0 * runtime_fraction + rng.normal(0.0, 0.6)
        vibration = max(0.02, 0.16 + rng.normal(0.0, 0.025))
        if asset_id in scenario_plan.hvac_energy and timestamp >= anomaly_start:
            energy *= float(rng.uniform(1.55, 1.75))
            temperature += float(rng.uniform(3.2, 4.5))
            runtime_fraction = _clamp(runtime_fraction * 1.2)
    elif asset_type == "pump":
        runtime_fraction = 0.48 if is_daily else (0.68 if business_hours else 0.34)
        runtime_fraction = _clamp(float(rng.normal(runtime_fraction, 0.08)))
        energy = (1.5 + 5.0 * runtime_fraction + rng.normal(0.0, 0.25)) * hours_per_period
        temperature = 32.0 + 14.0 * runtime_fraction + rng.normal(0.0, 0.9)
        vibration = max(0.05, 0.32 + 0.25 * runtime_fraction + rng.normal(0.0, 0.04))
        if asset_id in scenario_plan.pump_vibration and timestamp >= anomaly_start:
            vibration *= float(rng.uniform(2.3, 3.0))
            temperature += float(rng.uniform(2.5, 4.0))
            runtime_fraction = _clamp(runtime_fraction * 1.15)
    else:
        weekly_test = weekday == 0 and (is_daily or timestamp.hour == 10)
        runtime_fraction = 0.04 if is_daily else (0.85 if weekly_test else 0.02)
        runtime_fraction = _clamp(float(rng.normal(runtime_fraction, 0.02)))
        energy = (0.15 + 14.0 * runtime_fraction + rng.normal(0.0, 0.2)) * hours_per_period
        temperature = 27.0 + 32.0 * runtime_fraction + rng.normal(0.0, 1.0)
        vibration = max(0.02, 0.10 + 0.38 * runtime_fraction + rng.normal(0.0, 0.03))
        if asset_id in scenario_plan.generator_runtime and timestamp >= anomaly_start:
            runtime_fraction = max(runtime_fraction, float(rng.uniform(0.28, 0.38)))
            energy = (0.15 + 14.0 * runtime_fraction) * hours_per_period
            temperature += float(rng.uniform(4.0, 6.0))
            vibration *= float(rng.uniform(1.5, 1.9))

    runtime_hours = runtime_fraction * hours_per_period
    return {
        "energy_kwh": round(max(0.0, float(energy)), 3),
        "runtime_hours": round(max(0.0, min(hours_per_period, runtime_hours)), 3),
        "temperature": round(max(0.0, float(temperature)), 2),
        "vibration": round(max(0.0, float(vibration)), 4),
        "status": STATUS_CODE_TO_VI["normal"],
    }


def _generate_maintenance_tickets(
    assets: pd.DataFrame,
    scenario_plan: ControlledScenarioPlan,
    days: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for asset in assets.itertuples(index=False):
        asset_id = str(asset.asset_id)
        asset_type = ASSET_TYPE_VI_TO_CODE[str(asset.asset_type)]
        if asset_id in scenario_plan.overdue_assets:
            continue
        ticket_count = int(rng.integers(0, 3))
        for _ in range(ticket_count):
            failure_category = str(rng.choice(_failure_categories(asset_type)))
            status_code = str(rng.choice(["resolved", "resolved", "open", "in_progress"]))
            _append_ticket(
                rows=rows,
                asset_id=asset_id,
                asset_type=asset_type,
                failure_category=failure_category,
                status_code=status_code,
                created_day=int(rng.integers(0, max(1, days - 6))),
                days=days,
                rng=rng,
            )

    recurring_specs = [
        ("cooling_issue", ["resolved", "resolved", "in_progress"]),
        ("vibration_issue", ["resolved", "open", "resolved"]),
    ]
    for asset_id in sorted(scenario_plan.recurring_issue_assets):
        asset_type = "hvac" if asset_id.startswith("HVAC_") else "pump"
        category, statuses = recurring_specs[0 if asset_type == "hvac" else 1]
        for offset, status_code in zip([45, 30, 15], statuses, strict=True):
            _append_ticket(
                rows=rows,
                asset_id=asset_id,
                asset_type=asset_type,
                failure_category=category,
                status_code=status_code,
                created_day=max(0, days - offset),
                days=days,
                rng=rng,
            )

    for asset_id in sorted(scenario_plan.overdue_assets):
        for offset, status_code in [(20, "in_progress"), (5, "open")]:
            _append_ticket(
                rows=rows,
                asset_id=asset_id,
                asset_type="generator",
                failure_category="electrical_issue",
                status_code=status_code,
                created_day=max(0, days - offset),
                days=days,
                rng=rng,
            )

    frame = pd.DataFrame(rows).sort_values(["created_at", "asset_id"]).reset_index(drop=True)
    frame["ticket_id"] = [f"TCK-{index:06d}" for index in range(1, len(frame) + 1)]
    return frame[
        [
            "ticket_id",
            "asset_id",
            "issue_description",
            "priority",
            "status",
            "failure_category",
            "created_at",
            "resolved_at",
            "technician_id",
        ]
    ]


def _append_ticket(
    rows: list[dict[str, object]],
    asset_id: str,
    asset_type: str,
    failure_category: str,
    status_code: str,
    created_day: int,
    days: int,
    rng: np.random.Generator,
) -> None:
    latest_created_day = max(0, days - 1)
    created_day = min(created_day, latest_created_day)
    created_at = DATA_START + timedelta(
        days=created_day,
        hours=int(rng.integers(7, 19)),
        minutes=int(rng.integers(0, 60)),
    )
    resolved_at = ""
    if status_code == "resolved":
        resolution_days = int(rng.integers(1, 5))
        observation_end = DATA_START + timedelta(days=days) - timedelta(minutes=1)
        resolved = min(created_at + timedelta(days=resolution_days), observation_end)
        resolved_at = resolved.isoformat()

    rows.append(
        {
            "asset_id": asset_id,
            "issue_description": _issue_description(asset_type, failure_category),
            "priority": PRIORITY_CODE_TO_VI[_ticket_priority(failure_category)],
            "status": STATUS_CODE_TO_VI[status_code],
            "failure_category": FAILURE_TYPE_CODE_TO_VI[failure_category],
            "created_at": created_at.isoformat(),
            "resolved_at": resolved_at,
            "technician_id": str(rng.choice(TECHNICIAN_IDS)),
        }
    )


def _failure_categories(asset_type: str) -> list[str]:
    return {
        "hvac": ["cooling_issue", "sensor_issue", "runtime_issue", "no_failure"],
        "pump": ["vibration_issue", "sensor_issue", "runtime_issue", "no_failure"],
        "generator": ["electrical_issue", "sensor_issue", "runtime_issue", "no_failure"],
    }[asset_type]


def _ticket_priority(failure_category: str) -> str:
    if failure_category == "electrical_issue":
        return "critical"
    if failure_category in {"cooling_issue", "vibration_issue", "runtime_issue"}:
        return "high"
    if failure_category == "sensor_issue":
        return "medium"
    return "low"


def _issue_description(asset_type: str, failure_category: str) -> str:
    descriptions = {
        "cooling_issue": "Hiệu suất làm lạnh giảm và nhiệt độ khu vực không đạt yêu cầu.",
        "vibration_issue": "Độ rung tăng so với mức nền khi máy bơm đang vận hành.",
        "electrical_issue": "Máy phát ghi nhận cảnh báo điện trong lần kiểm tra gần nhất.",
        "runtime_issue": "Thời gian vận hành lệch khỏi lịch vận hành thông thường.",
        "sensor_issue": "Dữ liệu cảm biến chập chờn và cần được kiểm tra hiệu chuẩn.",
        "no_failure": "Yêu cầu kiểm tra xác nhận thiết bị theo kế hoạch vận hành.",
    }
    return descriptions.get(failure_category, f"Cần kiểm tra thiết bị {asset_type}.")


def _generate_maintenance_logs(
    assets: pd.DataFrame,
    maintenance_tickets: pd.DataFrame,
    scenario_plan: ControlledScenarioPlan,
    days: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    observation_end = DATA_START.date() + timedelta(days=days - 1)

    for asset in assets.itertuples(index=False):
        asset_id = str(asset.asset_id)
        interval_days = int(asset.maintenance_interval_days)
        baseline_date = date.fromisoformat(str(asset.last_maintenance_date))
        rows.append(
            _maintenance_log_row(
                asset_id=asset_id,
                ticket_id="",
                maintenance_date=baseline_date,
                interval_days=interval_days,
                maintenance_type_code="preventive",
                maintenance_result_code="resolved",
                technician_id=str(rng.choice(TECHNICIAN_IDS)),
                rng=rng,
            )
        )

        if asset_id not in scenario_plan.overdue_assets:
            scheduled_date = baseline_date + timedelta(days=interval_days)
            while scheduled_date <= observation_end:
                rows.append(
                    _maintenance_log_row(
                        asset_id=asset_id,
                        ticket_id="",
                        maintenance_date=scheduled_date,
                        interval_days=interval_days,
                        maintenance_type_code="preventive",
                        maintenance_result_code="resolved",
                        technician_id=str(rng.choice(TECHNICIAN_IDS)),
                        rng=rng,
                    )
                )
                scheduled_date += timedelta(days=interval_days)

    asset_intervals = assets.set_index("asset_id")["maintenance_interval_days"].astype(int)
    corrective_index = 0
    vendor_log_added = False
    for ticket in maintenance_tickets.itertuples(index=False):
        asset_id = str(ticket.asset_id)
        if asset_id in scenario_plan.overdue_assets:
            continue

        if ticket.status == STATUS_CODE_TO_VI["resolved"]:
            maintenance_date = pd.Timestamp(ticket.resolved_at).date()
            result_code = ["resolved", "partially_resolved", "monitoring_required"][
                corrective_index % 3
            ]
            corrective_index += 1
        elif ticket.status == STATUS_CODE_TO_VI["in_progress"] and not vendor_log_added:
            maintenance_date = pd.Timestamp(ticket.created_at).date() + timedelta(days=1)
            if maintenance_date > observation_end:
                continue
            result_code = "vendor_required"
            vendor_log_added = True
        else:
            continue

        rows.append(
            _maintenance_log_row(
                asset_id=asset_id,
                ticket_id=str(ticket.ticket_id),
                maintenance_date=maintenance_date,
                interval_days=int(asset_intervals.loc[asset_id]),
                maintenance_type_code="corrective",
                maintenance_result_code=result_code,
                technician_id=str(ticket.technician_id),
                rng=rng,
            )
        )

    frame = pd.DataFrame(rows).sort_values(["maintenance_date", "asset_id"]).reset_index(drop=True)
    frame["log_id"] = [f"LOG-{index:06d}" for index in range(1, len(frame) + 1)]
    return frame[
        [
            "log_id",
            "ticket_id",
            "asset_id",
            "maintenance_date",
            "maintenance_type",
            "technician_id",
            "inspection_result",
            "actions_taken",
            "parts_replaced",
            "technician_note",
            "maintenance_result",
            "follow_up_required",
            "next_maintenance_date",
        ]
    ]


def _maintenance_log_row(
    asset_id: str,
    ticket_id: str,
    maintenance_date: date,
    interval_days: int,
    maintenance_type_code: str,
    maintenance_result_code: str,
    technician_id: str,
    rng: np.random.Generator,
) -> dict[str, object]:
    asset_type = _asset_type_from_id(asset_id)
    actions = {
        "hvac": "Kiểm tra lưới lọc, dàn coil, dây curoa và cảm biến nhiệt độ.",
        "pump": "Kiểm tra bạc đạn, độ đồng tâm, bu lông bệ máy và độ rung.",
        "generator": "Kiểm tra ắc quy, dầu nhớt, nước làm mát và chạy thử máy phát.",
    }
    parts = {
        "hvac": ["", "lưới lọc", "cảm biến nhiệt"],
        "pump": ["", "bạc đạn", "bộ phớt"],
        "generator": ["", "lọc dầu", "ắc quy"],
    }
    inspection_results = {
        "resolved": "Thiết bị đạt yêu cầu kiểm tra và có thể tiếp tục vận hành.",
        "partially_resolved": "Thiết bị vận hành được nhưng còn hạng mục cần xử lý tiếp.",
        "monitoring_required": "Chưa phát hiện sự cố nghiêm trọng; cần theo dõi xu hướng.",
        "vendor_required": "Cần hỗ trợ chuyên môn bổ sung trước khi kết luận.",
    }
    follow_up_required = maintenance_result_code != "resolved"

    return {
        "ticket_id": ticket_id,
        "asset_id": asset_id,
        "maintenance_date": maintenance_date.isoformat(),
        "maintenance_type": MAINTENANCE_TYPE_CODE_TO_VI[maintenance_type_code],
        "technician_id": technician_id,
        "inspection_result": inspection_results[maintenance_result_code],
        "actions_taken": actions[asset_type],
        "parts_replaced": str(rng.choice(parts[asset_type])),
        "technician_note": (
            "Đã ghi nhận thông số sau kiểm tra và cập nhật kế hoạch theo dõi."
            if follow_up_required
            else "Đã hoàn tất kiểm tra và bàn giao thiết bị về trạng thái vận hành."
        ),
        "maintenance_result": MAINTENANCE_RESULT_CODE_TO_VI[maintenance_result_code],
        "follow_up_required": follow_up_required,
        "next_maintenance_date": (
            maintenance_date + timedelta(days=interval_days)
        ).isoformat(),
    }


def _finalize_asset_maintenance_dates(
    assets: pd.DataFrame,
    maintenance_logs: pd.DataFrame,
) -> pd.DataFrame:
    updated = assets.copy()
    latest_logs = (
        maintenance_logs.assign(
            _maintenance_date=pd.to_datetime(maintenance_logs["maintenance_date"])
        )
        .sort_values(["asset_id", "_maintenance_date", "log_id"])
        .groupby("asset_id", as_index=False)
        .tail(1)
        .set_index("asset_id")
    )

    for row_index, asset in updated.iterrows():
        latest_log = latest_logs.loc[str(asset["asset_id"])]
        updated.at[row_index, "last_maintenance_date"] = latest_log["maintenance_date"]
        updated.at[row_index, "next_maintenance_date"] = latest_log["next_maintenance_date"]
    return updated


def _asset_type_from_id(asset_id: str) -> str:
    if asset_id.startswith("HVAC_"):
        return "hvac"
    if asset_id.startswith("PUMP_"):
        return "pump"
    return "generator"


def _generate_documents() -> pd.DataFrame:
    templates = [
        (
            "DOC-001",
            "Checklist kiểm tra định kỳ máy lạnh",
            "checklist",
            "hvac",
            "Tài liệu minh họa nội bộ - máy lạnh",
            """Phạm vi: Checklist synthetic minh họa cho kiểm tra định kỳ máy lạnh; không thay thế hướng dẫn của nhà sản xuất.
An toàn: Kỹ thuật viên phải đánh giá hiện trường, mang PPE phù hợp, cô lập nguồn và áp dụng lockout/tagout theo quy định của tòa nhà trước khi mở tủ hoặc tiếp cận bộ phận chuyển động. Không vô hiệu hóa liên động hay thiết bị bảo vệ.
Các bước kiểm tra:
1. Xác nhận mã thiết bị, tình trạng vận hành và lịch bảo trì gần nhất.
2. Quan sát rò rỉ, tiếng ồn, mùi bất thường và cảnh báo trên bộ điều khiển mà không tháo bộ phận đang mang điện.
3. Kiểm tra tình trạng lưới lọc, dàn trao đổi nhiệt và đường thoát nước ngưng; chỉ vệ sinh theo hướng dẫn được phê duyệt.
4. Ghi nhận nhiệt độ vào/ra, dòng điện và thời gian vận hành để so sánh với giới hạn của nhà sản xuất.
5. Xác nhận tấm che, cảm biến và thiết bị bảo vệ đã ở trạng thái an toàn trước khi bàn giao.
Khi nào cần hỗ trợ chuyên môn: Dừng kiểm tra và liên hệ kỹ thuật trưởng hoặc đơn vị chuyên môn khi có mùi khét, rò môi chất lạnh, dây dẫn hư hỏng, cảnh báo bảo vệ lặp lại hoặc thông số vượt giới hạn nhà sản xuất.
Giới hạn: Không tự nạp môi chất, sửa mạch điện hoặc bỏ qua cảnh báo chỉ dựa trên checklist minh họa này.""",
        ),
        (
            "DOC-002",
            "Hướng dẫn kiểm tra máy lạnh không làm mát",
            "troubleshooting_guide",
            "hvac",
            "Tài liệu minh họa nội bộ - máy lạnh",
            """Phạm vi: Hướng dẫn synthetic minh họa để thu thập bằng chứng ban đầu khi máy lạnh không làm mát; không phải quy trình chẩn đoán hoặc sửa chữa chính thức.
An toàn: Không mở tủ điện, chạm mạch môi chất hoặc tiếp cận quạt khi chưa cô lập nguồn và thực hiện lockout/tagout. Tuân thủ PPE, quy trình an toàn tòa nhà và hướng dẫn nhà sản xuất.
Các bước kiểm tra:
1. Xác nhận yêu cầu nhiệt độ, chế độ vận hành, lịch chạy và mã cảnh báo hiển thị.
2. Kiểm tra bằng quan sát xem luồng gió có bị cản, lưới lọc có bẩn hoặc cửa gió có đóng hay không.
3. Ghi nhận nhiệt độ gió vào/ra, nhiệt độ phòng, runtime và điện năng tại cùng thời điểm.
4. Quan sát nước ngưng, dấu hiệu đóng băng, rò rỉ hoặc tiếng ồn bất thường mà không tháo đường ống.
5. Đối chiếu kết quả với manual và checklist được phê duyệt; ghi lại ảnh, cảnh báo và thông số để chuyển cấp.
Khi nào cần hỗ trợ chuyên môn: Liên hệ kỹ thuật trưởng hoặc đơn vị HVAC có chứng chỉ khi nghi ngờ rò môi chất, đóng băng kéo dài, bảo vệ điện tác động, máy nén không hoạt động hoặc cần đo/hiệu chỉnh chuyên dụng.
Giới hạn: Không nạp môi chất, đấu tắt cảm biến, cưỡng bức contactor hoặc khởi động lặp lại thiết bị đang báo bảo vệ.""",
        ),
        (
            "DOC-003",
            "Checklist kiểm tra định kỳ máy bơm nước",
            "checklist",
            "pump",
            "Tài liệu minh họa nội bộ - máy bơm",
            """Phạm vi: Checklist synthetic minh họa cho kiểm tra định kỳ máy bơm nước; không thay thế manual, quy trình lockout/tagout hoặc hướng dẫn vận hành hệ thống.
An toàn: Xác nhận áp suất hệ thống, cô lập điện và năng lượng thủy lực theo quy định trước khi tiếp cận khớp nối hoặc bộ phận chuyển động. Không tháo đường ống đang có áp và không bỏ qua công tắc bảo vệ.
Các bước kiểm tra:
1. Xác nhận mã bơm, trạng thái van theo quy trình vận hành và lịch bảo trì gần nhất.
2. Quan sát rò rỉ tại phớt, mặt bích và đường ống; ghi nhận nhưng không siết chỉnh khi hệ thống còn áp.
3. Ghi nhận độ rung, nhiệt độ ổ trục, dòng điện, áp suất và tiếng ồn tại điều kiện vận hành ổn định.
4. Quan sát bu lông bệ, tấm che khớp nối và dấu hiệu lệch hoặc lỏng từ bên ngoài.
5. So sánh thông số với baseline và giới hạn nhà sản xuất; ghi lại kết quả kiểm tra.
Khi nào cần hỗ trợ chuyên môn: Dừng thiết bị theo quy trình và liên hệ kỹ thuật trưởng hoặc chuyên gia khi rung tăng nhanh, ổ trục quá nhiệt, rò rỉ lớn, cavitation kéo dài hoặc thiết bị bảo vệ tác động.
Giới hạn: Không căn chỉnh khớp nối, thay phớt, tháo ổ trục hoặc thay đổi van ngoài thẩm quyền từ checklist này.""",
        ),
        (
            "DOC-004",
            "Hướng dẫn kiểm tra máy bơm rung hoặc ồn bất thường",
            "troubleshooting_guide",
            "pump",
            "Tài liệu minh họa nội bộ - máy bơm",
            """Phạm vi: Hướng dẫn synthetic minh họa để kiểm tra ban đầu khi máy bơm rung hoặc phát tiếng ồn bất thường; không phải chẩn đoán hư hỏng tự động.
An toàn: Giữ khoảng cách với bộ phận quay, không tháo tấm che khi máy chạy và không chạm đường ống đang có áp. Nếu cần kiểm tra cơ khí, phải dừng máy, cô lập mọi nguồn năng lượng và áp dụng lockout/tagout.
Các bước kiểm tra:
1. Ghi nhận thời điểm, chế độ tải, vị trí phát tiếng ồn và giá trị rung hiện tại.
2. So sánh rung, nhiệt độ ổ trục, dòng điện và áp suất với baseline cùng điều kiện vận hành.
3. Quan sát bên ngoài bệ máy, bu lông, tấm che, đường ống và dấu hiệu rò rỉ hoặc cavitation.
4. Kiểm tra điều kiện hút/xả và trạng thái van theo sơ đồ vận hành đã phê duyệt, không tự thay đổi cấu hình hệ thống.
5. Ghi lại xu hướng và chuyển bằng chứng cho người có thẩm quyền đánh giá căn chỉnh, ổ trục hoặc phớt.
Khi nào cần hỗ trợ chuyên môn: Dừng theo quy trình và liên hệ kỹ thuật trưởng hoặc chuyên gia rotating equipment khi rung vượt giới hạn nhà sản xuất, có tiếng va đập, nhiệt tăng nhanh, mất áp hoặc rò rỉ nguy hiểm.
Giới hạn: Không tiếp tục chạy thử nhiều lần, không căn chỉnh, tháo khớp nối hoặc can thiệp ổ trục chỉ dựa trên hướng dẫn minh họa này.""",
        ),
        (
            "DOC-005",
            "Checklist kiểm tra định kỳ máy phát điện dự phòng",
            "checklist",
            "generator",
            "Tài liệu minh họa nội bộ - máy phát điện",
            """Phạm vi: Checklist synthetic minh họa cho kiểm tra định kỳ máy phát điện dự phòng; không thay thế manual, kế hoạch chạy thử hoặc quy trình điện của tòa nhà.
An toàn: Chỉ nhân sự được phân quyền mới thao tác máy phát và ATS. Thực hiện kiểm soát nguồn điện, chống khởi động ngoài ý muốn, thông gió và phòng cháy theo quy định. Không chạm đầu cực, dây dẫn hoặc bộ phận nóng khi chưa bảo đảm an toàn.
Các bước kiểm tra:
1. Xác nhận mã thiết bị, chế độ Auto/Manual theo kế hoạch và các cảnh báo hiện có mà không thay đổi cài đặt bảo vệ.
2. Quan sát mức nhiên liệu, dầu, nước làm mát, rò rỉ và tình trạng khu vực bằng phương pháp được nhà sản xuất cho phép.
3. Kiểm tra trực quan ắc quy, cáp, bộ sạc và thông gió; không đo hoặc tháo đầu cực nếu không đủ thẩm quyền.
4. Khi có kế hoạch chạy thử được phê duyệt, ghi nhận điện áp, tần số, nhiệt độ, độ rung, áp suất dầu và thời gian chạy.
5. Xác nhận cảnh báo, tấm che và khu vực máy đã được bàn giao an toàn; lưu kết quả vào maintenance log.
Khi nào cần hỗ trợ chuyên môn: Liên hệ kỹ thuật trưởng hoặc đơn vị máy phát khi có rò nhiên liệu, khói bất thường, quá nhiệt, điện áp/tần số ngoài giới hạn, lỗi ATS hoặc cảnh báo bảo vệ lặp lại.
Giới hạn: Không tự điều chỉnh governor, AVR, ATS, hệ thống nhiên liệu hoặc vô hiệu hóa bảo vệ từ checklist này.""",
        ),
        (
            "DOC-006",
            "Hướng dẫn kiểm tra máy phát điện không khởi động",
            "troubleshooting_guide",
            "generator",
            "Tài liệu minh họa nội bộ - máy phát điện",
            """Phạm vi: Hướng dẫn synthetic minh họa để thu thập thông tin ban đầu khi máy phát điện không khởi động; không thay thế hướng dẫn nhà sản xuất và không cho phép khởi động cưỡng bức.
An toàn: Không đấu tắt interlock, relay bảo vệ, cảm biến hoặc mạch khởi động. Chỉ nhân sự được phân quyền mới kiểm tra điện. Bảo đảm thông gió, phòng cháy và chống khởi động ngoài ý muốn theo quy định của tòa nhà.
Các bước kiểm tra:
1. Ghi nhận chế độ điều khiển, mã cảnh báo, thời điểm yêu cầu khởi động và trạng thái emergency stop từ màn hình an toàn.
2. Kiểm tra trực quan mức nhiên liệu, dầu, nước làm mát, rò rỉ và vật cản mà không mở hệ thống đang có áp hoặc còn nóng.
3. Quan sát tình trạng ắc quy, bộ sạc và đầu cáp từ vị trí an toàn; chỉ đo điện khi có thẩm quyền và thiết bị phù hợp.
4. Xác nhận điều kiện cho phép khởi động và trạng thái ATS theo manual; không reset cảnh báo lặp lại nếu chưa xác định nguyên nhân.
5. Lưu mã lỗi, thông số và lịch sử lần khởi động để chuyển cho kỹ thuật trưởng hoặc đơn vị chuyên môn.
Khi nào cần hỗ trợ chuyên môn: Chuyển cấp ngay khi có mùi nhiên liệu, khói, dây dẫn hư hỏng, điện áp ắc quy bất thường, lỗi ATS, emergency stop không rõ nguyên nhân hoặc cảnh báo bảo vệ tái diễn.
Giới hạn: Không câu bình, cấp nhiên liệu trực tiếp, đấu tắt mạch, reset bảo vệ liên tục hoặc chạy thử cưỡng bức theo tài liệu minh họa này.""",
        ),
    ]
    rows = []
    for doc_id, title, doc_type, asset_type, source, text in templates:
        rows.append(
            {
                "doc_id": doc_id,
                "title": title,
                "doc_type": DOCUMENT_TYPE_CODE_TO_VI[doc_type],
                "asset_type": ASSET_TYPE_CODE_TO_VI[asset_type],
                "source": source,
                "raw_text": text,
                "clean_text": " ".join(text.lower().split()),
                "created_at": datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc).isoformat(),
            }
        )
    return pd.DataFrame(rows)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def main() -> None:
    """Generate focused maintenance CSV files from the command line."""

    parser = argparse.ArgumentParser(description="Generate synthetic maintenance data.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--asset-count", type=int, default=DEFAULT_ASSET_COUNT)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--frequency", choices=["hourly", "daily"], default=DEFAULT_FREQUENCY)
    args = parser.parse_args()

    dataset = generate_dataset(
        asset_count=args.asset_count,
        days=args.days,
        frequency=args.frequency,
        seed=args.seed,
    )
    save_dataset(dataset, args.output_dir)

    for name, frame in dataset.items():
        print(f"Wrote {len(frame):>7} rows: {args.output_dir / DATASET_FILENAMES[name]}")


if __name__ == "__main__":
    main()
