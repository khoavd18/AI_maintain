"""Streamlit manager dashboard for the focused AI Maintenance Copilot MVP."""

from __future__ import annotations

from datetime import date, timedelta
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
TICKET_STATUSES = ["Mới tạo", "Đang xử lý", "Đã xử lý"]
PRIORITIES = ["Thấp", "Trung bình", "Cao", "Khẩn cấp"]
FAILURE_CATEGORIES = [
    "Lỗi làm lạnh",
    "Lỗi rung động",
    "Lỗi điện",
    "Lỗi áp suất",
    "Lỗi thời gian vận hành",
    "Lỗi cảm biến",
    "Cảnh báo giả",
    "Không có lỗi",
]
MAINTENANCE_RESULTS = [
    "Đã xử lý",
    "Đã xử lý một phần",
    "Cần theo dõi",
    "Cần hỗ trợ chuyên môn",
]

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
    "manager_note",
    "note",
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
    """Render only public status for the legacy Streamlit development client."""

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
            "API đang hoạt động nhưng transactional storage hoặc analytics output chưa sẵn sàng. "
            "Hãy chạy lại batch pipeline."
        )
    else:
        st.sidebar.success("Đã kết nối API")

    st.warning(
        "Streamlit là client development legacy. Các workflow được bảo vệ đã bị vô hiệu hóa "
        "để không tạo đường bypass authentication."
    )
    st.info(
        "Sử dụng Next.js tại http://localhost:3000 để đăng nhập, xem analytics, xử lý ticket "
        "và dùng Maintenance Copilot."
    )
    st.metric(
        "Trạng thái FastAPI",
        "Đã kết nối" if health.get("status") == "ok" else "Degraded",
    )


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

    asset_options = filtered["asset_id"].astype(str).tolist()
    requested_asset_id = st.session_state.pop("requested_asset_id", None)
    if requested_asset_id in asset_options:
        st.session_state["selected_asset_details"] = requested_asset_id
    selected_asset_id = st.selectbox(
        "Chọn thiết bị để xem chi tiết",
        asset_options,
        key="selected_asset_details",
    )
    try:
        with st.spinner(f"Đang tải lịch sử {selected_asset_id}..."):
            details = client.get_asset_details(selected_asset_id, limit=10)
    except ApiClientError as exc:
        st.error(str(exc))
        return

    action_columns = st.columns(3)
    if action_columns[0].button(
        "Xem chi tiết",
        type="primary",
        key=f"view_asset_{selected_asset_id}",
        width="stretch",
    ):
        st.session_state["asset_details_open"] = selected_asset_id
    if action_columns[1].button(
        "Tạo ticket kiểm tra",
        key=f"create_ticket_{selected_asset_id}",
        width="stretch",
    ):
        st.session_state["asset_details_open"] = selected_asset_id
        st.session_state["ticket_create_asset_id"] = selected_asset_id
    if action_columns[2].button(
        "Mở Copilot checklist",
        key=f"asset_copilot_{selected_asset_id}",
        width="stretch",
    ):
        _set_copilot_context(details)
        st.success("Đã chuẩn bị ngữ cảnh. Mở tab Trợ lý bảo trì để xem checklist.")

    if st.session_state.get("ticket_create_asset_id") == selected_asset_id:
        _render_create_ticket_form(client, details)

    if st.session_state.get("asset_details_open") == selected_asset_id:
        _render_asset_details(details)
    else:
        st.caption("Chọn hành động để xem facts, tạo ticket hoặc mở checklist.")


