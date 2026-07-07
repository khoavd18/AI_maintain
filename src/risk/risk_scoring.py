"""Explainable equipment risk scoring from anomaly and daily feature outputs."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.config.value_mappings import ASSET_TYPE_CODE_TO_VI, RISK_LEVEL_CODE_TO_VI

DEFAULT_FEATURE_INPUT_PATH = Path("data/processed/asset_daily_features.csv")
DEFAULT_ANOMALY_INPUT_PATH = Path("data/processed/anomaly_results.csv")
DEFAULT_RISK_OUTPUT_PATH = Path("data/processed/risk_scores.csv")

RISK_OUTPUT_COLUMNS = [
    "asset_id",
    "date",
    "asset_name",
    "asset_type",
    "location",
    "anomaly_score",
    "maintenance_overdue_score",
    "recent_ticket_score",
    "criticality_score",
    "runtime_score",
    "final_risk_score",
    "risk_level",
    "main_reasons",
    "recommended_action",
]

REQUIRED_FEATURE_COLUMNS = {
    "asset_id",
    "feature_date",
    "asset_name",
    "asset_type",
    "location",
    "days_overdue",
    "ticket_count_30d",
    "high_priority_ticket_count_30d",
    "criticality_score",
    "runtime_delta_percent",
}

REQUIRED_ANOMALY_COLUMNS = {
    "asset_id",
    "date",
    "anomaly_score",
    "anomaly_type",
    "anomaly_reasons",
}

ACTION_BY_ASSET_TYPE = {
    ASSET_TYPE_CODE_TO_VI["hvac"]: "Kiểm tra lưới lọc, thermostat, gas lạnh và dàn nóng.",
    ASSET_TYPE_CODE_TO_VI["pump"]: "Kiểm tra độ rung, bạc đạn, áp suất và van.",
    ASSET_TYPE_CODE_TO_VI["elevator"]: (
        "Kiểm tra hệ thống điều khiển, cảm biến tầng và chạy thử nhiều lượt."
    ),
    ASSET_TYPE_CODE_TO_VI["generator"]: (
        "Kiểm tra ắc quy, dầu, nước làm mát và chạy thử tải."
    ),
    ASSET_TYPE_CODE_TO_VI["electrical_panel"]: (
        "Kiểm tra nhiệt độ tủ, đầu cos, aptomat và tải tiêu thụ."
    ),
    ASSET_TYPE_CODE_TO_VI["lighting"]: (
        "Kiểm tra nguồn cấp, timer, bóng đèn và runtime bất thường."
    ),
    ASSET_TYPE_CODE_TO_VI["water_tank"]: (
        "Kiểm tra phao mức nước, van cấp xả, rò rỉ và cảm biến mức."
    ),
    ASSET_TYPE_CODE_TO_VI["fire_safety"]: (
        "Kiểm tra trung tâm báo cháy, đầu báo, còi đèn và nguồn dự phòng."
    ),
}


def load_inputs(
    feature_path: Path = DEFAULT_FEATURE_INPUT_PATH,
    anomaly_path: Path = DEFAULT_ANOMALY_INPUT_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load feature and anomaly CSV inputs for risk scoring."""

    if not feature_path.exists():
        raise FileNotFoundError(f"Feature file not found: {feature_path}")
    if not anomaly_path.exists():
        raise FileNotFoundError(f"Anomaly file not found: {anomaly_path}")

    features = pd.read_csv(feature_path)
    anomalies = pd.read_csv(anomaly_path)
    _validate_columns(features, REQUIRED_FEATURE_COLUMNS, "feature input")
    _validate_columns(anomalies, REQUIRED_ANOMALY_COLUMNS, "anomaly input")
    return features, anomalies


def calculate_maintenance_overdue_score(days_overdue: object) -> float:
    """Convert days overdue into a 0-100 maintenance overdue score."""

    days = _safe_float(days_overdue)
    if days <= 0:
        return 0.0
    if days <= 7:
        return 30.0
    if days <= 30:
        return 60.0
    return 100.0


def calculate_recent_ticket_score(
    ticket_count_30d: object,
    high_priority_ticket_count_30d: object,
) -> float:
    """Score recent ticket load with an additional high-priority penalty."""

    ticket_count = _safe_float(ticket_count_30d)
    high_priority_count = _safe_float(high_priority_ticket_count_30d)

    if ticket_count <= 0:
        score = 0.0
    elif ticket_count == 1:
        score = 30.0
    elif ticket_count <= 3:
        score = 60.0
    else:
        score = 80.0

    if high_priority_count > 0:
        score += 20.0
    return min(score, 100.0)


def calculate_runtime_score(runtime_delta_percent: object) -> float:
    """Convert runtime delta percent into a 0-100 runtime behavior score."""

    runtime_delta = _safe_float(runtime_delta_percent)
    if runtime_delta <= 10:
        return 0.0
    if runtime_delta <= 25:
        return 30.0
    if runtime_delta <= 50:
        return 70.0
    return 100.0


