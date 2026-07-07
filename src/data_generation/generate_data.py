"""Generate deterministic synthetic facility-maintenance datasets."""

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.config.value_mappings import (
    ANOMALY_TYPE_CODE_TO_VI,
    ASSET_TYPE_CODE_TO_VI,
    ASSET_TYPE_VI_TO_CODE,
    CRITICALITY_CODE_TO_VI,
    CRITICALITY_VI_TO_SCORE,
    DOCUMENT_TYPE_CODE_TO_VI,
    FAILURE_TYPE_CODE_TO_VI,
    MAINTENANCE_TYPE_CODE_TO_VI,
    PRIORITY_CODE_TO_VI,
    RISK_LEVEL_CODE_TO_VI,
    STATUS_CODE_TO_VI,
)

DEFAULT_SEED = 42
DEFAULT_ASSET_COUNT = 100
DEFAULT_DAYS = 60
DEFAULT_FREQUENCY = "hourly"
DATA_START = datetime(2026, 5, 2, tzinfo=timezone.utc)
SCORE_DATE = date(2026, 7, 1)

DATASET_FILENAMES = {
    "assets": "assets.csv",
    "sensor_readings": "sensor_readings.csv",
    "maintenance_tickets": "maintenance_tickets.csv",
    "maintenance_logs": "maintenance_logs.csv",
    "risk_scores": "risk_scores.csv",
    "documents": "documents.csv",
}

ASSET_TYPE_COUNTS = {
    "hvac": 25,
    "water_pump": 20,
    "elevator": 15,
    "generator": 10,
    "lighting": 20,
    "energy_meter": 10,
}

# Asset type keys and prefixes stay in English for stable IDs; only the
# human-readable "label" (used to build asset_name) is Vietnamese.
ASSET_CONFIG = {
    "hvac": {
        "prefix": "HVAC",
        "label": "Máy lạnh",
        "frequency_days": 90,
        "criticality": (0.62, 0.95),
    },
    "water_pump": {
        "prefix": "PUMP",
        "label": "Máy bơm nước",
        "frequency_days": 60,
        "criticality": (0.58, 0.92),
    },
    "elevator": {
        "prefix": "ELEV",
        "label": "Thang máy",
        "frequency_days": 30,
        "criticality": (0.72, 0.98),
    },
    "generator": {
        "prefix": "GEN",
        "label": "Máy phát điện dự phòng",
        "frequency_days": 120,
        "criticality": (0.78, 1.0),
    },
    "lighting": {
        "prefix": "LITE",
        "label": "Tủ chiếu sáng",
        "frequency_days": 180,
        "criticality": (0.30, 0.70),
    },
    "energy_meter": {
        "prefix": "MTR",
        "label": "Đồng hồ điện năng",
        "frequency_days": 365,
        "criticality": (0.40, 0.78),
    },
}

ASSET_TYPE_COUNTS = {
    "hvac": 18,
    "pump": 16,
    "elevator": 12,
    "generator": 10,
    "lighting": 16,
    "electrical_panel": 10,
    "water_tank": 8,
    "fire_safety": 10,
}

ASSET_CONFIG = {
    "hvac": {
        "prefix": "HVAC",
        "label": ASSET_TYPE_CODE_TO_VI["hvac"],
        "frequency_days": 90,
        "criticality_codes": ["medium", "high", "critical"],
    },
    "pump": {
        "prefix": "PUMP",
        "label": ASSET_TYPE_CODE_TO_VI["pump"],
        "frequency_days": 60,
        "criticality_codes": ["medium", "high", "critical"],
    },
    "elevator": {
        "prefix": "ELEVATOR",
        "label": ASSET_TYPE_CODE_TO_VI["elevator"],
        "frequency_days": 30,
        "criticality_codes": ["high", "critical"],
    },
    "generator": {
        "prefix": "GENERATOR",
        "label": ASSET_TYPE_CODE_TO_VI["generator"],
        "frequency_days": 120,
        "criticality_codes": ["high", "critical"],
    },
    "lighting": {
        "prefix": "LIGHTING",
        "label": ASSET_TYPE_CODE_TO_VI["lighting"],
        "frequency_days": 180,
        "criticality_codes": ["low", "medium", "high"],
    },
    "electrical_panel": {
        "prefix": "PANEL",
        "label": ASSET_TYPE_CODE_TO_VI["electrical_panel"],
        "frequency_days": 120,
        "criticality_codes": ["high", "critical"],
    },
    "water_tank": {
        "prefix": "TANK",
        "label": ASSET_TYPE_CODE_TO_VI["water_tank"],
        "frequency_days": 90,
        "criticality_codes": ["medium", "high"],
    },
    "fire_safety": {
        "prefix": "FIRE",
        "label": ASSET_TYPE_CODE_TO_VI["fire_safety"],
        "frequency_days": 30,
        "criticality_codes": ["critical"],
    },
}

LOCATIONS = [
    "Phòng máy khu Bắc",
    "Phòng máy khu Nam",
    "Sân thượng phía Đông",
    "Sân thượng phía Tây",
    "Khu lõi sảnh chính",
    "Tầng hầm kỹ thuật",
    "Tòa tháp A",
    "Tòa tháp B",
    "Tầng hầm để xe",
    "Khối đế thương mại",
]

TECHNICIANS = [
    "Nguyễn Văn An",
    "Trần Thị Mai",
    "Lê Hoàng Nam",
    "Phạm Minh Tuấn",
    "Võ Thị Hồng",
    "Đặng Quốc Bảo",
]


@dataclass(frozen=True)
class AnomalyPlan:
    """Assets selected for deterministic anomaly injection."""

    hvac_energy: set[str]
    pump_vibration: set[str]
    elevator_faults: set[str]
    generator_overdue: set[str]
    lighting_runtime: set[str]

    @property
    def all_assets(self) -> set[str]:
        """Return all assets with an injected anomaly pattern."""

        return (
            self.hvac_energy
            | self.pump_vibration
            | self.elevator_faults
            | self.generator_overdue
            | self.lighting_runtime
        )


