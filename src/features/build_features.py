"""Daily asset-level feature engineering for maintenance analytics."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.config.value_mappings import PRIORITY_VI_TO_SCORE, criticality_score
from src.ingestion.validation import validate_csv_dataset, validate_feature_overdue_days

DEFAULT_FEATURE_OUTPUT_PATH = Path("data/processed/asset_daily_features.csv")

FEATURE_COLUMNS = [
    "asset_id",
    "feature_date",
    "asset_name",
    "asset_type",
    "location",
    "energy_kwh",
    "temperature",
    "vibration",
    "runtime_hours",
    "pressure",
    "rolling_avg_energy_7d",
    "rolling_std_energy_7d",
    "energy_delta_percent",
    "rolling_avg_temperature_7d",
    "temperature_delta",
    "rolling_avg_vibration_7d",
    "vibration_delta",
    "runtime_delta_percent",
    "last_maintenance_date",
    "next_maintenance_date",
    "days_since_last_maintenance",
    "days_overdue",
    "ticket_count_7d",
    "ticket_count_30d",
    "high_priority_ticket_count_30d",
    "asset_age_days",
    "criticality_score",
]


def build_daily_asset_features(
    assets: pd.DataFrame,
    sensor_readings: pd.DataFrame,
    maintenance_tickets: pd.DataFrame,
    maintenance_logs: pd.DataFrame,
) -> pd.DataFrame:
    """Build daily per-asset features from raw facility maintenance data."""

    assets_prepared = _prepare_assets(assets)
    readings_daily = _build_daily_sensor_features(sensor_readings)
    ticket_features = _build_ticket_features(readings_daily, maintenance_tickets)
    maintenance_features = _build_maintenance_features(
        readings_daily=readings_daily,
        assets=assets_prepared,
        maintenance_logs=maintenance_logs,
    )

    features = (
        readings_daily.merge(
            assets_prepared[["asset_id", "asset_name", "asset_type", "location"]],
            on="asset_id",
            how="left",
        )
        .merge(ticket_features, on=["asset_id", "feature_date"], how="left")
        .merge(maintenance_features, on=["asset_id", "feature_date"], how="left")
    )

    count_columns = ["ticket_count_7d", "ticket_count_30d", "high_priority_ticket_count_30d"]
    features[count_columns] = features[count_columns].fillna(0).astype(int)
    features = features[FEATURE_COLUMNS].sort_values(["asset_id", "feature_date"]).reset_index(drop=True)
    features["feature_date"] = features["feature_date"].dt.date.astype(str)
    for column in ["last_maintenance_date", "next_maintenance_date"]:
        features[column] = pd.to_datetime(features[column]).dt.date.astype(str)
    return features


def build_features_from_csv(
    input_dir: Path = Path("data/raw"),
    output_path: Path = DEFAULT_FEATURE_OUTPUT_PATH,
) -> pd.DataFrame:
    """Validate raw CSVs, build daily features, and save them to disk."""

    frames = validate_csv_dataset(input_dir)
    features = build_daily_asset_features(
        assets=frames["assets"],
        sensor_readings=frames["sensor_readings"],
        maintenance_tickets=frames["maintenance_tickets"],
        maintenance_logs=frames["maintenance_logs"],
    )
    validate_feature_overdue_days(features)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(output_path, index=False)
    return features


def build_asset_feature_frame(readings: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible aggregate feature helper for simple reading frames."""

    required_columns = {"asset_id", "value"}
    missing = required_columns - set(readings.columns)
    if missing:
        raise ValueError(f"Missing reading columns: {sorted(missing)}")

    features = (
        readings.groupby("asset_id")["value"]
        .agg(reading_count="count", value_mean="mean", value_std="std", value_max="max")
        .fillna(0.0)
        .reset_index()
    )
    return features


def _prepare_assets(assets: pd.DataFrame) -> pd.DataFrame:
    prepared = assets.copy()
    for column in [
        "installation_date",
        "last_maintenance_date",
        "next_maintenance_date",
    ]:
        prepared[column] = pd.to_datetime(prepared[column], errors="raise").dt.normalize()
    prepared["criticality_score"] = prepared["criticality"].map(criticality_score)
    return prepared


