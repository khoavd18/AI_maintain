"""Streamlit dashboard for the AI Maintenance Copilot."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.dashboard.api_client import ApiClientError, MaintenanceApiClient, get_api_base_url
from src.dashboard.api_client import records_to_dataframe

ALL_OPTION = "All"

RISK_COLUMNS = [
    "asset_id",
    "date",
    "asset_name",
    "asset_type",
    "location",
    "final_risk_score",
    "risk_level",
    "main_reasons",
    "recommended_action",
]
ANOMALY_COLUMNS = [
    "asset_id",
    "date",
    "asset_type",
    "location",
    "anomaly_score",
    "is_anomaly",
    "anomaly_type",
    "anomaly_reasons",
]
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
    "days_overdue",
    "ticket_count_7d",
    "ticket_count_30d",
]


def main() -> None:
    """Render the dashboard."""

    st.set_page_config(page_title="AI Maintenance Copilot", layout="wide")
    st.title("AI Maintenance Copilot")
    st.caption("Predictive maintenance intelligence dashboard powered by the FastAPI backend.")

    api_base_url = _render_sidebar()
    client = MaintenanceApiClient(api_base_url)

    try:
        client.health()
    except ApiClientError as exc:
        _render_connection_error(api_base_url, exc)
        return

    st.sidebar.success("API connected")

    try:
        summary = client.get_summary()
        latest_date = _as_text(summary.get("latest_date"))
        latest_risks = records_to_dataframe(
            client.list_risks(date=latest_date, limit=1000) if latest_date else client.list_risks()
        )
    except ApiClientError as exc:
        _render_data_error(exc)
        return

    tabs = st.tabs(
        [
            "Overview",
            "Asset Risk Monitoring",
            "Anomaly Monitoring",
            "Asset Context",
            "Demo Story",
            "Maintenance Copilot",
        ]
    )

    with tabs[0]:
        render_overview(client, summary, latest_risks)
    with tabs[1]:
        render_asset_risk_monitoring(client, summary, latest_risks)
    with tabs[2]:
        render_anomaly_monitoring(client)
    with tabs[3]:
        render_asset_context(client, latest_risks)
    with tabs[4]:
        render_demo_story(client, summary)
    with tabs[5]:
        render_maintenance_copilot(client, latest_risks)


def render_overview(
    client: MaintenanceApiClient,
    summary: dict[str, Any],
    latest_risks: pd.DataFrame,
) -> None:
    """Render overall maintenance health and top risky assets."""

    st.subheader("Overview")
    first_row = st.columns(4)
    first_row[0].metric("total_assets", _metric_value(summary.get("total_assets")))
    first_row[1].metric("total_records", _metric_value(summary.get("total_records")))
    first_row[2].metric("high_risk_count", _metric_value(summary.get("high_risk_count")))
    first_row[3].metric("urgent_risk_count", _metric_value(summary.get("urgent_risk_count")))

    second_row = st.columns(3)
    second_row[0].metric("anomaly_count", _metric_value(summary.get("anomaly_count")))
    second_row[1].metric("latest_date", _metric_value(summary.get("latest_date")))
    second_row[2].metric(
        "average_risk_score",
        _metric_value(summary.get("average_risk_score"), decimals=2),
    )

    st.divider()
    table_col, chart_col = st.columns([2, 1])

    with table_col:
        st.subheader("Top 10 Risky Assets")
        try:
            top_risks = records_to_dataframe(
                client.list_top_risks(limit=10, date=_as_text(summary.get("latest_date")))
            )
        except ApiClientError as exc:
            st.error(str(exc))
        else:
            _dataframe(top_risks, RISK_COLUMNS)

    with chart_col:
        st.subheader("Risk Level Distribution")
        if latest_risks.empty or "risk_level" not in latest_risks.columns:
            st.info("Risk distribution is not available from the current API response.")
        else:
            distribution = latest_risks["risk_level"].value_counts().rename("records")
            st.bar_chart(distribution)


def render_asset_risk_monitoring(
    client: MaintenanceApiClient,
    summary: dict[str, Any],
    latest_risks: pd.DataFrame,
) -> None:
    """Render filterable asset risk monitoring."""

    st.subheader("Asset Risk Monitoring")
    latest_date = _as_text(summary.get("latest_date"))
    if latest_date:
        st.caption(f"Showing latest asset-level risk records for {latest_date}.")

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
    risk_level = filter_col1.selectbox(
        "risk_level",
        _option_values(latest_risks, "risk_level"),
        key="risk_monitoring_risk_level",
    )
    asset_type = filter_col2.selectbox(
        "asset_type",
        _option_values(latest_risks, "asset_type"),
        key="risk_monitoring_asset_type",
    )
    location = filter_col3.selectbox(
        "location",
        _option_values(latest_risks, "location"),
        key="risk_monitoring_location",
    )
    limit = filter_col4.number_input(
        "limit",
        min_value=1,
        max_value=1000,
        value=50,
        step=10,
        key="risk_monitoring_limit",
    )

    try:
        risk_df = records_to_dataframe(
            client.list_risks(
                risk_level=_selected_value(risk_level),
                asset_type=_selected_value(asset_type),
                location=_selected_value(location),
                date=latest_date,
                limit=int(limit),
            )
        )
    except ApiClientError as exc:
        st.error(str(exc))
        return

    risk_df = _sort_dataframe(risk_df, "final_risk_score")
    _dataframe(risk_df, RISK_COLUMNS)

    if risk_df.empty or "asset_id" not in risk_df.columns:
        st.info("No assets match the selected filters.")
        return

    selected_asset_id = st.selectbox(
        "Select asset_id",
        risk_df["asset_id"].astype(str).tolist(),
        key="risk_monitoring_selected_asset_id",
    )
    selected_row = risk_df[risk_df["asset_id"].astype(str) == selected_asset_id].iloc[0].to_dict()
    _render_asset_detail(selected_row)

    try:
        history_df = records_to_dataframe(client.get_asset_risk_history(selected_asset_id))
    except ApiClientError:
        history_df = pd.DataFrame()
    if not history_df.empty and {"date", "final_risk_score"}.issubset(history_df.columns):
        st.subheader("Risk Trend")
        trend = history_df.sort_values("date").set_index("date")[["final_risk_score"]]
        st.line_chart(trend)


def render_anomaly_monitoring(client: MaintenanceApiClient) -> None:
    """Render anomaly monitoring with filters and simple charts."""

    st.subheader("Anomaly Monitoring")

    try:
        option_source = records_to_dataframe(client.list_anomalies(only_anomalies=False, limit=1000))
    except ApiClientError as exc:
        st.error(str(exc))
        return

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
    anomaly_type = filter_col1.selectbox(
        "anomaly_type",
        _option_values(option_source, "anomaly_type"),
        key="anomaly_monitoring_anomaly_type",
    )
    asset_type = filter_col2.selectbox(
        "asset_type",
        _option_values(option_source, "asset_type"),
        key="anomaly_monitoring_asset_type",
    )
    only_anomalies = filter_col3.checkbox(
        "only_anomalies",
        value=True,
        key="anomaly_monitoring_only_anomalies",
    )
    limit = filter_col4.number_input(
        "limit",
        min_value=1,
        max_value=1000,
        value=100,
        step=25,
        key="anomaly_limit",
    )

    try:
        anomaly_df = records_to_dataframe(
            client.list_anomalies(
                asset_type=_selected_value(asset_type),
                anomaly_type=_selected_value(anomaly_type),
                only_anomalies=only_anomalies,
                limit=int(limit),
            )
        )
    except ApiClientError as exc:
        st.error(str(exc))
        return

    anomaly_df = _sort_dataframe(anomaly_df, "anomaly_score")
    _dataframe(anomaly_df, ANOMALY_COLUMNS)

    if anomaly_df.empty:
        st.info("No anomaly records match the selected filters.")
        return

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.subheader("Anomaly Type Counts")
        if "anomaly_type" in anomaly_df.columns:
            st.bar_chart(anomaly_df["anomaly_type"].value_counts().rename("records"))
    with chart_col2:
        st.subheader("Average Score by Asset Type")
        if {"asset_type", "anomaly_score"}.issubset(anomaly_df.columns):
            score_by_type = anomaly_df.groupby("asset_type")["anomaly_score"].mean()
            st.bar_chart(score_by_type.sort_values(ascending=False))


def render_asset_context(client: MaintenanceApiClient, latest_risks: pd.DataFrame) -> None:
    """Render combined asset context for inspection and future RAG use."""

    st.subheader("Asset Context")
    st.caption(
        "This context bundle is the handoff point for a future RAG Copilot: asset identity, "
        "latest risk, recent anomalies, feature history, and recommendation."
    )

    asset_ids = _asset_id_options(latest_risks)
    selected_asset_id = (
        st.selectbox("Select asset_id", asset_ids, key="asset_context_selected_asset_id")
        if asset_ids
        else ""
    )
    typed_asset_id = st.text_input(
        "Or enter asset_id",
        value=selected_asset_id,
        key="asset_context_typed_asset_id",
    )
    asset_id = typed_asset_id.strip() or selected_asset_id

    if not asset_id:
        st.info("Select or enter an asset_id to load context.")
        return

    try:
        context = client.get_asset_context(asset_id)
    except ApiClientError as exc:
        st.error(str(exc))
        return

    latest_risk = records_to_dataframe(context.get("latest_risk"))
    recent_anomalies = records_to_dataframe(context.get("recent_anomalies"))
    recent_features = records_to_dataframe(context.get("recent_features"))

    st.subheader("Latest Recommendation")
    st.info(_as_text(context.get("latest_recommendation")) or "No recommendation available.")

    st.subheader("Latest Risk Row")
    _dataframe(latest_risk, RISK_COLUMNS)

    st.subheader("Recent Anomalies")
    _dataframe(_sort_dataframe(recent_anomalies, "date"), ANOMALY_COLUMNS)

    st.subheader("Recent Feature Records")
    _dataframe(_sort_dataframe(recent_features, "feature_date"), FEATURE_COLUMNS)

    st.info(
        "Future RAG Copilot retrieval can use this same asset context to fetch SOPs, "
        "inspection checklists, and historical technician notes."
    )


def render_demo_story(client: MaintenanceApiClient, summary: dict[str, Any]) -> None:
    """Render a short guided portfolio demo narrative."""

    st.subheader("Demo Story")

    try:
        top_risks = client.list_top_risks(limit=1, date=_as_text(summary.get("latest_date")))
    except ApiClientError as exc:
        st.error(str(exc))
        return

    top_asset = top_risks[0] if top_risks else {}
    asset_id = _as_text(top_asset.get("asset_id")) or "selected asset"
    asset_name = _as_text(top_asset.get("asset_name")) or asset_id
    risk_level = _as_text(top_asset.get("risk_level")) or "unknown"
    recommendation = _as_text(top_asset.get("recommended_action")) or "No recommendation available."

    st.markdown(
        f"""
