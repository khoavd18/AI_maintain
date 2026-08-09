"""Anomaly detection over engineered daily asset-level maintenance features."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from src.config.value_mappings import ANOMALY_TYPE_CODE_TO_VI

DEFAULT_FEATURE_INPUT_PATH = Path("data/processed/asset_daily_features.csv")
DEFAULT_ANOMALY_OUTPUT_PATH = Path("data/processed/anomaly_results.csv")

ENERGY_DELTA_THRESHOLD_PERCENT = 50.0
VIBRATION_DELTA_THRESHOLD = 0.15
RUNTIME_DELTA_THRESHOLD_PERCENT = 40.0
TEMPERATURE_DELTA_THRESHOLD = 3.0
ANOMALY_SCORE_THRESHOLD = 60.0
DEFAULT_CONTAMINATION = 0.06
RANDOM_STATE = 42

NUMERIC_FEATURE_COLUMNS = [
    "energy_kwh",
    "temperature",
    "vibration",
    "runtime_hours",
    "energy_delta_percent",
    "vibration_delta",
    "runtime_delta_percent",
    "ticket_count_7d",
    "ticket_count_30d",
    "days_overdue",
    "criticality_score",
]

REQUIRED_FEATURE_COLUMNS = {
    "asset_id",
    "feature_date",
    "asset_type",
    "location",
    "energy_kwh",
    "temperature",
    "vibration",
    "runtime_hours",
    "pressure",
    "energy_delta_percent",
    "temperature_delta",
    "vibration_delta",
    "runtime_delta_percent",
    "ticket_count_7d",
    "ticket_count_30d",
    "days_overdue",
    "criticality_score",
}

ANOMALY_OUTPUT_COLUMNS = [
    "asset_id",
    "feature_date",
    "date",
    "asset_type",
    "location",
    "energy_kwh",
    "temperature",
    "vibration",
    "runtime_hours",
    "pressure",
    "energy_delta_percent",
    "vibration_delta",
    "runtime_delta_percent",
    "rule_based_score",
    "isolation_forest_score",
    "anomaly_score",
    "is_anomaly",
    "anomaly_type",
    "anomalous_metrics",
    "contributing_signals",
    "anomaly_reasons",
]

ANOMALY_METRIC_BY_SIGNAL = {
    "energy_spike": "energy_kwh",
    "vibration_increase": "vibration",
    "runtime_abnormal": "runtime_hours",
    "temperature_high": "temperature",
}


def load_feature_data(input_path: Path = DEFAULT_FEATURE_INPUT_PATH) -> pd.DataFrame:
    """Load engineered daily asset features from CSV."""

    if not input_path.exists():
        raise FileNotFoundError(f"Feature file not found: {input_path}")

    features = pd.read_csv(input_path)
    missing_columns = REQUIRED_FEATURE_COLUMNS - set(features.columns)
    if missing_columns:
        raise ValueError(
            f"Feature file is missing required anomaly-detection columns: {sorted(missing_columns)}"
        )

    features = features.copy()
    features["feature_date"] = pd.to_datetime(features["feature_date"], errors="raise").dt.date.astype(str)
    for column in NUMERIC_FEATURE_COLUMNS + ["temperature_delta"]:
        features[column] = pd.to_numeric(features[column], errors="coerce")
    features[NUMERIC_FEATURE_COLUMNS + ["temperature_delta"]] = features[
        NUMERIC_FEATURE_COLUMNS + ["temperature_delta"]
    ].replace([np.inf, -np.inf], np.nan)
    return features


def detect_rule_based_anomalies(features: pd.DataFrame) -> pd.DataFrame:
    """Detect threshold-based anomalies from rolling daily features."""

    results = features.copy()
    rule_scores: list[float] = []
    anomaly_types: list[str] = []
    rule_reasons: list[list[str]] = []
    anomalous_metrics: list[list[str]] = []

    for row in results.itertuples(index=False):
        signals = _rule_signals(row)
        rule_scores.append(max((score for _, score, _ in signals), default=0.0))
        anomaly_types.append(_primary_anomaly_type(signals))
        rule_reasons.append([reason for _, _, reason in signals])
        anomalous_metrics.append(
            [ANOMALY_METRIC_BY_SIGNAL[signal_code] for signal_code, _, _ in signals]
        )

    results["rule_based_score"] = rule_scores
    results["rule_anomaly_type"] = anomaly_types
    results["rule_reasons"] = rule_reasons
    results["rule_anomalous_metrics"] = anomalous_metrics
    return results


def detect_isolation_forest_anomalies(
    features: pd.DataFrame,
    contamination: float = DEFAULT_CONTAMINATION,
) -> pd.DataFrame:
    """Run Isolation Forest on numeric feature columns and return anomaly severity."""

    results = features.copy()
    results["isolation_forest_score"] = 0.0
    results["isolation_forest_is_anomaly"] = False

    for _, group_index in results.groupby("asset_type").groups.items():
        group = results.loc[group_index]
        if len(group) < 8:
            continue

        numeric_frame = _prepare_numeric_features(group)
        scaled_features = StandardScaler().fit_transform(numeric_frame)
        model = IsolationForest(
            contamination=contamination,
            random_state=RANDOM_STATE,
            n_estimators=150,
        )
        predictions = model.fit_predict(scaled_features)
        raw_scores = -model.decision_function(scaled_features)
        severity = _rank_to_severity(pd.Series(raw_scores, index=group.index))

        results.loc[group.index, "isolation_forest_score"] = severity
        results.loc[group.index, "isolation_forest_is_anomaly"] = predictions == -1

    return results


def combine_anomaly_scores(features: pd.DataFrame) -> pd.DataFrame:
    """Combine rule-based severity and Isolation Forest severity into a 0-100 score."""

    results = features.copy()
    combined = 0.70 * results["rule_based_score"] + 0.30 * results["isolation_forest_score"]
    results["anomaly_score"] = combined.clip(0, 100).round(2)
    results["is_anomaly"] = results["anomaly_score"] >= ANOMALY_SCORE_THRESHOLD
    results["anomaly_type"] = np.where(
        results["is_anomaly"],
        results["rule_anomaly_type"],
        ANOMALY_TYPE_CODE_TO_VI["none"],
    )
    results["anomaly_reasons"] = generate_anomaly_reasons(results)
    results["contributing_signals"] = results["anomaly_reasons"]
    results["anomalous_metrics"] = results.apply(_format_anomalous_metrics, axis=1)
    return results


def generate_anomaly_reasons(features: pd.DataFrame) -> pd.Series:
    """Generate Vietnamese explanations for anomaly results."""

    reasons: list[str] = []
    for row in features.itertuples(index=False):
        row_reasons = list(getattr(row, "rule_reasons", []) or [])
        if getattr(row, "isolation_forest_is_anomaly", False) or row.isolation_forest_score >= 90:
            row_reasons.append(
                "Mô hình Isolation Forest đánh dấu bản ghi này là bất thường so với các thiết bị cùng nhóm."
            )
        if not row_reasons:
            row_reasons.append("Không phát hiện dấu hiệu bất thường đáng kể.")
        reasons.append(" ".join(row_reasons))
    return pd.Series(reasons, index=features.index)


def build_anomaly_results(
    features: pd.DataFrame,
    contamination: float = DEFAULT_CONTAMINATION,
) -> pd.DataFrame:
    """Build final anomaly results from engineered daily features."""

    rule_results = detect_rule_based_anomalies(features)
    isolation_results = detect_isolation_forest_anomalies(rule_results, contamination=contamination)
    combined = combine_anomaly_scores(isolation_results)
    output = combined.copy()
    output["feature_date"] = pd.to_datetime(
        output["feature_date"], errors="raise"
    ).dt.date.astype(str)
    output["date"] = output["feature_date"]
    _validate_unique_asset_dates(output)
    output = output[ANOMALY_OUTPUT_COLUMNS].copy()
    output["is_anomaly"] = output["is_anomaly"].astype(bool)
    output = output.replace([np.inf, -np.inf], np.nan)
    if output.isna().any().any():
        numeric_columns = output.select_dtypes(include=[np.number]).columns
        output[numeric_columns] = output[numeric_columns].fillna(0.0)
        output = output.fillna("")
    return output


def _format_anomalous_metrics(row: pd.Series) -> str:
    metrics = list(row.get("rule_anomalous_metrics", []) or [])
    if row.get("isolation_forest_is_anomaly", False) and not metrics:
        metrics.append("multivariate_profile")
    return ", ".join(metrics) if metrics else "none"


def _validate_unique_asset_dates(results: pd.DataFrame) -> None:
    duplicate = results.duplicated(["asset_id", "feature_date"], keep=False)
    if duplicate.any():
        row = results.loc[duplicate].iloc[0]
        raise ValueError(
            "Anomaly input contains duplicate asset/date row: "
            f"asset_id={row['asset_id']} feature_date={row['feature_date']}"
        )


def save_anomaly_results(
    results: pd.DataFrame,
    output_path: Path = DEFAULT_ANOMALY_OUTPUT_PATH,
) -> None:
    """Save anomaly results to CSV."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_path, index=False)