def generate_dataset(
    asset_count: int = DEFAULT_ASSET_COUNT,
    days: int = DEFAULT_DAYS,
    frequency: str = DEFAULT_FREQUENCY,
    seed: int = DEFAULT_SEED,
) -> dict[str, pd.DataFrame]:
    """Generate all structured datasets for the facility maintenance MVP."""

    if asset_count <= 0:
        raise ValueError("asset_count must be positive")
    if days <= 0:
        raise ValueError("days must be positive")
    if frequency not in {"hourly", "daily"}:
        raise ValueError("frequency must be 'hourly' or 'daily'")

    rng = np.random.default_rng(seed)
    assets = _generate_assets(asset_count=asset_count, rng=rng)
    anomaly_plan = _build_anomaly_plan(assets)
    assets = _apply_anomaly_asset_status(assets, anomaly_plan)
    sensor_readings = _generate_sensor_readings(
        assets=assets,
        anomaly_plan=anomaly_plan,
        days=days,
        frequency=frequency,
        rng=rng,
    )
    maintenance_tickets = _generate_maintenance_tickets(
        assets=assets,
        anomaly_plan=anomaly_plan,
        days=days,
        rng=rng,
    )
    maintenance_logs = _generate_maintenance_logs(assets=assets, rng=rng)
    risk_scores = _generate_risk_scores(
        assets=assets,
        sensor_readings=sensor_readings,
        maintenance_tickets=maintenance_tickets,
        days=days,
    )
    documents = _generate_documents()

    return {
        "assets": assets,
        "sensor_readings": sensor_readings,
        "maintenance_tickets": maintenance_tickets,
        "maintenance_logs": maintenance_logs,
        "risk_scores": risk_scores,
        "documents": documents,
    }