def render_ticket_workspace(client: MaintenanceApiClient, assets: pd.DataFrame) -> None:
    """Render the small assignment, inspection, and resolution workflow."""

    st.subheader("Ticket workspace")
    notice = st.session_state.pop("ticket_workflow_notice", None)
    if notice:
        st.success(str(notice))
    try:
        tickets = records_to_dataframe(client.list_tickets(limit=1000))
    except ApiClientError as exc:
        st.error(str(exc))
        return
    if tickets.empty:
        st.info("Chưa có ticket bảo trì.")
        return

    status_metrics = st.columns(3)
    for column, status_value in zip(status_metrics, TICKET_STATUSES, strict=True):
        count = int((tickets["status"] == status_value).sum())
        column.metric(status_value, count)

    status_tabs = st.tabs(TICKET_STATUSES)
    for tab, status_value in zip(status_tabs, TICKET_STATUSES, strict=True):
        with tab:
            status_rows = tickets[tickets["status"] == status_value].head(15)
            _dataframe(
                status_rows,
                [
                    "ticket_id",
                    "asset_id",
                    "priority",
                    "failure_category",
                    "technician_id",
                    "created_at",
                ],
            )

    st.markdown("#### Chọn ticket để xử lý")
    filter_columns = st.columns(3)
    status_filter = filter_columns[0].selectbox(
        "Trạng thái",
        [ALL_OPTION, *TICKET_STATUSES],
        key="ticket_status_filter",
    )
    priority_filter = filter_columns[1].selectbox(
        "Mức ưu tiên",
        [ALL_OPTION, *PRIORITIES],
        key="ticket_priority_filter",
    )
    asset_filter = filter_columns[2].selectbox(
        "Thiết bị",
        [ALL_OPTION, *_asset_id_options(assets)],
        key="ticket_asset_filter",
    )
    filtered = _filter_frame(tickets, "status", _selected_value(status_filter))
    filtered = _filter_frame(filtered, "priority", _selected_value(priority_filter))
    filtered = _filter_frame(filtered, "asset_id", _selected_value(asset_filter))
    filtered = filtered.sort_values("created_at", ascending=False)
    if filtered.empty:
        st.info("Không có ticket phù hợp với bộ lọc.")
        return

    ticket_options = filtered["ticket_id"].astype(str).tolist()
    requested_ticket_id = st.session_state.pop("requested_ticket_id", None)
    if requested_ticket_id in ticket_options:
        st.session_state["selected_ticket_id"] = requested_ticket_id
    selected_ticket_id = st.selectbox(
        "Ticket",
        ticket_options,
        key="selected_ticket_id",
    )
    selected_ticket = filtered[
        filtered["ticket_id"].astype(str) == selected_ticket_id
    ].iloc[0].to_dict()

    badge_columns = st.columns([1, 1, 3])
    with badge_columns[0]:
        st.badge(
            str(selected_ticket["status"]),
            color=_ticket_status_color(str(selected_ticket["status"])),
        )
    with badge_columns[1]:
        st.badge(
            str(selected_ticket["priority"]),
            color=_priority_color(str(selected_ticket["priority"])),
        )
    badge_columns[2].caption(
        f"{selected_ticket['asset_id']} · {selected_ticket['failure_category']}"
    )

    detail_columns = st.columns(3)
    detail_columns[0].metric("Kỹ thuật viên", selected_ticket.get("technician_id") or "-")
    detail_columns[1].metric("Ngày tạo", selected_ticket.get("created_at") or "-")
    detail_columns[2].metric("Ngày xử lý", selected_ticket.get("resolved_at") or "-")
    st.write(str(selected_ticket.get("issue_description") or ""))

    action_columns = st.columns(2)
    if action_columns[0].button(
        "Mở thiết bị liên quan",
        key=f"ticket_asset_{selected_ticket_id}",
        width="stretch",
    ):
        st.session_state["requested_asset_id"] = str(selected_ticket["asset_id"])
        st.session_state["asset_details_open"] = str(selected_ticket["asset_id"])
        st.success("Đã chọn thiết bị liên quan. Mở tab Thiết bị và rủi ro để xem.")
    if action_columns[1].button(
        "Mở Copilot checklist",
        key=f"ticket_copilot_{selected_ticket_id}",
        width="stretch",
    ):
        try:
            details = client.get_asset_details(str(selected_ticket["asset_id"]), limit=5)
        except ApiClientError as exc:
            st.error(str(exc))
        else:
            _set_copilot_context(details, selected_ticket)
            st.success("Đã chuẩn bị ticket context. Mở tab Trợ lý bảo trì để tiếp tục.")

    with st.expander("Phân công và cập nhật trạng thái", expanded=True):
        allowed_statuses = _allowed_ticket_statuses(str(selected_ticket["status"]))
        with st.form(f"ticket_update_form_{selected_ticket_id}"):
            update_columns = st.columns(3)
            updated_status = update_columns[0].selectbox(
                "Trạng thái",
                allowed_statuses,
                index=allowed_statuses.index(str(selected_ticket["status"])),
            )
            updated_priority = update_columns[1].selectbox(
                "Mức ưu tiên",
                PRIORITIES,
                index=PRIORITIES.index(str(selected_ticket["priority"])),
            )
            updated_technician = update_columns[2].text_input(
                "Kỹ thuật viên",
                value=str(selected_ticket.get("technician_id") or ""),
            )
            update_note = st.text_area("Ghi chú cập nhật", height=80)
            update_submitted = st.form_submit_button(
                "Lưu cập nhật",
                type="primary",
                width="stretch",
            )
        if update_submitted:
            try:
                updated = client.update_ticket(
                    selected_ticket_id,
                    status=updated_status,
                    priority=updated_priority,
                    technician_id=updated_technician,
                    note=update_note or None,
                )
            except ApiClientError as exc:
                st.error(str(exc))
            else:
                st.session_state["requested_ticket_id"] = selected_ticket_id
                st.session_state["ticket_workflow_notice"] = (
                    f"Đã cập nhật {selected_ticket_id}: {updated['status']}."
                )
                st.rerun()

    if selected_ticket["status"] == "Đang xử lý":
        _render_maintenance_result_form(client, selected_ticket)
    elif selected_ticket["status"] == "Mới tạo":
        st.info("Chuyển ticket sang Đang xử lý trước khi ghi kết quả kiểm tra.")

    st.caption(
        "Ticket và log được ghi vào PostgreSQL. Risk/KPI hiện tại giữ nguyên cho đến lần chạy batch "
        "analytics tiếp theo."
    )


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
    context = st.session_state.get("copilot_context") or {}
    context_asset_id = str(context.get("asset_id") or "")
    if "copilot_asset_id" not in st.session_state:
        st.session_state["copilot_asset_id"] = (
            context_asset_id if context_asset_id in asset_ids else ""
        )
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
            context_columns = st.columns(5)
            context_columns[0].metric("Thiết bị", _metric_value(profile.get("asset_name")))
            context_columns[1].metric("Loại", _metric_value(profile.get("asset_type")))
            context_columns[2].metric(
                "Vị trí", _metric_value(profile.get("location"))
            )
            context_columns[3].metric(
                "Risk Score", _metric_value(latest_risk.get("risk_score"), decimals=2)
            )
            context_columns[4].metric(
                "Risk Level", _metric_value(latest_risk.get("risk_level"))
            )
            if context_asset_id == selected_asset_id and context.get("ticket_id"):
                st.badge(
                    f"Ticket {context['ticket_id']} · {context.get('failure_category') or '-'}",
                    color="orange",
                )
                with st.expander("Context được chuyển từ ticket", expanded=False):
                    st.write(context.get("ticket_description") or "-")
                    st.caption(
                        "Giải thích risk mới nhất: "
                        f"{context.get('risk_explanation') or 'Không có.'}"
                    )

    if "copilot_question" not in st.session_state:
        st.session_state["copilot_question"] = (
            "Vì sao thiết bị này có rủi ro cao và kỹ thuật viên nên kiểm tra gì?"
        )
    question = st.text_area(
        "Câu hỏi bảo trì",
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
        st.info(
            "Qdrant cần được index bằng `python -m src.rag.index_documents` "
            "trước khi hỏi Copilot."
        )
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
                failure_category=(
                    str(context.get("failure_category"))
                    if context_asset_id == selected_asset_id
                    and context.get("failure_category")
                    else None
                ),
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


def _render_create_ticket_form(
    client: MaintenanceApiClient,
    details: dict[str, Any],
) -> None:
    defaults = _ticket_form_defaults(details)
    asset_id = str(defaults["asset_id"])
    with st.expander("Tạo ticket kiểm tra", expanded=True):
        st.markdown("**Facts đo được từ batch analytics**")
        fact_columns = st.columns(2)
        fact_columns[0].metric("Asset ID", asset_id)
        with fact_columns[1]:
            st.badge(
                f"Risk Level: {defaults['risk_level']}",
                color=_risk_color(str(defaults["risk_level"])),
            )
        st.caption(f"Yếu tố đóng góp: {defaults['contributing_factors'] or 'Không có.'}")

        st.markdown("**Đề xuất của manager trước khi giao kỹ thuật viên**")
        with st.form(f"create_ticket_form_{asset_id}"):
            issue_description = st.text_area(
                "Mô tả kiểm tra đề xuất",
                value=str(defaults["issue_description"]),
                height=100,
            )
            form_columns = st.columns(3)
            priority = form_columns[0].selectbox(
                "Mức ưu tiên",
                PRIORITIES,
                index=PRIORITIES.index(str(defaults["priority"])),
            )
            failure_category = form_columns[1].selectbox(
                "Nhóm sự cố",
                FAILURE_CATEGORIES,
                index=FAILURE_CATEGORIES.index(str(defaults["failure_category"])),
            )
            technician_id = form_columns[2].text_input(
                "Kỹ thuật viên",
                value=str(defaults["technician_id"]),
            )
            manager_note = st.text_area(
                "Ghi chú manager (khuyến nghị)",
                value=str(defaults["manager_note"]),
                height=80,
            )
            submitted = st.form_submit_button(
                "Tạo ticket kiểm tra",
                type="primary",
                width="stretch",
            )
        if submitted:
            try:
                ticket = client.create_ticket(
                    asset_id=asset_id,
                    issue_description=issue_description,
                    priority=priority,
                    failure_category=failure_category,
                    technician_id=technician_id,
                    manager_note=manager_note or None,
                )
            except ApiClientError as exc:
                st.error(str(exc))
            else:
                st.session_state["requested_ticket_id"] = ticket["ticket_id"]
                st.session_state.pop("ticket_create_asset_id", None)
                st.success(
                    f"Đã tạo {ticket['ticket_id']} ở trạng thái {ticket['status']}. "
                    "Mở Ticket workspace để phân công và cập nhật."
                )
                st.caption("Risk/KPI sẽ chỉ thay đổi sau lần chạy batch analytics tiếp theo.")


def _render_maintenance_result_form(
    client: MaintenanceApiClient,
    ticket: dict[str, Any],
) -> None:
    ticket_id = str(ticket["ticket_id"])
    try:
        asset = client.get_asset(str(ticket["asset_id"]))
    except ApiClientError as exc:
        st.error(str(exc))
        return
    interval_days = int(asset.get("maintenance_interval_days") or 1)
    default_date = date.today()
    default_next_date = _calculate_next_maintenance_date(default_date, interval_days)

    with st.expander("Ghi kết quả kiểm tra/bảo trì", expanded=True):
        with st.form(f"maintenance_result_form_{ticket_id}"):
            date_columns = st.columns(2)
            maintenance_date = date_columns[0].date_input(
                "Ngày bảo trì",
                value=default_date,
            )
            next_maintenance_date = date_columns[1].date_input(
                "Ngày bảo trì kế tiếp",
                value=default_next_date,
            )
            inspection_result = st.text_area("Kết quả kiểm tra", height=80)
            actions_taken = st.text_area("Hành động đã thực hiện", height=80)
            parts_replaced = st.text_input(
                "Vật tư đã thay (lịch sử mô tả, không phải inventory)"
            )
            technician_note = st.text_area("Ghi chú kỹ thuật viên", height=80)
            maintenance_result = st.selectbox(
                "Kết quả bảo trì",
                MAINTENANCE_RESULTS,
            )
            follow_up_required = _maintenance_follow_up(maintenance_result)
            st.checkbox(
                "Cần follow-up",
                value=follow_up_required,
                disabled=True,
                help="Giá trị được xác định theo canonical maintenance result contract.",
            )
            submitted = st.form_submit_button(
                "Lưu kết quả bảo trì",
                type="primary",
                width="stretch",
            )
        if submitted:
            try:
                client.create_maintenance_log(
                    ticket_id=ticket_id,
                    asset_id=str(ticket["asset_id"]),
                    maintenance_date=maintenance_date.isoformat(),
                    inspection_result=inspection_result,
                    actions_taken=actions_taken,
                    parts_replaced=parts_replaced or None,
                    technician_note=technician_note,
                    maintenance_result=maintenance_result,
                    follow_up_required=follow_up_required,
                    next_maintenance_date=next_maintenance_date.isoformat(),
                )
            except ApiClientError as exc:
                st.error(str(exc))
            else:
                st.session_state["requested_ticket_id"] = ticket_id
                st.session_state["ticket_workflow_notice"] = (
                    "Maintenance data has been recorded. Risk and KPI results will update in "
                    "the next analytics batch."
                )
                st.rerun()
        st.caption(
            "Kết quả Đã xử lý có thể chuyển ticket sang Đã xử lý sau khi lưu log. Các kết quả "
            "khác giữ ticket để follow-up."
        )


def _set_copilot_context(
    details: dict[str, Any],
    ticket: dict[str, Any] | None = None,
) -> None:
    context = _build_copilot_context(details, ticket)
    st.session_state["copilot_context"] = context
    st.session_state["copilot_asset_id"] = context["asset_id"]
    st.session_state["copilot_question"] = _build_copilot_question(context)


def _render_asset_details(details: dict[str, Any]) -> None:
    profile = details.get("asset_profile") or {}
    latest_risk = details.get("latest_risk") or {}
    preventive = details.get("preventive_maintenance") or {}

    badge_columns = st.columns(2)
    with badge_columns[0]:
        st.badge(
            f"Risk: {latest_risk.get('risk_level') or '-'}",
            color=_risk_color(str(latest_risk.get("risk_level") or "")),
        )
    with badge_columns[1]:
        st.badge(
            f"Bảo trì: {preventive.get('maintenance_status_display') or '-'}",
            color=_maintenance_status_color(
                str(preventive.get("maintenance_status") or "")
            ),
        )
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


def _ticket_form_defaults(details: dict[str, Any]) -> dict[str, str]:
    """Build deterministic ticket form defaults from the selected asset facts."""

    profile = details.get("asset_profile") or {}
    latest_risk = details.get("latest_risk") or {}
    recent_tickets = details.get("recent_tickets") or []
    latest_ticket = recent_tickets[0] if recent_tickets else {}
    asset_id = str(profile.get("asset_id") or "")
    asset_name = str(profile.get("asset_name") or asset_id)
    asset_type = str(profile.get("asset_type") or "")
    risk_level = str(latest_risk.get("risk_level") or "Chưa xác định")
    contributing_factors = str(details.get("risk_contributing_factors") or "")
    default_categories = {
        "Máy lạnh": "Lỗi làm lạnh",
        "Máy bơm nước": "Lỗi rung động",
        "Máy phát điện dự phòng": "Lỗi điện",
    }
    failure_category = str(
        latest_ticket.get("failure_category")
        or default_categories.get(asset_type)
        or "Không có lỗi"
    )
    if failure_category not in FAILURE_CATEGORIES:
        failure_category = "Không có lỗi"
    priority = {
        "Khẩn cấp": "Khẩn cấp",
        "Cao": "Cao",
        "Trung bình": "Trung bình",
    }.get(risk_level, "Thấp")
    issue_description = f"Kiểm tra {asset_name} ({asset_id}) theo tín hiệu Risk Level {risk_level}."
    if contributing_factors:
        issue_description += f" Yếu tố đóng góp từ batch analytics: {contributing_factors}."
    return {
        "asset_id": asset_id,
        "risk_level": risk_level,
        "contributing_factors": contributing_factors,
        "issue_description": issue_description,
        "priority": priority,
        "failure_category": failure_category,
        "technician_id": str(latest_ticket.get("technician_id") or "TECH_001"),
        "manager_note": str(details.get("recommended_action") or ""),
    }


def _allowed_ticket_statuses(current_status: str) -> list[str]:
    """Return current and next status for the linear local workflow."""

    transitions = {
        "Mới tạo": ["Mới tạo", "Đang xử lý"],
        "Đang xử lý": ["Đang xử lý", "Đã xử lý"],
        "Đã xử lý": ["Đã xử lý"],
    }
    return transitions.get(current_status, [current_status])


def _maintenance_follow_up(maintenance_result: str) -> bool:
    return maintenance_result != "Đã xử lý"


def _calculate_next_maintenance_date(
    maintenance_date: date,
    interval_days: int,
) -> date:
    return maintenance_date + timedelta(days=interval_days)


def _build_copilot_context(
    details: dict[str, Any],
    ticket: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build the structured dashboard handoff without changing RAG behavior."""

    profile = details.get("asset_profile") or {}
    context = {
        "asset_id": str(profile.get("asset_id") or ""),
        "asset_type": str(profile.get("asset_type") or ""),
        "risk_explanation": str(details.get("risk_contributing_factors") or ""),
        "ticket_id": "",
        "failure_category": "",
        "ticket_description": "",
    }
    if ticket:
        context.update(
            {
                "ticket_id": str(ticket.get("ticket_id") or ""),
                "failure_category": str(ticket.get("failure_category") or ""),
                "ticket_description": str(ticket.get("issue_description") or ""),
            }
        )
    return context


def _build_copilot_question(context: dict[str, str]) -> str:
    parts = [
        f"Thiết bị {context.get('asset_id') or 'đã chọn'} thuộc loại "
        f"{context.get('asset_type') or 'chưa xác định'}.",
    ]
    if context.get("ticket_id"):
        parts.append(
            f"Ticket {context['ticket_id']} thuộc nhóm {context.get('failure_category') or '-'}: "
            f"{context.get('ticket_description') or '-'}"
        )
    if context.get("risk_explanation"):
        parts.append(f"Giải thích risk mới nhất: {context['risk_explanation']}")
    parts.append(
        "Hãy truy xuất SOP/checklist phù hợp và nêu các bước cần kiểm tra trước, kèm cảnh báo "
        "an toàn và nguồn tham khảo."
    )
    return " ".join(parts)[:1000]


def _risk_color(risk_level: str) -> str:
    return {
        "Khẩn cấp": "red",
        "Cao": "orange",
        "Trung bình": "yellow",
        "Thấp": "green",
    }.get(risk_level, "gray")

def _maintenance_status_color(maintenance_status: str) -> str:
    return {
        "overdue": "red",
        "due_soon": "orange",
        "not_due": "green",
    }.get(maintenance_status, "gray")


def _ticket_status_color(ticket_status: str) -> str:
    return {
        "Mới tạo": "blue",
        "Đang xử lý": "orange",
        "Đã xử lý": "green",
    }.get(ticket_status, "gray")


def _priority_color(priority: str) -> str:
    return {
        "Khẩn cấp": "red",
        "Cao": "orange",
        "Trung bình": "yellow",
        "Thấp": "green",
    }.get(priority, "gray")


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
    st.code(
        "python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000",
        language="powershell",
    )


def _render_data_error(error: ApiClientError) -> None:
    st.error("API đã kết nối nhưng transactional storage hoặc analytics output chưa sẵn sàng.")
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