def run_anomaly_detection(
    input_path: Path = DEFAULT_FEATURE_INPUT_PATH,
    output_path: Path = DEFAULT_ANOMALY_OUTPUT_PATH,
    contamination: float = DEFAULT_CONTAMINATION,
) -> pd.DataFrame:
    """Load features, run anomaly detection, save results, and return the frame."""

    features = load_feature_data(input_path)
    results = build_anomaly_results(features, contamination=contamination)
    save_anomaly_results(results, output_path)
    return results


def _rule_signals(row: object) -> list[tuple[str, float, str]]:
    signals: list[tuple[str, float, str]] = []

    energy_delta = _safe_float(row.energy_delta_percent)
    if energy_delta >= ENERGY_DELTA_THRESHOLD_PERCENT:
        signals.append(
            (
                "energy_spike",
                _threshold_severity(energy_delta, ENERGY_DELTA_THRESHOLD_PERCENT),
                f"Điện năng tiêu thụ tăng {energy_delta:.1f}% so với trung bình 7 ngày.",
            )
        )

    vibration_delta = _safe_float(row.vibration_delta)
    if vibration_delta >= VIBRATION_DELTA_THRESHOLD:
        signals.append(
            (
                "vibration_increase",
                _threshold_severity(vibration_delta, VIBRATION_DELTA_THRESHOLD),
                "Độ rung tăng mạnh so với mức nền của thiết bị.",
            )
        )

    runtime_delta = _safe_float(row.runtime_delta_percent)
    if runtime_delta >= RUNTIME_DELTA_THRESHOLD_PERCENT:
        signals.append(
            (
                "runtime_abnormal",
                _threshold_severity(runtime_delta, RUNTIME_DELTA_THRESHOLD_PERCENT),
                (
                    f"Thời gian vận hành tăng {runtime_delta:.1f}%, "
                    "có thể thiết bị đang hoạt động kém hiệu quả."
                ),
            )
        )

    temperature_delta = _safe_float(getattr(row, "temperature_delta", 0.0))
    if temperature_delta >= TEMPERATURE_DELTA_THRESHOLD:
        signals.append(
            (
                "temperature_high",
                _threshold_severity(temperature_delta, TEMPERATURE_DELTA_THRESHOLD),
                f"Nhiệt độ trung bình tăng {temperature_delta:.1f}°C so với mức nền 7 ngày.",
            )
        )

    return signals


