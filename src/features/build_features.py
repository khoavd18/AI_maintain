"""Daily asset-level feature engineering for maintenance analytics."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.config.value_mappings import (
    MAINTENANCE_STATUS_CODE_TO_VI,
    PRIORITY_VI_TO_SCORE,
    RISK_LEVEL_CODE_TO_VI,
    STATUS_CODE_TO_VI,
    criticality_score,
)
from src.ingestion.validation import validate_csv_dataset, validate_feature_overdue_days

DEFAULT_FEATURE_OUTPUT_PATH = Path("data/processed/asset_daily_features.csv")
DEFAULT_PREVENTIVE_STATUS_OUTPUT_PATH = Path(
    "data/processed/preventive_maintenance_status.csv"
)
DEFAULT_RECURRING_ISSUES_OUTPUT_PATH = Path("data/processed/recurring_issues.csv")
DEFAULT_MAINTENANCE_KPI_OUTPUT_PATH = Path("data/processed/maintenance_kpis.csv")

DUE_SOON_DAYS = 14
RECURRENCE_THRESHOLD = 3

FEATURE_COLUMNS = [
    "asset_id",
    "feature_date",
    "asset_name",
    "asset_type",
    "location",
    "criticality",
    "status",
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
    "unresolved_ticket_count",
    "recurring_issue_count",
    "follow_up_required_count",
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
            assets_prepared[
                [
                    "asset_id",
                    "asset_name",
                    "asset_type",
                    "location",
                    "criticality",
                    "status",
                ]
            ],
            on="asset_id",
            how="left",
        )
        .merge(ticket_features, on=["asset_id", "feature_date"], how="left")
        .merge(maintenance_features, on=["asset_id", "feature_date"], how="left")
    )

    count_columns = [
        "ticket_count_7d",
        "ticket_count_30d",
        "high_priority_ticket_count_30d",
        "unresolved_ticket_count",
        "recurring_issue_count",
        "follow_up_required_count",
    ]
    features[count_columns] = features[count_columns].fillna(0).astype(int)
    features = features[FEATURE_COLUMNS].sort_values(["asset_id", "feature_date"]).reset_index(drop=True)
    features["feature_date"] = features["feature_date"].dt.date.astype(str)
    for column in ["last_maintenance_date", "next_maintenance_date"]:
        features[column] = pd.to_datetime(features[column]).dt.date.astype(str)
    _validate_unique_asset_dates(features, "daily features")
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


def build_preventive_maintenance_status(
    assets: pd.DataFrame,
    as_of_date: object,
    due_soon_days: int = DUE_SOON_DAYS,
) -> pd.DataFrame:
    """Classify each asset's preventive maintenance status as of one date."""

    if due_soon_days < 0:
        raise ValueError("due_soon_days must be non-negative")

    analysis_date = pd.Timestamp(as_of_date).normalize()
    results = assets[
        ["asset_id", "last_maintenance_date", "next_maintenance_date"]
    ].copy()
    results["last_maintenance_date"] = pd.to_datetime(
        results["last_maintenance_date"], errors="raise"
    ).dt.normalize()
    results["next_maintenance_date"] = pd.to_datetime(
        results["next_maintenance_date"], errors="raise"
    ).dt.normalize()
    day_delta = (results["next_maintenance_date"] - analysis_date).dt.days
    results["days_until_due"] = day_delta.clip(lower=0).astype(int)
    results["days_overdue"] = (-day_delta).clip(lower=0).astype(int)
    results["maintenance_status"] = np.select(
        [day_delta < 0, day_delta <= due_soon_days],
        ["overdue", "due_soon"],
        default="not_due",
    )
    results["maintenance_status_display"] = results["maintenance_status"].map(
        MAINTENANCE_STATUS_CODE_TO_VI
    )
    results.insert(1, "as_of_date", analysis_date.date().isoformat())
    for column in ["last_maintenance_date", "next_maintenance_date"]:
        results[column] = results[column].dt.date.astype(str)
    return results.sort_values("asset_id").reset_index(drop=True)