def normalize_criticality_score(criticality_score: object) -> float:
    """Normalize feature-engineered criticality score from 1-4 into 25-100."""

    score = _safe_float(criticality_score)
    return float(np.clip(score, 0, 4) * 25)


def calculate_final_risk_score(
    anomaly_score: object,
    maintenance_overdue_score: object,
    recent_ticket_score: object,
    criticality_score: object,
    runtime_score: object,
) -> float:
    """Calculate the final weighted 0-100 maintenance risk score."""

    final_score = (
        0.35 * _safe_float(anomaly_score)
        + 0.20 * _safe_float(maintenance_overdue_score)
        + 0.20 * _safe_float(recent_ticket_score)
        + 0.15 * _safe_float(criticality_score)
        + 0.10 * _safe_float(runtime_score)
    )
    return round(float(np.clip(final_score, 0, 100)), 2)


def assign_risk_level(final_risk_score: object) -> str:
    """Map a final risk score to a Vietnamese risk level."""

    score = _safe_float(final_risk_score)
    if score <= 30:
        return RISK_LEVEL_CODE_TO_VI["low"]
    if score <= 60:
        return RISK_LEVEL_CODE_TO_VI["medium"]
    if score <= 80:
        return RISK_LEVEL_CODE_TO_VI["high"]
    return RISK_LEVEL_CODE_TO_VI["critical"]


def generate_main_reasons(row: pd.Series) -> str:
    """Generate Vietnamese explanations from the main contributing risk factors."""

    candidates = [
        (
            row["anomaly_score"] * 0.35,
            _anomaly_reason(row),
        ),
        (
            row["maintenance_overdue_score"] * 0.20,
            _maintenance_reason(row),
        ),
        (
            row["recent_ticket_score"] * 0.20,
            _ticket_reason(row),
        ),
        (
            row["criticality_score"] * 0.15,
            _criticality_reason(row),
        ),
        (
            row["runtime_score"] * 0.10,
            _runtime_reason(row),
        ),
    ]
    reasons = [
        reason
        for _, reason in sorted(candidates, key=lambda item: item[0], reverse=True)
        if reason
    ][:3]
    return " ".join(reasons) if reasons else "Tài sản đang ở mức rủi ro thấp theo các tín hiệu hiện tại."


def generate_recommended_action(row: pd.Series) -> str:
    """Generate a Vietnamese maintenance recommendation for an asset."""

    base_action = ACTION_BY_ASSET_TYPE.get(
        row["asset_type"],
        "Kiểm tra tổng thể thiết bị, rà soát lịch sử vận hành và cập nhật kế hoạch bảo trì.",
    )
    if row["risk_level"] == RISK_LEVEL_CODE_TO_VI["critical"]:
        return f"Ưu tiên kiểm tra trong 24 giờ. {base_action}"
    if row["risk_level"] == RISK_LEVEL_CODE_TO_VI["high"]:
        return f"Lên lịch kiểm tra trong tuần này. {base_action}"
    if row["maintenance_overdue_score"] >= 60:
        return f"Bổ sung vào kế hoạch bảo trì định kỳ gần nhất. {base_action}"
    return f"Theo dõi trong chu kỳ vận hành tiếp theo. {base_action}"


def build_risk_scores(features: pd.DataFrame, anomalies: pd.DataFrame) -> pd.DataFrame:
    """Build explainable daily equipment risk scores."""

    feature_frame = features.copy()
    anomaly_frame = anomalies.copy()
    feature_frame["date"] = pd.to_datetime(feature_frame["feature_date"], errors="raise").dt.date.astype(str)
    anomaly_frame["date"] = pd.to_datetime(anomaly_frame["date"], errors="raise").dt.date.astype(str)

    risk_frame = feature_frame.merge(
        anomaly_frame[["asset_id", "date", "anomaly_score", "anomaly_type", "anomaly_reasons"]],
        on=["asset_id", "date"],
        how="left",
    )
    risk_frame["anomaly_score"] = pd.to_numeric(risk_frame["anomaly_score"], errors="coerce").fillna(0.0)
    risk_frame["maintenance_overdue_score"] = risk_frame["days_overdue"].map(
        calculate_maintenance_overdue_score
    )
    risk_frame["recent_ticket_score"] = risk_frame.apply(
        lambda row: calculate_recent_ticket_score(
            row["ticket_count_30d"], row["high_priority_ticket_count_30d"]
        ),
        axis=1,
    )
    risk_frame["criticality_score"] = risk_frame["criticality_score"].map(normalize_criticality_score)
    risk_frame["runtime_score"] = risk_frame["runtime_delta_percent"].map(calculate_runtime_score)
    risk_frame["final_risk_score"] = risk_frame.apply(
        lambda row: calculate_final_risk_score(
            row["anomaly_score"],
            row["maintenance_overdue_score"],
            row["recent_ticket_score"],
            row["criticality_score"],
            row["runtime_score"],
        ),
        axis=1,
    )
    risk_frame["risk_level"] = risk_frame["final_risk_score"].map(assign_risk_level)
    risk_frame["main_reasons"] = risk_frame.apply(generate_main_reasons, axis=1)
    risk_frame["recommended_action"] = risk_frame.apply(generate_recommended_action, axis=1)

    output = risk_frame[RISK_OUTPUT_COLUMNS].copy()
    output = output.replace([np.inf, -np.inf], np.nan)
    if output.isna().any().any():
        numeric_columns = output.select_dtypes(include=[np.number]).columns
        output[numeric_columns] = output[numeric_columns].fillna(0.0)
        output = output.fillna("")
    return output