def save_dataset(dataset: dict[str, pd.DataFrame], output_dir: Path) -> None:
    """Save generated datasets as CSV files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for dataset_name, filename in DATASET_FILENAMES.items():
        dataset[dataset_name].to_csv(output_dir / filename, index=False)


def _asset_type_sequence(asset_count: int) -> list[str]:
    if asset_count == sum(ASSET_TYPE_COUNTS.values()):
        return [
            asset_type
            for asset_type, count in ASSET_TYPE_COUNTS.items()
            for _ in range(count)
        ]

    weights = np.array(list(ASSET_TYPE_COUNTS.values()), dtype=float)
    raw_counts = weights / weights.sum() * asset_count
    counts = np.floor(raw_counts).astype(int)
    remainder = asset_count - int(counts.sum())
    for index in np.argsort(raw_counts - counts)[::-1][:remainder]:
        counts[index] += 1

    sequence: list[str] = []
    for asset_type, count in zip(ASSET_TYPE_COUNTS, counts, strict=True):
        sequence.extend([asset_type] * int(count))
    return sequence


def _generate_assets(asset_count: int, rng: np.random.Generator) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    type_counters = {asset_type: 0 for asset_type in ASSET_CONFIG}

    for asset_type in _asset_type_sequence(asset_count):
        type_counters[asset_type] += 1
        config = ASSET_CONFIG[asset_type]
        prefix = str(config["prefix"])
        sequence_number = type_counters[asset_type]
        frequency_days = int(config["frequency_days"])
        criticality_code = str(rng.choice(config["criticality_codes"]))
        installation_date = SCORE_DATE - timedelta(days=int(rng.integers(365, 365 * 13)))
        last_maintenance_date = SCORE_DATE - timedelta(
            days=int(rng.integers(7, frequency_days + 25))
        )

        rows.append(
            {
                "asset_id": f"{prefix}_{sequence_number:03d}",
                "asset_name": f"{config['label']} {sequence_number:03d}",
                "asset_type": ASSET_TYPE_CODE_TO_VI[asset_type],
                "location": str(rng.choice(LOCATIONS)),
                "floor": int(rng.integers(-1, 18)),
                "criticality": CRITICALITY_CODE_TO_VI[criticality_code],
                "installation_date": installation_date.isoformat(),
                "last_maintenance_date": last_maintenance_date.isoformat(),
                "maintenance_frequency_days": frequency_days,
                "status": STATUS_CODE_TO_VI["normal"],
            }
        )

    return pd.DataFrame(rows)


def _build_anomaly_plan(assets: pd.DataFrame) -> AnomalyPlan:
    def select(asset_type_code: str, limit: int) -> set[str]:
        asset_type = ASSET_TYPE_CODE_TO_VI[asset_type_code]
        asset_ids = assets.loc[assets["asset_type"] == asset_type, "asset_id"].head(limit)
        return set(asset_ids.tolist())

    return AnomalyPlan(
        hvac_energy=select("hvac", 5),
        pump_vibration=select("pump", 4),
        elevator_faults=select("elevator", 3),
        generator_overdue=select("generator", 2),
        lighting_runtime=select("lighting", 4),
    )


def _apply_anomaly_asset_status(assets: pd.DataFrame, anomaly_plan: AnomalyPlan) -> pd.DataFrame:
    updated = assets.copy()
    warning_assets = anomaly_plan.all_assets - anomaly_plan.generator_overdue
    updated.loc[updated["asset_id"].isin(warning_assets), "status"] = STATUS_CODE_TO_VI["warning"]
    updated.loc[updated["asset_id"].isin(anomaly_plan.generator_overdue), "status"] = STATUS_CODE_TO_VI[
        "warning"
    ]

    for asset_id in anomaly_plan.generator_overdue:
        row_index = updated.index[updated["asset_id"] == asset_id][0]
        frequency_days = int(updated.at[row_index, "maintenance_frequency_days"])
        overdue_date = SCORE_DATE - timedelta(days=frequency_days + 55)
        updated.at[row_index, "last_maintenance_date"] = overdue_date.isoformat()

    return updated


def _generate_sensor_readings(
    assets: pd.DataFrame,
    anomaly_plan: AnomalyPlan,
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
        for timestamp in timestamps:
            values = _simulate_reading(
                asset_id=str(asset.asset_id),
                asset_type=ASSET_TYPE_VI_TO_CODE[str(asset.asset_type)],
                timestamp=timestamp.to_pydatetime(),
                anomaly_plan=anomaly_plan,
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
    anomaly_plan: AnomalyPlan,
    days: int,
    hours_per_period: int,
    rng: np.random.Generator,
) -> dict[str, object]:
    hour = timestamp.hour
    weekday = timestamp.weekday()
    business_hours = weekday < 5 and 7 <= hour <= 19
    evening_hours = 17 <= hour <= 23
    anomaly_start = DATA_START + timedelta(days=max(days - 14, 0))
    recent_start = DATA_START + timedelta(days=max(days - 21, 0))
    status_code = "normal"
    anomaly_type_code = "none"

    if asset_type == "hvac":
        runtime = _clamp(float(rng.normal(0.82 if business_hours else 0.42, 0.08)))
        energy = (6.0 + 12.0 * runtime + rng.normal(0.0, 0.7)) * hours_per_period
        temperature = 22.5 + 4.5 * runtime + rng.normal(0.0, 0.7)
        vibration = max(0.02, 0.18 + rng.normal(0.0, 0.03))
        pressure = max(40.0, 96.0 + rng.normal(0.0, 5.0))
        if asset_id in anomaly_plan.hvac_energy and timestamp >= anomaly_start:
            energy *= float(rng.uniform(1.5, 1.8))
            temperature += float(rng.uniform(2.0, 4.0))
            status_code = "fault"
            anomaly_type_code = "energy_spike"
    elif asset_type == "pump":
        runtime = _clamp(float(rng.normal(0.66 if business_hours else 0.38, 0.12)))
        energy = (2.8 + 5.5 * runtime + rng.normal(0.0, 0.35)) * hours_per_period
        temperature = 34.0 + 15.0 * runtime + rng.normal(0.0, 1.2)
        vibration = max(0.05, 0.38 + 0.22 * runtime + rng.normal(0.0, 0.06))
        pressure = max(10.0, 52.0 + 9.0 * runtime + rng.normal(0.0, 3.5))
        if asset_id in anomaly_plan.pump_vibration and timestamp >= anomaly_start:
            vibration *= float(rng.uniform(2.4, 3.6))
            pressure -= float(rng.uniform(8.0, 16.0))
            status_code = "fault"
            anomaly_type_code = "vibration_increase"
    elif asset_type == "elevator":
        runtime = _clamp(float(rng.normal(0.46 if business_hours else 0.16, 0.08)))
        energy = (0.9 + 4.2 * runtime + rng.normal(0.0, 0.25)) * hours_per_period
        temperature = 24.0 + 6.0 * runtime + rng.normal(0.0, 0.8)
        vibration = max(0.02, 0.15 + 0.20 * runtime + rng.normal(0.0, 0.04))
        pressure = 0.0
        if asset_id in anomaly_plan.elevator_faults and timestamp >= recent_start:
            if rng.random() < 0.12:
                vibration *= float(rng.uniform(1.7, 2.5))
                status_code = "warning"
                anomaly_type_code = "vibration_increase"
    elif asset_type == "generator":
        weekly_test = weekday == 0 and hour == 10
        runtime = _clamp(float(rng.normal(0.85 if weekly_test else 0.03, 0.03)))
        energy = (0.2 + 18.0 * runtime + rng.normal(0.0, 0.3)) * hours_per_period
        temperature = 28.0 + 38.0 * runtime + rng.normal(0.0, 1.5)
        vibration = max(0.02, 0.12 + 0.45 * runtime + rng.normal(0.0, 0.04))
        pressure = max(0.0, 42.0 + 16.0 * runtime + rng.normal(0.0, 2.5))
        if asset_id in anomaly_plan.generator_overdue and timestamp >= recent_start:
            temperature += 3.5
            vibration *= 1.35
            status_code = "warning"
            anomaly_type_code = "temperature_high"
    elif asset_type == "lighting":
        runtime = 0.92 if business_hours or evening_hours else 0.18
        runtime = _clamp(float(rng.normal(runtime, 0.06)))
        energy = (1.4 + 7.5 * runtime + rng.normal(0.0, 0.25)) * hours_per_period
        temperature = 23.0 + 5.0 * runtime + rng.normal(0.0, 0.8)
        vibration = 0.0
        pressure = 0.0
        if asset_id in anomaly_plan.lighting_runtime and timestamp >= anomaly_start and hour <= 5:
            runtime = float(rng.uniform(0.92, 1.0))
            energy *= float(rng.uniform(1.55, 1.85))
            status_code = "fault"
            anomaly_type_code = "runtime_abnormal"
    else:
        runtime = 1.0
        building_load = 0.95 if business_hours else 0.55
        energy = (32.0 + 48.0 * building_load + rng.normal(0.0, 2.5)) * hours_per_period
        temperature = 24.0 + rng.normal(0.0, 1.0)
        vibration = 0.0
        pressure = 0.0

    if status_code == "normal" and rng.random() < 0.006:
        status_code = "warning"

    return {
        "energy_kwh": round(max(0.0, float(energy)), 3),
        "temperature": round(max(0.0, float(temperature)), 2),
        "vibration": round(max(0.0, float(vibration)), 4),
        "runtime_hours": round(max(0.0, float(runtime * hours_per_period)), 3),
        "pressure": round(max(0.0, float(pressure)), 2),
        "status": STATUS_CODE_TO_VI[status_code],
        "anomaly_type": ANOMALY_TYPE_CODE_TO_VI[anomaly_type_code],
    }


def _generate_maintenance_tickets(
    assets: pd.DataFrame,
    anomaly_plan: AnomalyPlan,
    days: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    ticket_number = 1

    for asset in assets.itertuples(index=False):
        asset_type_code = ASSET_TYPE_VI_TO_CODE[str(asset.asset_type)]
        base_count = int(rng.poisson(_ticket_lambda(asset_type_code)))
        for _ in range(base_count):
            ticket_number = _append_ticket(
                rows=rows,
                ticket_number=ticket_number,
                asset_id=str(asset.asset_id),
                asset_type=asset_type_code,
                days=days,
                rng=rng,
            )

    for asset_id in sorted(anomaly_plan.hvac_energy):
        for _ in range(2):
            ticket_number = _append_ticket(
                rows, ticket_number, asset_id, "hvac", days, rng, failure_type="cooling_issue"
            )

    for asset_id in sorted(anomaly_plan.pump_vibration):
        for _ in range(2):
            ticket_number = _append_ticket(
                rows, ticket_number, asset_id, "pump", days, rng, failure_type="vibration_issue"
            )

    for asset_id in sorted(anomaly_plan.elevator_faults):
        for _ in range(5):
            ticket_number = _append_ticket(
                rows, ticket_number, asset_id, "elevator", days, rng, failure_type="electrical_issue"
            )

    for asset_id in sorted(anomaly_plan.generator_overdue):
        ticket_number = _append_ticket(
            rows, ticket_number, asset_id, "generator", days, rng, failure_type="electrical_issue"
        )

    for asset_id in sorted(anomaly_plan.lighting_runtime):
        for _ in range(2):
            ticket_number = _append_ticket(
                rows,
                ticket_number,
                asset_id,
                "lighting",
                days,
                rng,
                failure_type="runtime_issue",
            )

    return pd.DataFrame(rows).sort_values("created_at").reset_index(drop=True)


def _append_ticket(
    rows: list[dict[str, object]],
    ticket_number: int,
    asset_id: str,
    asset_type: str,
    days: int,
    rng: np.random.Generator,
    failure_type: str | None = None,
) -> int:
    failure_type = failure_type or str(rng.choice(_failure_types(asset_type)))
    created_at = DATA_START + timedelta(
        days=int(rng.integers(0, days)),
        hours=int(rng.integers(6, 21)),
        minutes=int(rng.integers(0, 60)),
    )
    priority_code = _ticket_priority(failure_type)
    ticket_status_code = str(rng.choice(["resolved", "resolved", "open", "in_progress"]))
    if priority_code == "critical":
        ticket_status_code = str(rng.choice(["open", "in_progress", "resolved"]))
    resolved_at = ""
    if ticket_status_code == "resolved":
        resolved_at = (created_at + timedelta(days=int(rng.integers(1, 5)))).isoformat()

    rows.append(
        {
            "ticket_id": f"TCK-{ticket_number:06d}",
            "asset_id": asset_id,
            "issue_description": _issue_description(asset_type, failure_type),
            "priority": PRIORITY_CODE_TO_VI[priority_code],
            "status": STATUS_CODE_TO_VI[ticket_status_code],
            "created_at": created_at.isoformat(),
            "resolved_at": resolved_at,
            "technician_note": _technician_note(failure_type),
            "failure_type": FAILURE_TYPE_CODE_TO_VI[failure_type],
        }
    )
    return ticket_number + 1


def _ticket_lambda(asset_type: str) -> float:
    return {
        "hvac": 0.9,
        "pump": 0.8,
        "elevator": 1.2,
        "generator": 0.6,
        "lighting": 0.5,
        "electrical_panel": 0.7,
        "water_tank": 0.4,
        "fire_safety": 0.5,
    }.get(asset_type, 0.5)


def _failure_types(asset_type: str) -> list[str]:
    return {
        "hvac": ["cooling_issue", "sensor_issue", "runtime_issue"],
        "pump": ["vibration_issue", "pressure_issue", "sensor_issue"],
        "elevator": ["electrical_issue", "sensor_issue", "runtime_issue"],
        "generator": ["electrical_issue", "runtime_issue", "sensor_issue"],
        "lighting": ["runtime_issue", "electrical_issue", "sensor_issue"],
        "electrical_panel": ["electrical_issue", "sensor_issue"],
        "water_tank": ["pressure_issue", "sensor_issue"],
        "fire_safety": ["false_alarm", "sensor_issue", "electrical_issue"],
    }.get(asset_type, ["no_failure"])


def _ticket_priority(failure_type: str) -> str:
    if failure_type in {"electrical_issue"}:
        return "critical"
    if failure_type in {"vibration_issue", "pressure_issue", "runtime_issue", "cooling_issue"}:
        return "high"
    if failure_type in {"sensor_issue"}:
        return "medium"
    return "low"


def _issue_description(asset_type: str, failure_type: str) -> str:
    descriptions = {
        "cooling_issue": "Hiệu suất làm lạnh giảm, nhiệt độ khu vực phục vụ không đạt yêu cầu vận hành.",
        "vibration_issue": "Độ rung tăng cao so với đường cơ sở, cần kiểm tra cân chỉnh và bạc đạn.",
        "electrical_issue": "Thiết bị ghi nhận lỗi điện hoặc cảnh báo quá nhiệt trong quá trình vận hành.",
        "pressure_issue": "Áp suất vận hành lệch khỏi ngưỡng thiết kế trong nhiều chu kỳ đo.",
        "runtime_issue": "Thời gian vận hành bất thường so với lịch sử dụng và lịch điều khiển BMS.",
        "sensor_issue": "Dữ liệu cảm biến chập chờn hoặc nằm ngoài dải hiệu chuẩn.",
        "false_alarm": "Hệ thống phát cảnh báo nhưng chưa ghi nhận điều kiện sự cố thực tế.",
        "no_failure": "Không ghi nhận lỗi, tạo phiếu để kiểm tra xác nhận theo kế hoạch.",
        "abnormal_energy": "Điện năng tiêu thụ cao hơn mức bình thường so với lịch vận hành hiện tại.",
        "high_vibration": "Độ rung vượt ngưỡng cho phép khi thiết bị vận hành ở tải cao.",
        "door_fault": "Cửa thang máy báo lỗi khóa liên động và lặp lại sau khi khởi động lại.",
        "overdue_service": "Đã quá hạn chu kỳ bảo trì phòng ngừa.",
        "abnormal_runtime": "Đèn chiếu sáng vẫn bật ngoài khung giờ có người sử dụng.",
        "filter_clogged": "Lưu lượng gió giảm và chênh áp qua lưới lọc tăng cao.",
        "refrigerant_leak": "Hiệu suất làm lạnh giảm, nghi ngờ rò rỉ gas lạnh.",
        "sensor_fault": "Giá trị cảm biến chập chờn hoặc nằm ngoài dải hiệu chuẩn.",
        "seal_leak": "Phát hiện rò rỉ nước quanh khu vực phớt bơm.",
        "bearing_wear": "Có tiếng ồn từ bạc đạn khi máy bơm vận hành.",
        "low_pressure": "Áp suất đầu đẩy tụt xuống dưới ngưỡng vận hành.",
        "control_fault": "Bộ điều khiển báo lỗi truyền thông chập chờn.",
        "leveling_error": "Cabin thang máy dừng lệch so với mặt sàn tầng.",
        "repeated_stop": "Thang máy dừng đột ngột nhiều lần trong một ca trực.",
        "battery_fault": "Điện áp ắc quy khởi động của máy phát thấp hơn ngưỡng.",
        "coolant_leak": "Mức nước làm mát giảm sau khi chạy thử máy phát hàng tuần.",
        "failed_test": "Máy phát không hoàn tất bài kiểm tra chuyển nguồn theo lịch.",
        "ballast_failure": "Nhánh đèn nhấp nháy chập chờn và khởi động chậm.",
        "occupancy_sensor_fault": "Cảm biến hiện diện giữ mạch đèn luôn bật dù không có chuyển động.",
        "meter_drift": "Chỉ số đồng hồ điện sai lệch so với số liệu tham chiếu của điện lực.",
        "communication_loss": "Đồng hồ điện bị mất tín hiệu truyền thông nhiều lần.",
        "panel_overload": "Tải tủ điện tiến sát giới hạn của aptomat.",
    }
    return descriptions.get(failure_type, f"Cần kiểm tra thiết bị {asset_type}.")


def _technician_note(failure_type: str) -> str:
    notes = {
        "cooling_issue": "Kiểm tra lịch chạy, lưới lọc, dàn trao đổi nhiệt và cảm biến nhiệt độ.",
        "vibration_issue": "Kiểm tra độ đồng tâm, bu lông bệ máy, bạc đạn và tình trạng khớp nối.",
        "electrical_issue": "Kiểm tra tủ điện, đầu nối, tải dòng điện và dấu hiệu quá nhiệt.",
        "pressure_issue": "Đối chiếu áp suất đầu hút, đầu đẩy và kiểm tra rò rỉ đường ống.",
        "runtime_issue": "Đối chiếu lịch BMS, cảm biến hiện diện và lệnh ghi đè vận hành.",
        "sensor_issue": "Vệ sinh, hiệu chuẩn hoặc thay cảm biến nếu dữ liệu tiếp tục bất ổn.",
        "false_alarm": "Xác minh đầu báo, lịch sử báo động và điều kiện môi trường tại khu vực.",
        "no_failure": "Ghi nhận kết quả kiểm tra và tiếp tục theo dõi ở chu kỳ kế tiếp.",
        "abnormal_energy": "Đối chiếu lịch vận hành với lịch sử lệnh BMS và kiểm tra dàn coil.",
        "high_vibration": "Kiểm tra độ đồng tâm, bu lông bệ máy và tình trạng bạc đạn.",
        "door_fault": "Vệ sinh ray cửa, kiểm tra con lăn và căn chỉnh khóa liên động.",
        "overdue_service": "Lên lịch bảo trì phòng ngừa và thực hiện checklist an toàn.",
        "abnormal_runtime": "Kiểm tra cảm biến hiện diện và lịch hẹn giờ.",
    }
    return notes.get(failure_type, "Kiểm tra thiết bị và cập nhật lịch sử sau khi bảo trì.")


def _generate_maintenance_logs(assets: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    log_number = 1

    for asset in assets.itertuples(index=False):
        last_date = date.fromisoformat(str(asset.last_maintenance_date))
        frequency_days = int(asset.maintenance_frequency_days)
        rows.append(
            _maintenance_log_row(
                log_number=log_number,
                asset_id=str(asset.asset_id),
                asset_type=ASSET_TYPE_VI_TO_CODE[str(asset.asset_type)],
                maintenance_date=last_date,
                frequency_days=frequency_days,
                rng=rng,
            )
        )
        log_number += 1

        if rng.random() < 0.55:
            historical_date = last_date - timedelta(days=int(rng.integers(35, 180)))
            rows.append(
                _maintenance_log_row(
                    log_number=log_number,
                    asset_id=str(asset.asset_id),
                    asset_type=ASSET_TYPE_VI_TO_CODE[str(asset.asset_type)],
                    maintenance_date=historical_date,
                    frequency_days=frequency_days,
                    rng=rng,
                )
            )
            log_number += 1

    return pd.DataFrame(rows).sort_values("maintenance_date").reset_index(drop=True)


def _maintenance_log_row(
    log_number: int,
    asset_id: str,
    asset_type: str,
    maintenance_date: date,
    frequency_days: int,
    rng: np.random.Generator,
) -> dict[str, object]:
    maintenance_type_code = str(rng.choice(["preventive", "corrective", "inspection"]))
    actions_by_type = {
        "hvac": "Kiểm tra lưới lọc, dàn coil, dây curoa, đường thoát nước ngưng và hiệu chuẩn cảm biến nhiệt.",
        "water_pump": "Kiểm tra phớt, bạc đạn, độ đồng tâm, áp suất và dòng điện động cơ.",
        "elevator": "Kiểm tra hoạt động cửa, độ chính xác dừng tầng, nút dừng khẩn và lỗi bộ điều khiển.",
        "generator": "Kiểm tra ắc quy, nước làm mát, nhiên liệu, dầu nhớt và tủ chuyển nguồn.",
        "lighting": "Kiểm tra bộ đèn, bộ nguồn, cảm biến hiện diện và lịch hẹn giờ.",
        "energy_meter": "Kiểm tra truyền thông đồng hồ, sai lệch hiệu chuẩn và tải tủ điện.",
    }
    parts_by_type = {
        "hvac": ["lưới lọc", "dây curoa", "cảm biến nhiệt"],
        "water_pump": ["bộ phớt", "bạc đạn", "khớp nối"],
        "elevator": ["con lăn cửa", "công tắc khóa liên động", "rơ le"],
        "generator": ["ắc quy", "lọc dầu", "ống nước làm mát"],
        "lighting": ["bộ nguồn", "cảm biến hiện diện", "mô đun đèn"],
        "energy_meter": ["mô đun truyền thông", "biến dòng"],
    }
    actions_by_type.update(
        {
            "hvac": "Kiểm tra lưới lọc, dàn coil, dây curoa, đường thoát nước ngưng và cảm biến nhiệt.",
            "pump": "Kiểm tra phớt, bạc đạn, độ đồng tâm, áp suất và dòng điện động cơ.",
            "elevator": "Kiểm tra cửa, độ chính xác dừng tầng, nút dừng khẩn cấp và lịch sử lỗi bộ điều khiển.",
            "generator": "Kiểm tra ắc quy, nước làm mát, nhiên liệu, dầu nhớt và tủ chuyển nguồn.",
            "lighting": "Kiểm tra bộ đèn, bộ nguồn, cảm biến hiện diện và lịch hẹn giờ.",
            "electrical_panel": "Kiểm tra đầu nối, nhiệt độ tủ điện, tải dòng điện và tình trạng aptomat.",
            "water_tank": "Kiểm tra phao mức nước, van cấp xả, rò rỉ và tín hiệu cảm biến mức.",
            "fire_safety": "Kiểm tra trung tâm báo cháy, đầu báo, còi đèn và nguồn dự phòng.",
        }
    )
    parts_by_type.update(
        {
            "hvac": ["lưới lọc", "dây curoa", "cảm biến nhiệt"],
            "pump": ["bộ phớt", "bạc đạn", "khớp nối"],
            "elevator": ["con lăn cửa", "công tắc khóa liên động", "rơ le"],
            "generator": ["ắc quy", "lọc dầu", "ống nước làm mát"],
            "lighting": ["bộ nguồn", "cảm biến hiện diện", "mô đun đèn"],
            "electrical_panel": ["cầu dao điện", "đầu cos", "quạt tủ điện"],
            "water_tank": ["phao điện", "van một chiều", "cảm biến mức"],
            "fire_safety": ["đầu báo khói", "ắc quy dự phòng", "module tín hiệu"],
        }
    )
    parts = ", ".join(
        rng.choice(parts_by_type[asset_type], size=int(rng.integers(0, 3)), replace=False)
    )
    next_date = maintenance_date + timedelta(days=frequency_days)

    return {
        "log_id": f"LOG-{log_number:06d}",
        "asset_id": asset_id,
        "maintenance_date": maintenance_date.isoformat(),
        "maintenance_type": MAINTENANCE_TYPE_CODE_TO_VI[maintenance_type_code],
        "technician_name": str(rng.choice(TECHNICIANS)),
        "actions_taken": actions_by_type[asset_type],
        "parts_replaced": parts,
        "next_maintenance_date": next_date.isoformat(),
        "note": "Thiết bị đã được đưa trở lại vận hành; theo dõi dữ liệu xu hướng trong chu kỳ hoạt động tiếp theo.",
    }


def _generate_risk_scores(
    assets: pd.DataFrame,
    sensor_readings: pd.DataFrame,
    maintenance_tickets: pd.DataFrame,
    days: int,
) -> pd.DataFrame:
    recent_cutoff = pd.Timestamp(DATA_START + timedelta(days=max(days - 7, 0)))
    sensor_recent = sensor_readings[pd.to_datetime(sensor_readings["timestamp"]) >= recent_cutoff]
    sensor_signal_scores = sensor_recent.groupby("asset_id")["status"].apply(
        lambda s: (s == STATUS_CODE_TO_VI["fault"]).sum() * 2.5
        + (s == STATUS_CODE_TO_VI["warning"]).sum()
    )
    runtime_means = sensor_recent.groupby("asset_id")["runtime_hours"].mean()
    open_tickets = maintenance_tickets[
        maintenance_tickets["status"].isin([STATUS_CODE_TO_VI["open"], STATUS_CODE_TO_VI["in_progress"]])
    ].groupby("asset_id")["ticket_id"].count()

    rows: list[dict[str, object]] = []
    for index, asset in enumerate(assets.itertuples(index=False), start=1):
        asset_id = str(asset.asset_id)
        asset_type_code = ASSET_TYPE_VI_TO_CODE[str(asset.asset_type)]
        frequency_days = int(asset.maintenance_frequency_days)
        last_maintenance_date = date.fromisoformat(str(asset.last_maintenance_date))
        days_since_maintenance = (SCORE_DATE - last_maintenance_date).days
        overdue_days = max(0, days_since_maintenance - frequency_days)
        maintenance_overdue_score = min(100.0, overdue_days / max(frequency_days, 1) * 100)
        ticket_score = min(100.0, float(open_tickets.get(asset_id, 0)) * 28.0)
        criticality_score = round(float(CRITICALITY_VI_TO_SCORE[str(asset.criticality)] * 25), 2)
        anomaly_score = min(100.0, float(sensor_signal_scores.get(asset_id, 0)))
        expected_runtime = _expected_runtime(asset_type_code)
        runtime_score = min(
            100.0,
            max(0.0, (float(runtime_means.get(asset_id, expected_runtime)) - expected_runtime) * 85.0),
        )
        failure_probability = min(
            0.95,
            (
                0.0035 * anomaly_score
                + 0.0020 * maintenance_overdue_score
                + 0.0020 * ticket_score
                + 0.0015 * criticality_score
                + 0.0015 * runtime_score
            ),
        )
        final_risk_score = round(
            0.34 * anomaly_score
            + 0.20 * maintenance_overdue_score
            + 0.17 * ticket_score
            + 0.16 * criticality_score
            + 0.13 * runtime_score,
            2,
        )
        risk_level_code = _risk_level(final_risk_score)
        risk_level = RISK_LEVEL_CODE_TO_VI[risk_level_code]
        main_reasons = _risk_reasons(
            anomaly_score=anomaly_score,
            maintenance_overdue_score=maintenance_overdue_score,
            ticket_score=ticket_score,
            runtime_score=runtime_score,
            criticality_score=criticality_score,
        )

        rows.append(
            {
                "risk_id": f"RISK-{index:06d}",
                "asset_id": asset_id,
                "score_date": SCORE_DATE.isoformat(),
                "anomaly_score": round(anomaly_score, 2),
                "failure_probability": round(failure_probability, 3),
                "maintenance_overdue_score": round(maintenance_overdue_score, 2),
                "ticket_score": round(ticket_score, 2),
                "criticality_score": criticality_score,
                "runtime_score": round(runtime_score, 2),
                "final_risk_score": final_risk_score,
                "risk_level": risk_level,
                "main_reasons": "; ".join(main_reasons),
                "recommended_action": _recommended_action(
                    str(asset.asset_type), risk_level_code, main_reasons
                ),
            }
        )

    return pd.DataFrame(rows)


def _expected_runtime(asset_type: str) -> float:
    return {
        "hvac": 0.62,
        "pump": 0.52,
        "elevator": 0.31,
        "generator": 0.08,
        "lighting": 0.64,
        "electrical_panel": 1.0,
        "water_tank": 0.38,
        "fire_safety": 0.18,
    }.get(asset_type, 0.5)


def _risk_level(score: float) -> str:
    if score >= 75:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _risk_reasons_legacy(
    anomaly_score: float,
    maintenance_overdue_score: float,
    ticket_score: float,
    runtime_score: float,
    criticality_score: float,
) -> list[str]:
    reasons: list[str] = []
    if anomaly_score >= 30:
        reasons.append("xu hướng bất thường từ cảm biến")
    if maintenance_overdue_score >= 20:
        reasons.append("quá hạn bảo trì")
    if ticket_score >= 28:
        reasons.append("phiếu sự cố đang mở hoặc lặp lại")
    if runtime_score >= 20:
        reasons.append("thời gian vận hành bất thường")
    if criticality_score >= 80:
        reasons.append("thiết bị có mức trọng yếu cao")
    return reasons or ["hồ sơ vận hành bình thường"]


def _recommended_action_legacy(asset_type: str, risk_level: str, reasons: list[str]) -> str:
    if risk_level == "critical":
        return (
            f"Điều động kỹ thuật viên trong vòng 24 giờ và thực hiện checklist "
            f"kiểm tra khẩn cấp cho thiết bị {asset_type}."
        )
    if risk_level == "high":
        return f"Lên lịch bảo trì trong tuần này và rà soát lịch sử xu hướng của thiết bị {asset_type}."
    if "quá hạn bảo trì" in reasons:
        return "Bổ sung thiết bị vào lộ trình bảo trì phòng ngừa kế tiếp."
    return "Tiếp tục theo dõi và xem xét trong chu kỳ lập kế hoạch bảo trì tiếp theo."


def _risk_reasons(
    anomaly_score: float,
    maintenance_overdue_score: float,
    ticket_score: float,
    runtime_score: float,
    criticality_score: float,
) -> list[str]:
    reasons: list[str] = []
    if anomaly_score >= 30:
        reasons.append("xu hướng bất thường từ cảm biến")
    if maintenance_overdue_score >= 20:
        reasons.append("quá hạn bảo trì")
    if ticket_score >= 28:
        reasons.append("phiếu sự cố đang mở hoặc lặp lại")
    if runtime_score >= 20:
        reasons.append("thời gian vận hành bất thường")
    if criticality_score >= 80:
        reasons.append("thiết bị có mức trọng yếu cao")
    return reasons or ["hồ sơ vận hành bình thường"]


def _recommended_action(asset_type: str, risk_level: str, reasons: list[str]) -> str:
    if risk_level == "critical":
        return (
            f"Điều động kỹ thuật viên trong vòng 24 giờ và thực hiện checklist "
            f"kiểm tra khẩn cấp cho thiết bị {asset_type}."
        )
    if risk_level == "high":
        return f"Lên lịch bảo trì trong tuần này và rà soát lịch sử xu hướng của thiết bị {asset_type}."
    if "quá hạn bảo trì" in reasons:
        return "Bổ sung thiết bị vào lộ trình bảo trì phòng ngừa kế tiếp."
    return "Tiếp tục theo dõi và xem xét trong chu kỳ lập kế hoạch bảo trì tiếp theo."


def _generate_documents() -> pd.DataFrame:
    # doc_type and asset_type stay in English (enum). `title`, `source` and body text
    # are Vietnamese (user-facing); `source_path` is an English/path-like technical
    # reference kept separate from the Vietnamese citation text.
    templates = [
        (
            "DOC-001",
            "Quy trình xử lý sự cố điện năng và tiện nghi máy lạnh",
            "sop",
            "hvac",
            "Sổ tay kỹ thuật – Xử lý sự cố máy lạnh",
            "sop_docs/hvac_energy_anomaly.md",
            "Kiểm tra lệnh vận hành theo lịch, vệ sinh lưới lọc và dàn coil, kiểm tra vị trí van gió hồi, "
            "so sánh nhiệt độ gió cấp và gió hồi, xác nhận mức gas lạnh trước khi khởi động lại.",
        ),
        (
            "DOC-002",
            "Checklist bảo trì phòng ngừa máy lạnh",
            "checklist",
            "hvac",
            "Checklist bảo trì phòng ngừa máy lạnh",
            "sop_docs/hvac_pm_checklist.md",
            "Thay hoặc vệ sinh lưới lọc, kiểm tra dây curoa, vệ sinh khay nước ngưng, hiệu chuẩn cảm biến nhiệt, "
            "ghi lại dòng điện và xác nhận độ rung nằm trong ngưỡng bình thường.",
        ),
        (
            "DOC-003",
            "Quy trình xử lý rung động cao của máy bơm nước",
            "sop",
            "water_pump",
            "Quy trình an toàn – Rung động máy bơm",
            "sop_docs/pump_vibration_sop.md",
            "Cô lập và khóa nguồn máy bơm, kiểm tra độ đồng tâm khớp nối, kiểm tra bạc đạn, siết bu lông bệ máy, "
            "kiểm tra phớt và so sánh áp suất đầu đẩy trước khi đưa vào vận hành.",
        ),
        (
            "DOC-004",
            "Checklist bảo trì phòng ngừa máy bơm nước",
            "checklist",
            "water_pump",
            "Checklist bảo trì phòng ngừa máy bơm",
            "sop_docs/pump_pm_checklist.md",
            "Kiểm tra phớt, đối chiếu đồng hồ áp suất, kiểm tra dòng điện động cơ, tra mỡ bạc đạn, "
            "vệ sinh lọc rác và ghi nhận mọi tiếng ồn bất thường.",
        ),
        (
            "DOC-005",
            "Quy trình xử lý lỗi cửa thang máy lặp lại",
            "sop",
            "elevator",
            "Quy trình xử lý lỗi cửa thang máy",
            "sop_docs/elevator_door_fault.md",
            "Đưa thang máy về chế độ kiểm tra, kiểm tra vật cản trên ray cửa, vệ sinh cảm biến, "
            "căn chỉnh khóa liên động, xem lại lịch sử lỗi bộ điều khiển và chạy thử ba chu kỳ.",
        ),
        (
            "DOC-006",
            "Checklist kiểm tra an toàn thang máy",
            "checklist",
            "elevator",
            "Checklist kiểm tra an toàn thang máy",
            "sop_docs/elevator_safety_checklist.md",
            "Kiểm tra nút dừng khẩn, thiết bị mở lại cửa, độ chính xác dừng tầng, thông tin liên lạc báo động, "
            "tình trạng phòng máy và nhật ký sự kiện của bộ điều khiển.",
        ),
        (
            "DOC-007",
            "Quy trình bảo trì máy phát điện quá hạn",
            "sop",
            "generator",
            "Quy trình bảo trì máy phát quá hạn",
            "sop_docs/generator_overdue_sop.md",
            "Kiểm tra điện áp ắc quy, kiểm tra nước làm mát và dầu nhớt, xác nhận mức nhiên liệu, "
            "chạy thử tủ chuyển nguồn, chạy thử tải nếu được phép và ghi lại ngày bảo trì kế tiếp.",
        ),
        (
            "DOC-008",
            "Checklist chạy thử máy phát điện hàng tuần",
            "checklist",
            "generator",
            "Checklist chạy thử máy phát hàng tuần",
            "sop_docs/generator_weekly_test.md",
            "Kiểm tra rò rỉ, kiểm tra báo động, khởi động máy phát, theo dõi nhiệt độ và độ rung, "
            "xác nhận điện áp đầu ra và ghi lại thời gian chạy.",
        ),
        (
            "DOC-009",
            "Quy trình xử lý thời gian chiếu sáng bất thường",
            "sop",
            "lighting",
            "Quy trình xử lý thời gian chiếu sáng bất thường",
            "sop_docs/lighting_runtime_sop.md",
            "So sánh lịch hẹn giờ với dữ liệu hiện diện, kiểm tra cảm biến hiện diện, kiểm tra trạng thái rơ le, "
            "xác nhận lệnh ghi đè từ BMS và đặt lại lịch sau khi kiểm tra.",
        ),
        (
            "DOC-010",
            "Checklist bảo trì phòng ngừa hệ thống chiếu sáng",
            "checklist",
            "lighting",
            "Checklist bảo trì phòng ngừa hệ thống chiếu sáng",
            "sop_docs/lighting_pm_checklist.md",
            "Kiểm tra bộ nguồn, thay các bóng đèn hỏng, vệ sinh chóa đèn, kiểm tra đèn chiếu sáng khẩn cấp, "
            "xác nhận cảm biến hiện diện và ghi lại thời gian chạy của mạch đèn.",
        ),
    ]
    rows = []
    for doc_id, title, doc_type, asset_type, source, _source_path, text in templates:
        asset_type_code = "pump" if asset_type == "water_pump" else asset_type
        rows.append(
            {
                "doc_id": doc_id,
                "title": title,
                "doc_type": DOCUMENT_TYPE_CODE_TO_VI[doc_type],
                "asset_type": ASSET_TYPE_CODE_TO_VI[asset_type_code],
                "source": source,
                "raw_text": text,
                "clean_text": " ".join(text.lower().split()),
                "created_at": datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc).isoformat(),
            }
        )
    return pd.DataFrame(rows)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def main() -> None:
    """Generate CSV files from the command line."""

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
