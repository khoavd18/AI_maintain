"""Streamlit manager dashboard for the focused AI Maintenance Copilot MVP."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.dashboard.api_client import (
    ApiClientError,
    MaintenanceApiClient,
    get_api_base_url,
    records_to_dataframe,
)

ALL_OPTION = "Tất cả"

ASSET_TABLE_COLUMNS = [
    "asset_id",
    "asset_name",
    "asset_type",
    "location",
    "criticality",
    "status",
    "risk_score",
    "risk_level",
    "maintenance_status_display",
    "days_overdue",
    "unresolved_ticket_count",
]
RISK_COLUMNS = [
    "date",
    "risk_score",
    "risk_level",
    "contributing_factors",
    "recommended_action",
]
ANOMALY_COLUMNS = [
    "asset_id",
    "date",
    "asset_type",
    "anomaly_score",
    "anomalous_metrics",
    "anomaly_type",
    "contributing_signals",
]
TICKET_COLUMNS = [
    "ticket_id",
    "created_at",
    "issue_description",
    "failure_category",
    "priority",
    "status",
    "resolved_at",
    "technician_id",
]
LOG_COLUMNS = [
    "log_id",
    "maintenance_date",
    "maintenance_type",
    "inspection_result",
    "actions_taken",
    "maintenance_result",
    "follow_up_required",
    "next_maintenance_date",
]
RECURRING_COLUMNS = [
    "asset_id",
    "failure_category",
    "occurrence_count",
    "first_occurrence",
    "last_occurrence",
    "resolved_count",
    "unresolved_count",
    "recurrence_flag",
]


def main() -> None:
    """Render the four-view manager workflow."""

    st.set_page_config(page_title="AI Maintenance Copilot", layout="wide")
    st.title("AI Maintenance Copilot")
    st.caption("Nền tảng hỗ trợ quyết định bảo trì theo batch trên dữ liệu synthetic tiếng Việt.")

    api_base_url = _render_sidebar()
    client = MaintenanceApiClient(api_base_url)
    try:
        with st.spinner("Đang kết nối FastAPI..."):
            health = client.health()
    except ApiClientError as exc:
        _render_connection_error(api_base_url, exc)
        return

    if health.get("status") != "ok":
        st.warning(
            "API đang hoạt động nhưng một số CSV nguồn hoặc analytics output chưa sẵn sàng. "
            "Hãy chạy lại batch pipeline."
        )
    else:
        st.sidebar.success("Đã kết nối API")

    try:
        with st.spinner("Đang tải danh mục thiết bị..."):
            assets = records_to_dataframe(client.list_assets())
    except ApiClientError as exc:
        _render_data_error(exc)
        return

    _render_safety_notice()
    tabs = st.tabs(
        [
            "Tổng quan",
            "Thiết bị và rủi ro",
            "Bất thường và lỗi lặp lại",
            "Trợ lý bảo trì",
        ]
    )
    with tabs[0]:
        render_overview(client, assets)
    with tabs[1]:
        render_assets_and_risk(client, assets)
    with tabs[2]:
        render_anomalies_and_recurring(client)
    with tabs[3]:
        render_maintenance_copilot(client, assets)


def render_overview(client: MaintenanceApiClient, assets: pd.DataFrame) -> None:
    """Render manager KPIs, distributions, and top priorities."""

    st.subheader("Tổng quan bảo trì")
    try:
        with st.spinner("Đang tải KPI và trạng thái bảo trì..."):
            kpis = client.get_maintenance_kpis()
            tickets = records_to_dataframe(client.list_tickets(limit=1000))
            preventive = records_to_dataframe(client.list_preventive_maintenance())
            recurring = records_to_dataframe(
                client.list_recurring_issues(recurrence_flag=True)
            )
    except ApiClientError as exc:
        st.error(str(exc))
        return

    first_row = st.columns(4)
    first_row[0].metric("Tổng thiết bị", _metric_value(len(assets)))
    first_row[1].metric("Ticket đang mở", _metric_value(kpis.get("open_tickets")))
    first_row[2].metric(
        "Tỷ lệ xử lý ticket",
        _format_percent(kpis.get("ticket_resolution_rate_percent")),
    )
    first_row[3].metric(
        "Thời gian xử lý trung bình",
        _format_hours(kpis.get("average_resolution_time_hours")),
    )

    second_row = st.columns(4)
    second_row[0].metric("Thiết bị quá hạn", _metric_value(kpis.get("overdue_asset_count")))
    second_row[1].metric(
        "High/Critical mới nhất",
        _metric_value(kpis.get("high_critical_risk_asset_count")),
    )
    second_row[2].metric("Nhóm lỗi lặp lại", _metric_value(len(recurring)))
    second_row[3].metric(
        "Log cần follow-up",
        _metric_value(kpis.get("follow_up_required_maintenance_count")),
    )

    st.subheader("Phân bố trạng thái")
    chart_columns = st.columns(3)
    _render_distribution_chart(chart_columns[0], tickets, "status", "Trạng thái ticket")
    _render_distribution_chart(chart_columns[1], assets, "risk_level", "Risk Level mới nhất")
    _render_distribution_chart(
        chart_columns[2],
        preventive,
        "maintenance_status_display",
        "Preventive maintenance",
    )

    st.subheader("Thiết bị cần ưu tiên")
    top_assets = _sort_dataframe(assets, "risk_score").head(10)
    _dataframe(top_assets, ASSET_TABLE_COLUMNS)
    st.caption(
        "Các số liệu trên là facts từ synthetic CSV và batch analytics. Risk Score chỉ dùng để "
        "xếp thứ tự xem xét."
    )


def render_assets_and_risk(client: MaintenanceApiClient, assets: pd.DataFrame) -> None:
    """Render filterable assets and one consolidated asset inspection workflow."""

    st.subheader("Thiết bị và rủi ro")
    filter_row = st.columns(4)
    asset_type = filter_row[0].selectbox(
        "Loại thiết bị", _option_values(assets, "asset_type"), key="assets_type"
    )
    location = filter_row[1].selectbox(
        "Vị trí", _option_values(assets, "location"), key="assets_location"
    )
    criticality = filter_row[2].selectbox(
        "Criticality", _option_values(assets, "criticality"), key="assets_criticality"
    )
    asset_status = filter_row[3].selectbox(
        "Trạng thái thiết bị", _option_values(assets, "status"), key="assets_status"
    )

    try:
        with st.spinner("Đang lọc danh mục thiết bị..."):
            filtered = records_to_dataframe(
                client.list_assets(
                    asset_type=_selected_value(asset_type),
                    location=_selected_value(location),
                    criticality=_selected_value(criticality),
                    status=_selected_value(asset_status),
                )
            )
    except ApiClientError as exc:
        st.error(str(exc))
        return

    secondary_filters = st.columns(2)
    risk_level = secondary_filters[0].selectbox(
        "Risk Level",
        _option_values(filtered, "risk_level"),
        key="assets_risk_level",
    )
    maintenance_status = secondary_filters[1].selectbox(
        "Tình trạng bảo trì",
        _option_values(filtered, "maintenance_status_display"),
        key="assets_maintenance_status",
    )
    filtered = _filter_frame(filtered, "risk_level", _selected_value(risk_level))
    filtered = _filter_frame(
        filtered,
        "maintenance_status_display",
        _selected_value(maintenance_status),
    )
    filtered = _sort_dataframe(filtered, "risk_score")
    _dataframe(filtered, ASSET_TABLE_COLUMNS)
    if filtered.empty:
        st.info("Không có thiết bị phù hợp với bộ lọc.")
        return

    selected_asset_id = st.selectbox(
        "Chọn thiết bị để xem chi tiết",
        filtered["asset_id"].astype(str).tolist(),
        key="selected_asset_details",
    )
    try:
        with st.spinner(f"Đang tải lịch sử {selected_asset_id}..."):
            details = client.get_asset_details(selected_asset_id, limit=10)
    except ApiClientError as exc:
        st.error(str(exc))
        return

    _render_asset_details(details)


def render_anomalies_and_recurring(client: MaintenanceApiClient) -> None:
    """Render anomaly evidence and deterministic recurring ticket groups."""

    st.subheader("Bất thường và lỗi lặp lại")
    try:
        with st.spinner("Đang tải anomaly và recurring issues..."):
            anomalies = records_to_dataframe(
                client.list_anomalies(only_anomalies=True, limit=1000)
            )
            recurring = records_to_dataframe(client.list_recurring_issues())
    except ApiClientError as exc:
        st.error(str(exc))
        return

    st.markdown("#### Anomaly records")
    anomaly_filters = st.columns(2)
    anomaly_type = anomaly_filters[0].selectbox(
        "Loại Anomaly",
        _option_values(anomalies, "anomaly_type"),
        key="anomaly_type_filter",
    )
    anomaly_asset_type = anomaly_filters[1].selectbox(
        "Loại thiết bị",
        _option_values(anomalies, "asset_type"),
        key="anomaly_asset_type_filter",
    )
    anomaly_view = _filter_frame(anomalies, "anomaly_type", _selected_value(anomaly_type))
    anomaly_view = _filter_frame(
        anomaly_view,
        "asset_type",
        _selected_value(anomaly_asset_type),
    )
    _dataframe(_sort_dataframe(anomaly_view, "anomaly_score"), ANOMALY_COLUMNS)
    if anomaly_view.empty:
        st.info("Không có anomaly phù hợp với bộ lọc.")

    st.markdown("#### Nhóm lỗi lặp lại")
    recurring_filters = st.columns(2)
    failure_category = recurring_filters[0].selectbox(
        "Failure category",
        _option_values(recurring, "failure_category"),
        key="recurring_failure_category",
    )
    flag_label = recurring_filters[1].selectbox(
        "Chỉ nhóm đạt ngưỡng",
        ["Có", "Không", ALL_OPTION],
        key="recurring_flag_filter",
    )
    recurrence_flag = {"Có": True, "Không": False}.get(flag_label)
    try:
        recurring_view = records_to_dataframe(
            client.list_recurring_issues(
                failure_category=_selected_value(failure_category),
                recurrence_flag=recurrence_flag,
            )
        )
    except ApiClientError as exc:
        st.error(str(exc))
        return
    _dataframe(recurring_view, RECURRING_COLUMNS)
    if recurring_view.empty:
        st.info("Không có nhóm lỗi lặp lại phù hợp với bộ lọc.")

    st.caption(
        "Anomaly là tín hiệu khác biệt so với baseline, không chứng minh thiết bị đã hỏng. "
        "Recurring issue là phép nhóm ticket deterministic với ngưỡng 3 occurrences."
    )


def render_maintenance_copilot(
    client: MaintenanceApiClient,
    assets: pd.DataFrame,
) -> None:
    """Preserve the existing RAG Copilot workflow with clearer safety context."""

    st.subheader("Trợ lý bảo trì")
    asset_ids = _asset_id_options(assets)
    selected_asset_id = st.selectbox(
        "Thiết bị",
        ["", *asset_ids],
        key="copilot_asset_id",
    )

    if selected_asset_id:
        try:
            with st.spinner("Đang tải ngữ cảnh thiết bị..."):
                details = client.get_asset_details(selected_asset_id, limit=3)
        except ApiClientError as exc:
            st.error(str(exc))
        else:
            profile = details.get("asset_profile") or {}
            latest_risk = details.get("latest_risk") or {}
            st.markdown("#### Facts từ dữ liệu thiết bị")
            context_columns = st.columns(4)
            context_columns[0].metric("Thiết bị", _metric_value(profile.get("asset_name")))
            context_columns[1].metric("Vị trí", _metric_value(profile.get("location")))
            context_columns[2].metric(
                "Risk Score", _metric_value(latest_risk.get("risk_score"), decimals=2)
            )
            context_columns[3].metric(
                "Risk Level", _metric_value(latest_risk.get("risk_level"))
            )

    question = st.text_area(
        "Câu hỏi bảo trì",
        value="Vì sao thiết bị này có rủi ro cao và kỹ thuật viên nên kiểm tra gì?",
        height=110,
        key="copilot_question",
    )
    top_k = st.number_input(
        "Số đoạn SOP/Checklist truy xuất",
        min_value=1,
        max_value=20,
        value=5,
        step=1,
        key="copilot_top_k",
    )
    if not st.button("Hỏi Copilot", type="primary", key="copilot_ask"):
        st.info("Qdrant cần được index bằng `make index-documents` trước khi hỏi Copilot.")
        _render_copilot_disclaimer()
        return
    if not question.strip():
        st.warning("Vui lòng nhập câu hỏi.")
        return

    try:
        with st.spinner("Copilot đang truy xuất SOP/Checklist..."):
            response = client.ask_copilot(
                question=question.strip(),
                asset_id=selected_asset_id or None,
                top_k=int(top_k),
            )
    except ApiClientError:
        st.warning(
            "Maintenance Copilot tạm thời không truy cập được. Dashboard quản lý và dữ liệu "
            "thiết bị vẫn có thể tiếp tục sử dụng."
        )
        _render_copilot_disclaimer()
        return

    retrieval_status = str(response.get("retrieval_status") or "success")
    if retrieval_status == "success":
        st.success("Đã tìm thấy hướng dẫn vượt ngưỡng relevance và có nguồn trích dẫn.")
    else:
        st.warning(
            "Copilot chưa tìm thấy tài liệu đủ liên quan hoặc kho tài liệu chưa sẵn sàng. "
            "Không sử dụng nội dung không liên quan để tạo khuyến nghị."
        )

    st.markdown("#### Hướng dẫn được truy xuất")
    st.write(response.get("answer") or "Không có câu trả lời.")
    filters_applied = response.get("filters_applied") or {}
    if filters_applied:
        filters_text = ", ".join(
            f"{key}={value}" for key, value in filters_applied.items()
        )
        st.caption(f"Bộ lọc retrieval: {filters_text}")
    st.markdown("#### Nguồn SOP/Checklist")
    sources = records_to_dataframe(response.get("sources"))
    _dataframe(
        sources,
        [
            "title",
            "document_type",
            "asset_type",
            "failure_category",
            "version",
            "effective_date",
            "source",
            "score",
        ],
    )
    if sources.empty:
        st.info("Không có nguồn đủ liên quan để hiển thị.")
    with st.expander("Đoạn tài liệu đã truy xuất", expanded=False):
        chunks = records_to_dataframe(response.get("retrieved_chunks"))
        _dataframe(
            chunks,
            [
                "title",
                "document_type",
                "asset_type",
                "failure_category",
                "chunk_index",
                "score",
                "content",
            ],
        )
    safety_notice = response.get("safety_notice")
    if safety_notice:
        st.warning(str(safety_notice))
    _render_copilot_disclaimer()


def _render_asset_details(details: dict[str, Any]) -> None:
    profile = details.get("asset_profile") or {}
    latest_risk = details.get("latest_risk") or {}
    preventive = details.get("preventive_maintenance") or {}

    st.markdown("#### Hồ sơ và facts mới nhất")
    profile_columns = st.columns(4)
    profile_columns[0].metric("Tên thiết bị", _metric_value(profile.get("asset_name")))
    profile_columns[1].metric("Loại", _metric_value(profile.get("asset_type")))
    profile_columns[2].metric("Vị trí", _metric_value(profile.get("location")))
    profile_columns[3].metric("Criticality", _metric_value(profile.get("criticality")))
    signal_columns = st.columns(4)
    signal_columns[0].metric(
        "Risk Score", _metric_value(latest_risk.get("risk_score"), decimals=2)
    )
    signal_columns[1].metric("Risk Level", _metric_value(latest_risk.get("risk_level")))
    signal_columns[2].metric(
        "Bảo trì", _metric_value(preventive.get("maintenance_status_display"))
    )
    signal_columns[3].metric(
        "Số ngày quá hạn", _metric_value(preventive.get("days_overdue"))
    )

    st.markdown("#### Giải thích Risk Score")
    st.write(_as_text(details.get("risk_contributing_factors")) or "Không có.")
    st.markdown("#### Khuyến nghị tham khảo")
    st.info(_as_text(details.get("recommended_action")) or "Không có khuyến nghị.")
    st.caption("Khuyến nghị phải được kỹ thuật viên xác minh trước khi thực hiện.")

    history = records_to_dataframe(details.get("risk_history"))
    if not history.empty and {"date", "risk_score"}.issubset(history.columns):
        st.markdown("#### Lịch sử Risk Score")
        trend = history.sort_values("date").set_index("date")[["risk_score"]]
        st.line_chart(trend)

    detail_tabs = st.tabs(
        ["Ticket gần đây", "Maintenance logs", "Anomaly", "Lỗi lặp lại"]
    )
    with detail_tabs[0]:
        _dataframe(records_to_dataframe(details.get("recent_tickets")), TICKET_COLUMNS)
    with detail_tabs[1]:
        _dataframe(
            records_to_dataframe(details.get("recent_maintenance_logs")), LOG_COLUMNS
        )
    with detail_tabs[2]:
        _dataframe(records_to_dataframe(details.get("recent_anomalies")), ANOMALY_COLUMNS)
    with detail_tabs[3]:
        _dataframe(records_to_dataframe(details.get("recurring_issues")), RECURRING_COLUMNS)


def _render_distribution_chart(
    container: Any,
    frame: pd.DataFrame,
    column: str,
    title: str,
) -> None:
    with container:
        st.markdown(f"**{title}**")
        distribution = _distribution(frame, column)
        if distribution.empty:
            st.info("Chưa có dữ liệu.")
        else:
            st.bar_chart(distribution)


def _distribution(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame.columns:
        return pd.Series(dtype="int64")
    return frame[column].dropna().astype(str).value_counts().rename("Số bản ghi")


def _render_safety_notice() -> None:
    st.info(
        "Risk Score là tín hiệu ưu tiên; Anomaly không chứng minh thiết bị hỏng. "
        "Kết quả dùng dữ liệu synthetic MVP và mọi khuyến nghị phải được kỹ thuật viên xác minh."
    )


def _render_copilot_disclaimer() -> None:
    st.warning(
        "Copilot chỉ hỗ trợ tra cứu và quyết định. Anomaly và Risk Score không chứng minh "
        "thiết bị đã hỏng. Kỹ thuật viên phải kiểm tra hiện trường; hướng dẫn nhà sản xuất và "
        "quy trình an toàn của tòa nhà luôn được ưu tiên."
    )


def _render_sidebar() -> str:
    st.sidebar.header("Kết nối")
    return st.sidebar.text_input(
        "API_BASE_URL",
        value=get_api_base_url(),
        key="sidebar_api_base_url",
    ).strip()


def _render_connection_error(api_base_url: str, error: ApiClientError) -> None:
    st.error(f"Không thể kết nối FastAPI tại {api_base_url}.")
    st.caption(str(error))
    st.code("make run-api", language="bash")


def _render_data_error(error: ApiClientError) -> None:
    st.error("API đã kết nối nhưng CSV nguồn hoặc analytics output chưa sẵn sàng.")
    st.caption(str(error))


def _dataframe(frame: pd.DataFrame, preferred_columns: list[str]) -> None:
    if frame.empty:
        st.info("Không có dữ liệu để hiển thị.")
        return
    columns = [column for column in preferred_columns if column in frame.columns]
    st.dataframe(frame[columns], width="stretch", hide_index=True)


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


def _filter_frame(frame: pd.DataFrame, column: str, value: str | None) -> pd.DataFrame:
    if value is None or frame.empty or column not in frame.columns:
        return frame
    return frame[frame[column].astype(str) == value]


def _sort_dataframe(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if frame.empty or column not in frame.columns:
        return frame
    return frame.sort_values(column, ascending=False, na_position="last")


def _metric_value(value: Any, decimals: int | None = None) -> str:
    if value is None or value == "" or pd.isna(value):
        return "-"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.{decimals or 0}f}"
    return str(value)


def _format_percent(value: Any) -> str:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "-"


def _format_hours(value: Any) -> str:
    try:
        return f"{float(value):.1f} giờ"
    except (TypeError, ValueError):
        return "-"


def _as_text(value: Any) -> str:
    return "" if value is None else str(value)


if __name__ == "__main__":
    main()
