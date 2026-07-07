"""API response schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    status: str


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
    anomaly_score: float
    maintenance_overdue_score: float
    recent_ticket_score: float
    criticality_score: float
    runtime_score: float
    final_risk_score: float
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
    rule_based_score: float
    isolation_forest_score: float
    anomaly_score: float
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


class CopilotAskRequest(BaseModel):
    """Request body for the deterministic Maintenance Copilot."""

    question: str = Field(min_length=1)
    asset_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class CopilotAskResponse(BaseModel):
    """Response returned by the Maintenance Copilot."""

    answer: str
    asset_context: dict[str, Any] | None
    sources: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