def _build_daily_sensor_features(sensor_readings: pd.DataFrame) -> pd.DataFrame:
    readings = sensor_readings.copy()
    readings["feature_date"] = _to_utc_naive_datetime(readings["timestamp"]).dt.normalize()

    aggregations: dict[str, tuple[str, str]] = {
        "daily_energy_kwh": ("energy_kwh", "sum"),
        "daily_avg_temperature": ("temperature", "mean"),
        "daily_avg_vibration": ("vibration", "mean"),
        "daily_runtime_hours": ("runtime_hours", "sum"),
    }
    if "pressure" in readings.columns:
        aggregations["daily_avg_pressure"] = ("pressure", "mean")

    daily = (
        readings.groupby(["asset_id", "feature_date"], as_index=False)
        .agg(**aggregations)
        .sort_values(["asset_id", "feature_date"])
    )
    if "daily_avg_pressure" not in daily.columns:
        daily["daily_avg_pressure"] = 0.0
    daily["energy_kwh"] = daily["daily_energy_kwh"]
    daily["temperature"] = daily["daily_avg_temperature"]
    daily["vibration"] = daily["daily_avg_vibration"]
    daily["runtime_hours"] = daily["daily_runtime_hours"]
    daily["pressure"] = daily["daily_avg_pressure"]

    daily["rolling_avg_energy_7d"] = _rolling_mean(daily, "daily_energy_kwh")
    daily["rolling_std_energy_7d"] = _rolling_std(daily, "daily_energy_kwh")
    daily["energy_delta_percent"] = _percent_delta(
        daily["daily_energy_kwh"], _previous_rolling_mean(daily, "daily_energy_kwh")
    )

    daily["rolling_avg_temperature_7d"] = _rolling_mean(daily, "daily_avg_temperature")
    daily["temperature_delta"] = (
        daily["daily_avg_temperature"] - _previous_rolling_mean(daily, "daily_avg_temperature")
    ).fillna(0.0)

    daily["rolling_avg_vibration_7d"] = _rolling_mean(daily, "daily_avg_vibration")
    daily["vibration_delta"] = (
        daily["daily_avg_vibration"] - _previous_rolling_mean(daily, "daily_avg_vibration")
    ).fillna(0.0)

    daily["runtime_delta_percent"] = _percent_delta(
        daily["daily_runtime_hours"], _previous_rolling_mean(daily, "daily_runtime_hours")
    )
    return daily


def _build_ticket_features(
    readings_daily: pd.DataFrame,
    maintenance_tickets: pd.DataFrame,
) -> pd.DataFrame:
    feature_grid = readings_daily[["asset_id", "feature_date"]].copy()
    tickets = maintenance_tickets.copy()
    tickets["feature_date"] = _to_utc_naive_datetime(tickets["created_at"]).dt.normalize()
    tickets["ticket_count"] = 1
    tickets["high_priority_ticket_count"] = tickets["priority"].map(
        lambda value: 1 if PRIORITY_VI_TO_SCORE[value] >= 3 else 0
    )

    ticket_daily = (
        tickets.groupby(["asset_id", "feature_date"], as_index=False)
        .agg(
            ticket_count=("ticket_count", "sum"),
            high_priority_ticket_count=("high_priority_ticket_count", "sum"),
        )
    )

    ticket_features = feature_grid.merge(ticket_daily, on=["asset_id", "feature_date"], how="left")
    ticket_features[["ticket_count", "high_priority_ticket_count"]] = ticket_features[
        ["ticket_count", "high_priority_ticket_count"]
    ].fillna(0)
    ticket_features = ticket_features.sort_values(["asset_id", "feature_date"])

    ticket_features["ticket_count_7d"] = _rolling_sum(ticket_features, "ticket_count", window=7)
    ticket_features["ticket_count_30d"] = _rolling_sum(ticket_features, "ticket_count", window=30)
    ticket_features["high_priority_ticket_count_30d"] = _rolling_sum(
        ticket_features, "high_priority_ticket_count", window=30
    )
    return ticket_features[
        [
            "asset_id",
            "feature_date",
            "ticket_count_7d",
            "ticket_count_30d",
            "high_priority_ticket_count_30d",
        ]
    ]