1. Manager checks `/summary` and sees **{summary.get("high_risk_count", 0)}** high-risk assets,
   **{summary.get("urgent_risk_count", 0)}** urgent assets, and
   **{summary.get("anomaly_count", 0)}** current anomalies.
2. Manager opens the top-risk table and identifies **{asset_name}** (`{asset_id}`) with risk level
   **{risk_level}**.
3. Manager reviews the Vietnamese risk reasons and recommendation from `/assets/risk/top`.
4. Technician inspects the asset using the suggested action: **{recommendation}**
5. Future phase: RAG Copilot retrieves SOP and checklist documents for the same asset context.
"""
    )

    if top_asset:
        st.subheader("Top Risk Asset")
        _dataframe(records_to_dataframe(top_asset), RISK_COLUMNS)


def render_maintenance_copilot(client: MaintenanceApiClient, latest_risks: pd.DataFrame) -> None:
    """Render the RAG Maintenance Copilot tab."""

    st.subheader("Maintenance Copilot")
    st.caption(
        "Ask Vietnamese technician or manager questions grounded in asset context and "
        "indexed SOP/checklist documents."
    )

    asset_ids = _asset_id_options(latest_risks)
    asset_options = [""] + asset_ids
    selected_asset_id = st.selectbox(
        "Optional asset_id",
        asset_options,
        key="copilot_selected_asset_id",
    )
    typed_asset_id = st.text_input(
        "Or enter asset_id manually",
        value=selected_asset_id,
        key="copilot_typed_asset_id",
    )
    asset_id = typed_asset_id.strip() or None
    top_k = st.number_input("top_k", min_value=1, max_value=20, value=5, step=1, key="copilot_top_k")
    question = st.text_area(
        "Question",
        value="Vì sao thiết bị này đang rủi ro cao và kỹ thuật viên nên làm gì tiếp theo?",
        height=110,
        key="copilot_question",
    )

    if not st.button("Ask Copilot", key="copilot_ask_button"):
        st.info("Run `make index-documents` first so Qdrant has SOP/checklist chunks.")
        return

    if not question.strip():
        st.warning("Please enter a question.")
        return

    try:
        response = client.ask_copilot(
            question=question.strip(),
            asset_id=asset_id,
            top_k=int(top_k),
        )
    except ApiClientError as exc:
        st.error(str(exc))
        return

    st.subheader("Answer")
    st.markdown(response.get("answer") or "No answer returned.")

    sources = records_to_dataframe(response.get("sources"))
    st.subheader("Sources")
    _dataframe(sources, ["doc_id", "title", "doc_type", "asset_type", "source", "score"])

    retrieved_chunks = records_to_dataframe(response.get("retrieved_chunks"))
    with st.expander("Retrieved Chunks", expanded=False):
        _dataframe(
            retrieved_chunks,
            ["chunk_id", "title", "doc_type", "asset_type", "score", "text"],
        )


def _render_sidebar() -> str:
    st.sidebar.header("Configuration")
    return st.sidebar.text_input(
        "API_BASE_URL",
        value=get_api_base_url(),
        key="sidebar_api_base_url",
    ).strip()


def _render_connection_error(api_base_url: str, error: ApiClientError) -> None:
    st.error(f"Could not connect to FastAPI at {api_base_url}.")
    st.caption(str(error))
    st.code("make run-api", language="bash")


def _render_data_error(error: ApiClientError) -> None:
    st.error("The API is reachable, but processed maintenance data could not be loaded.")
    st.caption(str(error))


def _render_asset_detail(row: dict[str, Any]) -> None:
    st.subheader("Asset Detail")
    metric_cols = st.columns(4)
    metric_cols[0].metric("asset_name", _metric_value(row.get("asset_name")))
    metric_cols[1].metric("asset_type", _metric_value(row.get("asset_type")))
    metric_cols[2].metric("location", _metric_value(row.get("location")))
    metric_cols[3].metric(
        "final_risk_score",
        _metric_value(row.get("final_risk_score"), decimals=2),
    )

    st.metric("risk_level", _metric_value(row.get("risk_level")))
    st.subheader("main_reasons")
    st.write(_as_text(row.get("main_reasons")) or "-")
    st.subheader("recommended_action")
    st.info(_as_text(row.get("recommended_action")) or "-")


def _dataframe(frame: pd.DataFrame, preferred_columns: list[str]) -> None:
    if frame.empty:
        st.info("No records to display.")
        return
    columns = [column for column in preferred_columns if column in frame.columns]
    remaining = [column for column in frame.columns if column not in columns]
    st.dataframe(frame[columns + remaining], width="stretch", hide_index=True)


def _option_values(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return [ALL_OPTION]
    values = sorted(frame[column].dropna().astype(str).unique().tolist())
    return [ALL_OPTION, *values]


def _selected_value(value: str) -> str | None:
    return None if value == ALL_OPTION else value


def _asset_id_options(frame: pd.DataFrame) -> list[str]:
    if frame.empty or "asset_id" not in frame.columns:
        return []
    return sorted(frame["asset_id"].dropna().astype(str).unique().tolist())


def _sort_dataframe(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if frame.empty or column not in frame.columns:
        return frame
    return frame.sort_values(column, ascending=False)


def _metric_value(value: Any, decimals: int | None = None) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.{decimals or 0}f}"
    return str(value)


def _as_text(value: Any) -> str:
    return "" if value is None else str(value)


if __name__ == "__main__":
    main()