def _primary_anomaly_type(signals: list[tuple[str, float, str]]) -> str:
    if not signals:
        return ANOMALY_TYPE_CODE_TO_VI["none"]
    signal_code = max(signals, key=lambda signal: signal[1])[0]
    return ANOMALY_TYPE_CODE_TO_VI[signal_code]


def _prepare_numeric_features(features: pd.DataFrame) -> pd.DataFrame:
    numeric_frame = features[NUMERIC_FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    numeric_frame = numeric_frame.replace([np.inf, -np.inf], np.nan)
    return numeric_frame.fillna(numeric_frame.median()).fillna(0.0)


def _rank_to_severity(raw_scores: pd.Series) -> pd.Series:
    if raw_scores.nunique(dropna=False) <= 1:
        return pd.Series(0.0, index=raw_scores.index)
    return raw_scores.rank(method="average", pct=True) * 100


def _threshold_severity(value: float, threshold: float) -> float:
    if value < threshold:
        return 0.0
    return min(100.0, 90.0 + ((value - threshold) / max(threshold, 1e-9)) * 10.0)


def _safe_float(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(number):
        return 0.0
    return number


def main() -> None:
    """Run anomaly detection from the command line."""

    parser = argparse.ArgumentParser(description="Detect anomalies from daily asset-level features.")
    parser.add_argument("--input-path", type=Path, default=DEFAULT_FEATURE_INPUT_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_ANOMALY_OUTPUT_PATH)
    parser.add_argument("--contamination", type=float, default=DEFAULT_CONTAMINATION)
    args = parser.parse_args()

    results = run_anomaly_detection(
        input_path=args.input_path,
        output_path=args.output_path,
        contamination=args.contamination,
    )
    anomaly_count = int(results["is_anomaly"].sum())
    print(f"Wrote {len(results):>7} rows: {args.output_path}")
    print(f"Detected {anomaly_count:>7} anomalous rows")


if __name__ == "__main__":
    main()