def _build_maintenance_features(
    readings_daily: pd.DataFrame,
    assets: pd.DataFrame,
    maintenance_logs: pd.DataFrame,
) -> pd.DataFrame:
    asset_lookup = assets.set_index("asset_id")
    logs = maintenance_logs.copy()
    logs["maintenance_date"] = pd.to_datetime(logs["maintenance_date"], errors="raise").dt.normalize()
    logs["next_maintenance_date"] = pd.to_datetime(
        logs["next_maintenance_date"], errors="raise"
    ).dt.normalize()
    logs_by_asset = {
        asset_id: group.sort_values(["maintenance_date", "log_id"])
        for asset_id, group in logs.groupby("asset_id")
    }

    rows: list[dict[str, object]] = []
    for row in readings_daily[["asset_id", "feature_date"]].itertuples(index=False):
        asset = asset_lookup.loc[row.asset_id]
        feature_date = row.feature_date

        asset_logs = logs_by_asset.get(row.asset_id)
        if asset_logs is None:
            raise ValueError(f"No maintenance history found for asset_id={row.asset_id}")
        eligible_logs = asset_logs[asset_logs["maintenance_date"] <= feature_date]
        if eligible_logs.empty:
            raise ValueError(
                "No point-in-time maintenance event found for "
                f"asset_id={row.asset_id} feature_date={feature_date.date()}"
            )
        latest_log = eligible_logs.iloc[-1]
        latest_maintenance_date = latest_log["maintenance_date"]
        next_maintenance_date = latest_log["next_maintenance_date"]
        days_since_last_maintenance = max(0, int((feature_date - latest_maintenance_date).days))
        days_overdue = max(0, int((feature_date - next_maintenance_date).days))

        rows.append(
            {
                "asset_id": row.asset_id,
                "feature_date": feature_date,
                "last_maintenance_date": latest_maintenance_date,
                "next_maintenance_date": next_maintenance_date,
                "days_since_last_maintenance": days_since_last_maintenance,
                "days_overdue": days_overdue,
                "asset_age_days": max(
                    0, int((feature_date - asset["installation_date"]).days)
                ),
                "criticality_score": int(asset["criticality_score"]),
            }
        )

    return pd.DataFrame(rows)


def _to_utc_naive_datetime(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="raise", utc=True).dt.tz_convert(None)


def _rolling_mean(frame: pd.DataFrame, column: str, window: int = 7) -> pd.Series:
    return frame.groupby("asset_id", group_keys=False)[column].apply(
        lambda series: series.rolling(window=window, min_periods=1).mean()
    )


def _previous_rolling_mean(frame: pd.DataFrame, column: str, window: int = 7) -> pd.Series:
    return frame.groupby("asset_id", group_keys=False)[column].apply(
        lambda series: series.rolling(window=window, min_periods=1).mean().shift(1)
    )


def _rolling_std(frame: pd.DataFrame, column: str, window: int = 7) -> pd.Series:
    return (
        frame.groupby("asset_id", group_keys=False)[column]
        .apply(lambda series: series.rolling(window=window, min_periods=1).std())
        .fillna(0.0)
    )


def _rolling_sum(frame: pd.DataFrame, column: str, window: int) -> pd.Series:
    return frame.groupby("asset_id", group_keys=False)[column].apply(
        lambda series: series.rolling(window=window, min_periods=1).sum()
    )


def _percent_delta(current: pd.Series, baseline: pd.Series) -> pd.Series:
    delta = np.where(baseline > 0, (current - baseline) / baseline * 100, 0.0)
    return pd.Series(delta, index=current.index).replace([np.inf, -np.inf], 0.0).fillna(0.0)


def main() -> None:
    """Build daily features from generated raw CSV files."""

    parser = argparse.ArgumentParser(description="Build daily asset-level maintenance features.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-path", type=Path, default=DEFAULT_FEATURE_OUTPUT_PATH)
    args = parser.parse_args()

    features = build_features_from_csv(input_dir=args.input_dir, output_path=args.output_path)
    print(f"Wrote {len(features):>7} rows: {args.output_path}")


if __name__ == "__main__":
    main()