def build_recurring_issue_analysis(
    maintenance_tickets: pd.DataFrame,
    recurrence_threshold: int = RECURRENCE_THRESHOLD,
) -> pd.DataFrame:
    """Group ticket history into deterministic asset/category recurrence results."""

    if recurrence_threshold < 2:
        raise ValueError("recurrence_threshold must be at least 2")

    tickets = maintenance_tickets.copy()
    tickets["created_at"] = _to_utc_naive_datetime(tickets["created_at"])
    tickets["is_resolved"] = tickets["status"].eq(STATUS_CODE_TO_VI["resolved"])
    results = (
        tickets.groupby(["asset_id", "failure_category"], as_index=False)
        .agg(
            occurrence_count=("ticket_id", "count"),
            first_occurrence=("created_at", "min"),
            last_occurrence=("created_at", "max"),
            resolved_count=("is_resolved", "sum"),
        )
        .sort_values(["asset_id", "failure_category"])
        .reset_index(drop=True)
    )
    results["resolved_count"] = results["resolved_count"].astype(int)
    results["unresolved_count"] = (
        results["occurrence_count"] - results["resolved_count"]
    ).astype(int)
    results["recurrence_flag"] = results["occurrence_count"].ge(
        recurrence_threshold
    )
    results["recurrence_threshold"] = recurrence_threshold
    for column in ["first_occurrence", "last_occurrence"]:
        results[column] = results[column].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return results[
        [
            "asset_id",
            "failure_category",
            "occurrence_count",
            "first_occurrence",
            "last_occurrence",
            "resolved_count",
            "unresolved_count",
            "recurrence_flag",
            "recurrence_threshold",
        ]
    ]