def save_risk_scores(results: pd.DataFrame, output_path: Path = DEFAULT_RISK_OUTPUT_PATH) -> None:
    """Save risk scoring results to CSV."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_path, index=False)


def run_risk_scoring(
    feature_path: Path = DEFAULT_FEATURE_INPUT_PATH,
    anomaly_path: Path = DEFAULT_ANOMALY_INPUT_PATH,
    output_path: Path = DEFAULT_RISK_OUTPUT_PATH,
) -> pd.DataFrame:
    """Load inputs, build risk scores, save results, and return the output frame."""

    features, anomalies = load_inputs(feature_path=feature_path, anomaly_path=anomaly_path)
    results = build_risk_scores(features=features, anomalies=anomalies)
    save_risk_scores(results, output_path=output_path)
    return results


def _validate_columns(frame: pd.DataFrame, required_columns: set[str], label: str) -> None:
    missing_columns = required_columns - set(frame.columns)
    if missing_columns:
        raise ValueError(f"{label} is missing required columns: {sorted(missing_columns)}")


def _anomaly_reason(row: pd.Series) -> str:
    if row["anomaly_score"] < 40:
        return ""
    anomaly_reason = str(row.get("anomaly_reasons", "")).strip()
    if anomaly_reason and anomaly_reason != "nan":
        return f"Điểm bất thường cao do: {anomaly_reason}"
    return f"Điểm bất thường cao ({row['anomaly_score']:.1f}/100)."


def _maintenance_reason(row: pd.Series) -> str:
    if row["maintenance_overdue_score"] <= 0:
        return ""
    days_overdue = int(max(0, round(_safe_float(row["days_overdue"]))))
    return f"Thiết bị đã quá hạn bảo trì {days_overdue} ngày."


def _ticket_reason(row: pd.Series) -> str:
    if row["recent_ticket_score"] <= 0:
        return ""
    ticket_count = int(max(0, round(_safe_float(row["ticket_count_30d"]))))
    high_priority_count = int(max(0, round(_safe_float(row["high_priority_ticket_count_30d"]))))
    if high_priority_count > 0:
        return (
            f"Có {ticket_count} ticket trong 30 ngày gần nhất, "
            "bao gồm ticket ưu tiên cao."
        )
    return f"Có {ticket_count} ticket trong 30 ngày gần nhất."


def _criticality_reason(row: pd.Series) -> str:
    if row["criticality_score"] < 75:
        return ""
    return "Thiết bị thuộc nhóm rất quan trọng nên cần ưu tiên kiểm tra."


def _runtime_reason(row: pd.Series) -> str:
    if row["runtime_score"] < 70:
        return ""
    runtime_delta = _safe_float(row["runtime_delta_percent"])
    return (
        f"Runtime tăng {runtime_delta:.1f}%, "
        "có thể thiết bị đang hoạt động kém hiệu quả."
    )


def _safe_float(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(number):
        return 0.0
    return number


def main() -> None:
    """Run risk scoring from the command line."""

    parser = argparse.ArgumentParser(description="Build explainable equipment risk scores.")
    parser.add_argument("--feature-path", type=Path, default=DEFAULT_FEATURE_INPUT_PATH)
    parser.add_argument("--anomaly-path", type=Path, default=DEFAULT_ANOMALY_INPUT_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_RISK_OUTPUT_PATH)
    args = parser.parse_args()

    results = run_risk_scoring(
        feature_path=args.feature_path,
        anomaly_path=args.anomaly_path,
        output_path=args.output_path,
    )
    high_risk_count = int(
        results["risk_level"].isin([RISK_LEVEL_CODE_TO_VI["high"], RISK_LEVEL_CODE_TO_VI["critical"]]).sum()
    )
    print(f"Wrote {len(results):>7} rows: {args.output_path}")
    print(f"Flagged {high_risk_count:>7} high or urgent risk rows")


if __name__ == "__main__":
    main()
