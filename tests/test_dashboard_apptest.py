"""Streamlit AppTest smoke coverage for the interactive workflow."""

from __future__ import annotations

from typing import Any

from streamlit.testing.v1 import AppTest

import src.dashboard.api_client as api_client_module


class FakeMaintenanceApiClient:
    """Small in-process API boundary used only by Streamlit AppTest."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "raw_data_available": True, "analytics_available": True}

    def list_assets(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [_asset_overview()]

    def get_maintenance_kpis(self) -> dict[str, Any]:
        return {
            "open_tickets": 1,
            "ticket_resolution_rate_percent": 50.0,
            "average_resolution_time_hours": 12.0,
            "overdue_asset_count": 1,
            "high_critical_risk_asset_count": 1,
            "follow_up_required_maintenance_count": 0,
        }

    def list_tickets(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [_ticket()]

    def list_preventive_maintenance(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "asset_id": "GENERATOR_002",
                "maintenance_status": "overdue",
                "maintenance_status_display": "Quá hạn",
            }
        ]

    def list_recurring_issues(self, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    def get_asset_details(self, asset_id: str, **kwargs: Any) -> dict[str, Any]:
        return _asset_details()

    def list_anomalies(self, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        return {
            "asset_id": asset_id,
            "maintenance_interval_days": 120,
        }


def test_dashboard_renders_interactive_workflow(monkeypatch) -> None:
    monkeypatch.setattr(
        api_client_module,
        "MaintenanceApiClient",
        FakeMaintenanceApiClient,
    )
    app = AppTest.from_file("src/dashboard/app.py", default_timeout=10).run()

    assert not app.exception
    tab_labels = [tab.label for tab in app.tabs]
    for expected_label in [
        "Tổng quan",
        "Thiết bị và rủi ro",
        "Ticket workspace",
        "Bất thường và lỗi lặp lại",
        "Trợ lý bảo trì",
        "Mới tạo",
        "Đang xử lý",
        "Đã xử lý",
    ]:
        assert expected_label in tab_labels
    button_labels = [button.label for button in app.button]
    assert "Xem chi tiết" in button_labels
    assert "Tạo ticket kiểm tra" in button_labels
    assert "Mở Copilot checklist" in button_labels
    assert "Lưu cập nhật" in button_labels

    next(button for button in app.button if button.label == "Tạo ticket kiểm tra").click()
    app.run()

    assert not app.exception
    assert any(area.label == "Mô tả kiểm tra đề xuất" for area in app.text_area)
    assert any(area.label == "Ghi chú manager (khuyến nghị)" for area in app.text_area)


def _asset_overview() -> dict[str, Any]:
    return {
        "asset_id": "GENERATOR_002",
        "asset_name": "Máy phát điện dự phòng 002",
        "asset_type": "Máy phát điện dự phòng",
        "location": "Sân thượng phía Đông",
        "criticality": "Rất quan trọng",
        "status": "Cảnh báo",
        "risk_score": 63.89,
        "risk_level": "Cao",
        "maintenance_status": "overdue",
        "maintenance_status_display": "Quá hạn",
        "days_overdue": 159,
        "unresolved_ticket_count": 2,
    }


def _ticket() -> dict[str, Any]:
    return {
        "ticket_id": "TCK-000101",
        "asset_id": "GENERATOR_002",
        "issue_description": "Kiểm tra khả năng khởi động.",
        "priority": "Cao",
        "status": "Mới tạo",
        "failure_category": "Lỗi điện",
        "created_at": "2026-07-15T01:00:00+00:00",
        "resolved_at": None,
        "technician_id": "TECH_001",
        "manager_note": None,
        "note": None,
    }


def _asset_details() -> dict[str, Any]:
    return {
        "asset_profile": {
            **_asset_overview(),
            "installation_date": "2023-01-01",
            "last_maintenance_date": "2025-07-25",
            "maintenance_interval_days": 120,
            "next_maintenance_date": "2025-11-22",
        },
        "latest_risk": {
            "asset_id": "GENERATOR_002",
            "risk_score": 63.89,
            "risk_level": "Cao",
        },
        "risk_contributing_factors": "Bảo trì quá hạn 159 ngày",
        "recommended_action": "Kiểm tra trong tuần.",
        "preventive_maintenance": {
            "maintenance_status": "overdue",
            "maintenance_status_display": "Quá hạn",
            "days_overdue": 159,
        },
        "risk_history": [],
        "recent_anomalies": [],
        "recent_tickets": [_ticket()],
        "recent_maintenance_logs": [],
        "recurring_issues": [],
    }
