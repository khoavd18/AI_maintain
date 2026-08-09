"""API request and response schemas."""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    status: str
    raw_data_available: bool | None = None
    analytics_available: bool | None = None


class RagHealthResponse(BaseModel):
    """Readiness of the optional but user-visible knowledge retrieval boundary."""

    status: Literal["ready", "degraded"]
    qdrant_ready: bool
    collection: str
    expected_vector_dimensions: int


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


class AssetProfileResponse(AssetRecord):
    """Canonical asset lifecycle profile with legacy fields retained."""

    asset_type_code: Literal["hvac", "pump", "generator"]
    asset_category: Literal["climate_control", "water_system", "power_system", "other"]
    asset_category_display: str
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    production_year: int | None
    location_id: UUID | None
    location_breadcrumb: str
    criticality_code: Literal["low", "medium", "high", "critical"]
    lifecycle_status: Literal["planned", "active", "inactive", "retired", "archived"]
    lifecycle_status_display: str
    lifecycle_status_before_archive: str | None
    operational_status: Literal[
        "running", "warning", "fault", "under_maintenance", "out_of_service"
    ]
    operational_status_display: str
    operational_status_before_archive: str | None
    installed_at: str
    commissioned_at: str | None
    retired_at: str | None
    archived_at: str | None
    archive_reason: str | None
    ownership_type: Literal["owned", "leased", "managed"]
    ownership_type_display: str
    description: str | None
    warranty_start_date: str | None
    warranty_end_date: str | None
    warranty_provider: str | None
    warranty_reference: str | None
    created_at: str
    updated_at: str
    created_by_user_id: UUID | None
    updated_by_user_id: UUID | None
    version: int = Field(ge=1)
    qr_lookup_token: UUID


class AssetCatalogPage(BaseModel):
    """Paginated asset-management catalog."""

    items: list[AssetProfileResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class AssetCreateRequest(BaseModel):
    """Explicit fields accepted when registering an asset."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    asset_id: str = Field(
        min_length=2,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    asset_name: str = Field(min_length=2, max_length=200)
    asset_type: Literal["hvac", "pump", "generator"]
    asset_category: Literal["climate_control", "water_system", "power_system", "other"] = "other"
    manufacturer: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    serial_number: str | None = Field(default=None, max_length=150)
    production_year: int | None = Field(default=None, ge=1900, le=2200)
    location_id: UUID
    criticality: Literal["low", "medium", "high", "critical"]
    lifecycle_status: Literal["planned", "active", "inactive"] = "active"
    operational_status: Literal[
        "running", "warning", "fault", "under_maintenance", "out_of_service"
    ] = "running"
    installed_at: datetime
    commissioned_at: datetime | None = None
    ownership_type: Literal["owned", "leased", "managed"] = "owned"
    description: str | None = Field(default=None, max_length=4000)
    warranty_start_date: date | None = None
    warranty_end_date: date | None = None
    warranty_provider: str | None = Field(default=None, max_length=200)
    warranty_reference: str | None = Field(default=None, max_length=200)
    maintenance_interval_days: int = Field(gt=0, le=3650)
    last_maintenance_date: date
    next_maintenance_date: date

    @field_validator("installed_at", "commissioned_at")
    @classmethod
    def require_zoned_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Timestamp phải có timezone.")
        return value

    @model_validator(mode="after")
    def validate_chronology(self) -> "AssetCreateRequest":
        if self.commissioned_at and self.commissioned_at < self.installed_at:
            raise ValueError("commissioned_at không được sớm hơn installed_at.")
        if (
            self.warranty_start_date
            and self.warranty_end_date
            and self.warranty_end_date < self.warranty_start_date
        ):
            raise ValueError("warranty_end_date không được sớm hơn warranty_start_date.")
        if self.next_maintenance_date < self.last_maintenance_date:
            raise ValueError("next_maintenance_date không được sớm hơn last_maintenance_date.")
        return self


class AssetUpdateRequest(BaseModel):
    """Bounded asset profile update with optimistic version."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    asset_name: str | None = Field(default=None, min_length=2, max_length=200)
    asset_type: Literal["hvac", "pump", "generator"] | None = None
    asset_category: Literal["climate_control", "water_system", "power_system", "other"] | None = (
        None
    )
    manufacturer: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    serial_number: str | None = Field(default=None, max_length=150)
    production_year: int | None = Field(default=None, ge=1900, le=2200)
    location_id: UUID | None = None
    criticality: Literal["low", "medium", "high", "critical"] | None = None
    installed_at: datetime | None = None
    commissioned_at: datetime | None = None
    ownership_type: Literal["owned", "leased", "managed"] | None = None
    description: str | None = Field(default=None, max_length=4000)
    warranty_start_date: date | None = None
    warranty_end_date: date | None = None
    warranty_provider: str | None = Field(default=None, max_length=200)
    warranty_reference: str | None = Field(default=None, max_length=200)
    maintenance_interval_days: int | None = Field(default=None, gt=0, le=3650)
    last_maintenance_date: date | None = None
    next_maintenance_date: date | None = None

    @field_validator("installed_at", "commissioned_at")
    @classmethod
    def require_zoned_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Timestamp phải có timezone.")
        return value

    @model_validator(mode="after")
    def require_update(self) -> "AssetUpdateRequest":
        if not (self.model_fields_set - {"expected_version"}):
            raise ValueError("Cần cung cấp ít nhất một field để cập nhật.")
        return self


class OperationalStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operational_status: Literal[
        "running", "warning", "fault", "under_maintenance", "out_of_service"
    ]
    expected_version: int = Field(ge=1)


class LifecycleTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lifecycle_status: Literal["planned", "active", "inactive", "retired"]
    expected_version: int = Field(ge=1)


class AssetArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    archive_reason: str = Field(min_length=5, max_length=1000)
    expected_version: int = Field(ge=1)


class AssetRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    lifecycle_status: Literal["planned", "active", "inactive"] | None = None


class LocationRecord(BaseModel):
    id: UUID
    code: str
    name: str
    location_type: Literal["building", "floor", "room", "area", "plant"]
    location_type_display: str
    parent_id: UUID | None
    breadcrumb: str
    description: str | None
    is_active: bool
    asset_count: int = Field(ge=0)
    created_at: str
    updated_at: str
    version: int = Field(ge=1)


class LocationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=200)
    location_type: Literal["building", "floor", "room", "area", "plant"]
    parent_id: UUID | None = None
    description: str | None = Field(default=None, max_length=2000)


class LocationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    code: str | None = Field(
        default=None,
        min_length=2,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    name: str | None = Field(default=None, min_length=2, max_length=200)
    location_type: Literal["building", "floor", "room", "area", "plant"] | None = None
    parent_id: UUID | None = None
    description: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_update(self) -> "LocationUpdateRequest":
        if not (self.model_fields_set - {"expected_version"}):
            raise ValueError("Cần cung cấp ít nhất một field để cập nhật.")
        return self


class VersionedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class AssetAttachmentRecord(BaseModel):
    id: UUID
    asset_id: str
    category: Literal[
        "asset_photo",
        "technical_manual",
        "warranty_document",
        "commissioning_record",
        "inspection_document",
        "other",
    ]
    category_display: str
    original_filename: str
    media_type: Literal["application/pdf", "image/png", "image/jpeg"]
    size_bytes: int = Field(gt=0)
    checksum: str = Field(min_length=64, max_length=64)
    uploaded_by_user_id: UUID
    created_at: str
    deleted_at: str | None
    deleted_by_user_id: UUID | None
    storage_cleanup_pending: bool | None = None


class AssetQrResponse(BaseModel):
    asset_id: str
    lookup_token: UUID
    lookup_url: str
    svg_base64: str
    label_text: str


class AssetHistoryEvent(BaseModel):
    id: str
    occurred_at: str
    action: str
    event_type: str
    summary: str
    actor_user_id: UUID | None
    actor_display_name: str | None
    resource_type: str
    resource_id: str | None
    changed_fields: list[str]


class AssetHistoryPage(BaseModel):
    items: list[AssetHistoryEvent]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class AssetOption(BaseModel):
    code: str
    display_name: str


class AssetOptionsResponse(BaseModel):
    asset_types: list[AssetOption]
    asset_categories: list[AssetOption]
    criticalities: list[AssetOption]
    lifecycle_statuses: list[AssetOption]
    operational_statuses: list[AssetOption]
    ownership_types: list[AssetOption]
    location_types: list[AssetOption]
    attachment_categories: list[AssetOption]


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
    manager_note: str | None = None
    note: str | None = None


class TicketCreateRequest(BaseModel):
    """Fields accepted when a manager creates a local inspection ticket."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    asset_id: str = Field(min_length=1, max_length=50)
    issue_description: str = Field(min_length=5, max_length=1000)
    priority: Literal["Thấp", "Trung bình", "Cao", "Khẩn cấp"]
    failure_category: Literal[
        "Lỗi làm lạnh",
        "Lỗi rung động",
        "Lỗi điện",
        "Lỗi áp suất",
        "Lỗi thời gian vận hành",
        "Lỗi cảm biến",
        "Cảnh báo giả",
        "Không có lỗi",
    ]
    technician_id: str = Field(min_length=1, max_length=50)
    manager_note: str | None = Field(default=None, max_length=1000)


class TicketUpdateRequest(BaseModel):
    """Small set of mutable ticket fields for the portfolio workflow."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: Literal["Mới tạo", "Đang xử lý", "Đã xử lý"] | None = None
    priority: Literal["Thấp", "Trung bình", "Cao", "Khẩn cấp"] | None = None
    technician_id: str | None = Field(default=None, min_length=1, max_length=50)
    note: str | None = Field(default=None, max_length=1000)
    resolved_at: datetime | None = None

    @field_validator("resolved_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("resolved_at phải có timezone.")
        return value

    @model_validator(mode="after")
    def require_update(self) -> "TicketUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Cần cung cấp ít nhất một trường để cập nhật.")
        return self


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


class MaintenanceLogCreateRequest(BaseModel):
    """Technician result recorded against one inspection ticket."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ticket_id: str = Field(min_length=1, max_length=50)
    asset_id: str = Field(min_length=1, max_length=50)
    maintenance_date: date
    inspection_result: str = Field(min_length=3, max_length=2000)
    actions_taken: str = Field(min_length=3, max_length=2000)
    parts_replaced: str | None = Field(default=None, max_length=1000)
    technician_note: str = Field(min_length=1, max_length=2000)
    maintenance_result: Literal[
        "Đã xử lý",
        "Đã xử lý một phần",
        "Cần theo dõi",
        "Cần hỗ trợ chuyên môn",
    ]
    follow_up_required: bool
    next_maintenance_date: date

    @model_validator(mode="after")
    def validate_result_contract(self) -> "MaintenanceLogCreateRequest":
        if self.next_maintenance_date <= self.maintenance_date:
            raise ValueError("next_maintenance_date phải sau maintenance_date.")
        expected_follow_up = self.maintenance_result != "Đã xử lý"
        if self.follow_up_required != expected_follow_up:
            raise ValueError(
                "follow_up_required phải là false khi đã xử lý và true với kết quả khác."
            )
        return self


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


class ConversationContextRequest(BaseModel):
    """Bounded prior-turn facts; raw unbounded chat history is not accepted."""

    model_config = ConfigDict(extra="forbid")

    recent_intent: str | None = Field(default=None, max_length=40)
    resolved_asset_type: str | None = Field(default=None, max_length=80)
    resolved_failure_category: str | None = Field(default=None, max_length=80)
    previous_source_ids: list[str] = Field(default_factory=list, max_length=10)
    previous_answer_summary: str = Field(default="", max_length=600)


class CopilotAskRequest(BaseModel):
    """Request body for the grounded Maintenance Copilot."""

    question: str = Field(min_length=1, max_length=1000)
    asset_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    document_type: str | None = None
    failure_category: str | None = None
    version: str | None = Field(default=None, max_length=40)
    language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
    conversation_context: ConversationContextRequest | None = None


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
    response_mode: str = "deterministic_fallback"
    fallback_reason: str | None = None
    structured_answer: dict[str, Any] | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    evidence_status: str = "insufficient"
    citation_validation: dict[str, Any] | None = None
    context_warnings: list[str] = Field(default_factory=list)
    confidence: Literal[
        "high",
        "medium",
        "low",
        "insufficient_evidence",
        "not_applicable",
    ] = "insufficient_evidence"