def calculate_maintenance_kpis(
    maintenance_tickets: pd.DataFrame,
    maintenance_logs: pd.DataFrame,
    preventive_status: pd.DataFrame,
    recurring_issues: pd.DataFrame,
    risk_scores: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate supported descriptive maintenance KPIs from batch data."""

    tickets = maintenance_tickets.copy()
    resolved_mask = tickets["status"].eq(STATUS_CODE_TO_VI["resolved"])
    total_tickets = len(tickets)
    resolved_tickets = int(resolved_mask.sum())
    resolution_hours = (
        _to_utc_naive_datetime(tickets.loc[resolved_mask, "resolved_at"])
        - _to_utc_naive_datetime(tickets.loc[resolved_mask, "created_at"])
    ).dt.total_seconds() / 3600

    latest_risks = _latest_risk_rows(risk_scores)
    if "risk_level_code" in latest_risks.columns:
        high_risk_mask = latest_risks["risk_level_code"].isin(["high", "critical"])
    else:
        high_risk_mask = latest_risks["risk_level"].isin(
            [RISK_LEVEL_CODE_TO_VI["high"], RISK_LEVEL_CODE_TO_VI["critical"]]
        )

    kpis = {
        "as_of_date": str(preventive_status["as_of_date"].iloc[0]),
        "total_tickets": total_tickets,
        "open_tickets": total_tickets - resolved_tickets,
        "resolved_tickets": resolved_tickets,
        "ticket_resolution_rate_percent": round(
            resolved_tickets / total_tickets * 100 if total_tickets else 0.0,
            2,
        ),
        "average_resolution_time_hours": round(
            float(resolution_hours.mean()) if not resolution_hours.empty else 0.0,
            2,
        ),
        "median_resolution_time_hours": round(
            float(resolution_hours.median()) if not resolution_hours.empty else 0.0,
            2,
        ),
        "overdue_asset_count": int(
            preventive_status["maintenance_status"].eq("overdue").sum()
        ),
        "due_soon_asset_count": int(
            preventive_status["maintenance_status"].eq("due_soon").sum()
        ),
        "recurring_issue_count": int(recurring_issues["recurrence_flag"].sum()),
        "follow_up_required_maintenance_count": int(
            _coerce_boolean_series(maintenance_logs["follow_up_required"]).sum()
        ),
        "high_critical_risk_asset_count": int(high_risk_mask.sum()),
    }
    return pd.DataFrame([kpis])


def build_maintenance_analytics_from_csv(
    input_dir: Path = Path("data/raw"),
    risk_path: Path = Path("data/processed/risk_scores.csv"),
    processed_dir: Path = Path("data/processed"),
) -> dict[str, pd.DataFrame]:
    """Build and save preventive, recurrence, and KPI analytics outputs."""

    frames = validate_csv_dataset(input_dir)
    if not risk_path.exists():
        raise FileNotFoundError(f"Risk file not found: {risk_path}")
    risks = pd.read_csv(risk_path)
    as_of_date = _observation_end(frames["sensor_readings"])
    preventive = build_preventive_maintenance_status(frames["assets"], as_of_date)
    recurring = build_recurring_issue_analysis(frames["maintenance_tickets"])
    kpis = calculate_maintenance_kpis(
        maintenance_tickets=frames["maintenance_tickets"],
        maintenance_logs=frames["maintenance_logs"],
        preventive_status=preventive,
        recurring_issues=recurring,
        risk_scores=risks,
    )

    outputs = {
        "preventive_maintenance_status": preventive,
        "recurring_issues": recurring,
        "maintenance_kpis": kpis,
    }
    filenames = {
        "preventive_maintenance_status": DEFAULT_PREVENTIVE_STATUS_OUTPUT_PATH.name,
        "recurring_issues": DEFAULT_RECURRING_ISSUES_OUTPUT_PATH.name,
        "maintenance_kpis": DEFAULT_MAINTENANCE_KPI_OUTPUT_PATH.name,
    }
    processed_dir.mkdir(parents=True, exist_ok=True)
    for output_name, frame in outputs.items():
        frame.to_csv(processed_dir / filenames[output_name], index=False)
    return outputs


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
    tickets["created_timestamp"] = _to_utc_naive_datetime(tickets["created_at"])
    tickets["resolved_timestamp"] = pd.to_datetime(
        tickets["resolved_at"].replace("", pd.NA), errors="coerce", utc=True
    ).dt.tz_convert(None)
    tickets["feature_date"] = tickets["created_timestamp"].dt.normalize()
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
    point_in_time_counts = _build_point_in_time_ticket_counts(feature_grid, tickets)
    ticket_features = ticket_features.merge(
        point_in_time_counts,
        on=["asset_id", "feature_date"],
        how="left",
    )
    return ticket_features[
        [
            "asset_id",
            "feature_date",
            "ticket_count_7d",
            "ticket_count_30d",
            "high_priority_ticket_count_30d",
            "unresolved_ticket_count",
            "recurring_issue_count",
        ]
    ]


def _build_point_in_time_ticket_counts(
    feature_grid: pd.DataFrame,
    tickets: pd.DataFrame,
) -> pd.DataFrame:
    tickets_by_asset = {
        asset_id: group.sort_values(["created_timestamp", "ticket_id"])
        for asset_id, group in tickets.groupby("asset_id")
    }
    rows: list[dict[str, object]] = []
    for row in feature_grid.itertuples(index=False):
        asset_tickets = tickets_by_asset.get(row.asset_id)
        if asset_tickets is None:
            eligible = tickets.iloc[0:0]
        else:
            eligible = asset_tickets[
                asset_tickets["created_timestamp"].dt.normalize() <= row.feature_date
            ]
        unresolved = eligible[
            eligible["resolved_timestamp"].isna()
            | (eligible["resolved_timestamp"].dt.normalize() > row.feature_date)
        ]
        category_counts = eligible.groupby("failure_category").size()
        rows.append(
            {
                "asset_id": row.asset_id,
                "feature_date": row.feature_date,
                "unresolved_ticket_count": len(unresolved),
                "recurring_issue_count": int(
                    category_counts.ge(RECURRENCE_THRESHOLD).sum()
                ),
            }
        )
    return pd.DataFrame(rows)


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
        follow_up_required_count = int(
            _coerce_boolean_series(eligible_logs["follow_up_required"]).sum()
        )

        rows.append(
            {
                "asset_id": row.asset_id,
                "feature_date": feature_date,
                "last_maintenance_date": latest_maintenance_date,
                "next_maintenance_date": next_maintenance_date,
                "days_since_last_maintenance": days_since_last_maintenance,
                "days_overdue": days_overdue,
                "follow_up_required_count": follow_up_required_count,
                "asset_age_days": max(
                    0, int((feature_date - asset["installation_date"]).days)
                ),
                "criticality_score": int(asset["criticality_score"]),
            }
        )

    return pd.DataFrame(rows)


def _to_utc_naive_datetime(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="raise", utc=True).dt.tz_convert(None)


def _coerce_boolean_series(values: pd.Series) -> pd.Series:
    normalized = values.astype(str).str.strip().str.lower()
    invalid = ~normalized.isin(["true", "false"])
    if invalid.any():
        raise ValueError(f"Invalid boolean value: {values.loc[invalid].iloc[0]!r}")
    return normalized.eq("true")


def _latest_risk_rows(risk_scores: pd.DataFrame) -> pd.DataFrame:
    date_column = "feature_date" if "feature_date" in risk_scores.columns else "date"
    if date_column not in risk_scores.columns:
        raise ValueError("Risk scores require a feature_date or date column")
    risks = risk_scores.copy()
    risks[date_column] = pd.to_datetime(risks[date_column], errors="raise")
    latest_date = risks[date_column].max()
    latest = risks[risks[date_column] == latest_date].copy()
    if latest["asset_id"].duplicated().any():
        raise ValueError("Latest risk scores contain duplicate asset rows")
    return latest


def _observation_end(sensor_readings: pd.DataFrame) -> pd.Timestamp:
    return _to_utc_naive_datetime(sensor_readings["timestamp"]).max().normalize()


def _validate_unique_asset_dates(frame: pd.DataFrame, label: str) -> None:
    duplicate = frame.duplicated(["asset_id", "feature_date"], keep=False)
    if duplicate.any():
        row = frame.loc[duplicate].iloc[0]
        raise ValueError(
            f"{label} contains duplicate asset/date row: "
            f"asset_id={row['asset_id']} feature_date={row['feature_date']}"
        )


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
    """Build daily features or focused maintenance analytics from raw CSV files."""

    parser = argparse.ArgumentParser(description="Build focused maintenance analytics.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-path", type=Path, default=DEFAULT_FEATURE_OUTPUT_PATH)
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--risk-path",
        type=Path,
        default=Path("data/processed/risk_scores.csv"),
    )
    parser.add_argument(
        "--analysis",
        choices=["features", "preventive", "recurring", "kpis", "maintenance"],
        default="features",
    )
    args = parser.parse_args()

    if args.analysis == "features":
        features = build_features_from_csv(
            input_dir=args.input_dir,
            output_path=args.output_path,
        )
        print(f"Wrote {len(features):>7} rows: {args.output_path}")
        return

    frames = validate_csv_dataset(args.input_dir)
    as_of_date = _observation_end(frames["sensor_readings"])
    preventive = build_preventive_maintenance_status(frames["assets"], as_of_date)
    recurring = build_recurring_issue_analysis(frames["maintenance_tickets"])
    args.processed_dir.mkdir(parents=True, exist_ok=True)

    if args.analysis == "preventive":
        path = args.processed_dir / DEFAULT_PREVENTIVE_STATUS_OUTPUT_PATH.name
        preventive.to_csv(path, index=False)
        print(f"Wrote {len(preventive):>7} rows: {path}")
        return
    if args.analysis == "recurring":
        path = args.processed_dir / DEFAULT_RECURRING_ISSUES_OUTPUT_PATH.name
        recurring.to_csv(path, index=False)
        print(f"Wrote {len(recurring):>7} rows: {path}")
        return

    if not args.risk_path.exists():
        raise FileNotFoundError(f"Risk file not found: {args.risk_path}")
    kpis = calculate_maintenance_kpis(
        maintenance_tickets=frames["maintenance_tickets"],
        maintenance_logs=frames["maintenance_logs"],
        preventive_status=preventive,
        recurring_issues=recurring,
        risk_scores=pd.read_csv(args.risk_path),
    )
    if args.analysis == "kpis":
        path = args.processed_dir / DEFAULT_MAINTENANCE_KPI_OUTPUT_PATH.name
        kpis.to_csv(path, index=False)
        print(f"Wrote {len(kpis):>7} rows: {path}")
        return

    outputs = {
        DEFAULT_PREVENTIVE_STATUS_OUTPUT_PATH.name: preventive,
        DEFAULT_RECURRING_ISSUES_OUTPUT_PATH.name: recurring,
        DEFAULT_MAINTENANCE_KPI_OUTPUT_PATH.name: kpis,
    }
    for filename, frame in outputs.items():
        path = args.processed_dir / filename
        frame.to_csv(path, index=False)
        print(f"Wrote {len(frame):>7} rows: {path}")


if __name__ == "__main__":
    main()
