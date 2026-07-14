"""API response schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    status: str
    raw_data_available: bool | None = None
    analytics_available: bool | None = None


class SummaryResponse(BaseModel):
    """Overall maintenance decision-support summary."""

    total_assets: int
    total_records: int
    high_risk_count: int
    urgent_risk_count: int
    anomaly_count: int
    latest_date: str | None
    average_risk_score: float


class RiskRecord(BaseModel):
    """Risk score record returned by API endpoints."""

    model_config = ConfigDict(extra="allow")

    asset_id: str
    date: str
    asset_name: str
    asset_type: str
    location: str
    anomaly_score: float = Field(ge=0, le=100)
    maintenance_overdue_score: float = Field(ge=0, le=100)
    recent_ticket_score: float = Field(ge=0, le=100)
    criticality_score: float = Field(ge=0, le=100)
    runtime_score: float = Field(ge=0, le=100)
    final_risk_score: float = Field(ge=0, le=100)
    risk_level: str
    main_reasons: str
    recommended_action: str


class AnomalyRecord(BaseModel):
    """Anomaly record returned by API endpoints."""

    model_config = ConfigDict(extra="allow")

    asset_id: str
    date: str
    asset_type: str
    location: str
    energy_kwh: float
    temperature: float
    vibration: float
    runtime_hours: float
    pressure: float
    energy_delta_percent: float
    vibration_delta: float
    runtime_delta_percent: float
    rule_based_score: float = Field(ge=0, le=100)
    isolation_forest_score: float = Field(ge=0, le=100)
    anomaly_score: float = Field(ge=0, le=100)
    is_anomaly: bool
    anomaly_type: str
    anomaly_reasons: str


class AssetContextResponse(BaseModel):
    """Combined asset context for future copilot and dashboard workflows."""

    asset_id: str
    latest_risk: dict[str, Any]
    recent_anomalies: list[dict[str, Any]]
    recent_features: list[dict[str, Any]]
    latest_recommendation: str | None


class AssetRecord(BaseModel):
    """Asset master record from the raw CSV contract."""

    model_config = ConfigDict(extra="allow")

    asset_id: str
    asset_name: str
    asset_type: str
    location: str
    criticality: str
    status: str
    installation_date: str
    last_maintenance_date: str
    maintenance_interval_days: int = Field(gt=0)
    next_maintenance_date: str


class AssetOverviewRecord(AssetRecord):
    """Asset master record enriched with the latest decision-support signals."""

    risk_score: float | None = Field(default=None, ge=0, le=100)
    risk_level_code: str | None = None
    risk_level: str | None = None
    contributing_factors: str | None = None
    recommended_action: str | None = None
    maintenance_status: str | None = None
    maintenance_status_display: str | None = None
    days_until_due: int | None = Field(default=None, ge=0)
    days_overdue: int | None = Field(default=None, ge=0)
    unresolved_ticket_count: int | None = Field(default=None, ge=0)


class TicketRecord(BaseModel):
    """Maintenance ticket record."""

    ticket_id: str
    asset_id: str
    issue_description: str
    priority: str
    status: str
    failure_category: str
    created_at: str
    resolved_at: str | None
    technician_id: str


class MaintenanceLogRecord(BaseModel):
    """Maintenance history record."""

    log_id: str
    ticket_id: str | None
    asset_id: str
    maintenance_date: str
    maintenance_type: str
    technician_id: str
    inspection_result: str
    actions_taken: str
    parts_replaced: str | None
    technician_note: str
    maintenance_result: str
    follow_up_required: bool
    next_maintenance_date: str


class PreventiveMaintenanceRecord(BaseModel):
    """Current preventive maintenance status for an asset."""

    model_config = ConfigDict(extra="allow")

    asset_id: str
    as_of_date: str
    last_maintenance_date: str
    next_maintenance_date: str
    days_until_due: int = Field(ge=0)
    days_overdue: int = Field(ge=0)
    maintenance_status: str
    maintenance_status_display: str


class RecurringIssueRecord(BaseModel):
    """Deterministic recurring ticket group."""

    asset_id: str
    failure_category: str
    occurrence_count: int = Field(ge=1)
    first_occurrence: str
    last_occurrence: str
    resolved_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    recurrence_flag: bool
    recurrence_threshold: int = Field(ge=2)


class MaintenanceKpiResponse(BaseModel):
    """Current descriptive maintenance KPI snapshot."""

    as_of_date: str
    total_tickets: int = Field(ge=0)
    open_tickets: int = Field(ge=0)
    resolved_tickets: int = Field(ge=0)
    ticket_resolution_rate_percent: float = Field(ge=0, le=100)
    average_resolution_time_hours: float = Field(ge=0)
    median_resolution_time_hours: float = Field(ge=0)
    overdue_asset_count: int = Field(ge=0)
    due_soon_asset_count: int = Field(ge=0)
    recurring_issue_count: int = Field(ge=0)
    follow_up_required_maintenance_count: int = Field(ge=0)
    high_critical_risk_asset_count: int = Field(ge=0)


class AssetDetailsResponse(BaseModel):
    """Consolidated manager-facing asset view."""

    asset_profile: AssetRecord
    latest_risk: RiskRecord | None
    risk_contributing_factors: str | None
    recommended_action: str | None
    preventive_maintenance: PreventiveMaintenanceRecord | None
    risk_history: list[RiskRecord]
    recent_anomalies: list[AnomalyRecord]
    recent_tickets: list[TicketRecord]
    recent_maintenance_logs: list[MaintenanceLogRecord]
    recurring_issues: list[RecurringIssueRecord]


class CopilotAskRequest(BaseModel):
    """Request body for the deterministic Maintenance Copilot."""

    question: str = Field(min_length=1, max_length=1000)
    asset_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    document_type: str | None = None
    failure_category: str | None = None


class CopilotAskResponse(BaseModel):
    """Response returned by the Maintenance Copilot."""

    answer: str
    asset_context: dict[str, Any] | None
    sources: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    retrieval_status: str = "relevant"
    relevance_status: str = "relevant"
    safety_notice: str = ""
    filters_applied: dict[str, str] = Field(default_factory=dict)
