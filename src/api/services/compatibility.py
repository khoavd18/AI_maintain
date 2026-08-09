"""Small compatibility façade for the historical ``ProcessedDataService`` API."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.asset_management.service import AssetManagementService
from src.repositories.contracts import MaintenanceRepository
from src.repositories.csv import CsvMaintenanceRepository
from src.security.audit import AuditContext

from .analytics_projection import AnalyticsProjectionService
from .analytics_snapshot import (
    ASSET_FILE,
    FEATURE_FILE,
    ANOMALY_FILE,
    RISK_FILE,
    TICKET_FILE,
    MAINTENANCE_LOG_FILE,
    PREVENTIVE_FILE,
    RECURRING_ISSUE_FILE,
    MAINTENANCE_KPI_FILE,
    AnalyticsSnapshotService,
)
from .asset_context import AssetContextQueryService
from src.composition.assets import build_asset_management_service
from .legacy_maintenance_adapter import LegacyMaintenanceAdapter
from .legacy_ticket_adapter import LegacyTicketAdapter

if TYPE_CHECKING:
    from src.security.principal import CurrentUser
    from src.ticket_management.service import TicketWorkflowService


class ProcessedDataService:
    """Preserve the old service surface while delegating to bounded services."""

    DEFAULT_TICKET_PATH = TICKET_FILE
    DEFAULT_MAINTENANCE_LOG_PATH = MAINTENANCE_LOG_FILE

    def __init__(
        self,
        feature_path: Path = FEATURE_FILE,
        anomaly_path: Path = ANOMALY_FILE,
        risk_path: Path = RISK_FILE,
        asset_path: Path = ASSET_FILE,
        ticket_path: Path = TICKET_FILE,
        maintenance_log_path: Path = MAINTENANCE_LOG_FILE,
        preventive_path: Path = PREVENTIVE_FILE,
        recurring_issue_path: Path = RECURRING_ISSUE_FILE,
        maintenance_kpi_path: Path = MAINTENANCE_KPI_FILE,
        repository: MaintenanceRepository | None = None,
        asset_management: AssetManagementService | None = None,
        ticket_workflow: "TicketWorkflowService | None" = None,
    ) -> None:
        self.repository = repository or CsvMaintenanceRepository(
            asset_path=asset_path,
            ticket_path=ticket_path,
            maintenance_log_path=maintenance_log_path,
        )
        self.ticket_workflow = ticket_workflow
        self.asset_management = asset_management or build_asset_management_service(self.repository)
        self.snapshot = AnalyticsSnapshotService(
            repository=self.repository,
            feature_path=feature_path,
            anomaly_path=anomaly_path,
            risk_path=risk_path,
            asset_path=asset_path,
            ticket_path=ticket_path,
            maintenance_log_path=maintenance_log_path,
            preventive_path=preventive_path,
            recurring_issue_path=recurring_issue_path,
            maintenance_kpi_path=maintenance_kpi_path,
        )
        self.analytics = AnalyticsProjectionService(self.snapshot)
        self.maintenance = LegacyMaintenanceAdapter(
            snapshot=self.snapshot,
            asset_queries=self.analytics,
        )
        self.tickets_adapter = LegacyTicketAdapter(
            snapshot=self.snapshot,
            asset_queries=self.analytics,
            asset_management=self.asset_management,
            ticket_workflow=self.ticket_workflow,
            maintenance_queries=self.maintenance,
        )
        self.asset_context = AssetContextQueryService(
            snapshot=self.snapshot,
            projections=self.analytics,
            tickets=self.tickets_adapter,
            maintenance_logs=self.maintenance,
        )

    @property
    def feature_path(self) -> Path:
        return self.snapshot.feature_path

    @feature_path.setter
    def feature_path(self, value: Path) -> None:
        self.snapshot.feature_path = value

    @property
    def anomaly_path(self) -> Path:
        return self.snapshot.anomaly_path

    @anomaly_path.setter
    def anomaly_path(self, value: Path) -> None:
        self.snapshot.anomaly_path = value

    @property
    def risk_path(self) -> Path:
        return self.snapshot.risk_path

    @risk_path.setter
    def risk_path(self, value: Path) -> None:
        self.snapshot.risk_path = value

    @property
    def asset_path(self) -> Path:
        return self.snapshot.asset_path

    @asset_path.setter
    def asset_path(self, value: Path) -> None:
        self.snapshot.asset_path = value

    @property
    def ticket_path(self) -> Path:
        return self.snapshot.ticket_path

    @ticket_path.setter
    def ticket_path(self, value: Path) -> None:
        self.snapshot.ticket_path = value

    @property
    def maintenance_log_path(self) -> Path:
        return self.snapshot.maintenance_log_path

    @maintenance_log_path.setter
    def maintenance_log_path(self, value: Path) -> None:
        self.snapshot.maintenance_log_path = value

    @property
    def preventive_path(self) -> Path:
        return self.snapshot.preventive_path

    @preventive_path.setter
    def preventive_path(self, value: Path) -> None:
        self.snapshot.preventive_path = value

    @property
    def recurring_issue_path(self) -> Path:
        return self.snapshot.recurring_issue_path

    @recurring_issue_path.setter
    def recurring_issue_path(self, value: Path) -> None:
        self.snapshot.recurring_issue_path = value

    @property
    def maintenance_kpi_path(self) -> Path:
        return self.snapshot.maintenance_kpi_path

    @maintenance_kpi_path.setter
    def maintenance_kpi_path(self, value: Path) -> None:
        self.snapshot.maintenance_kpi_path = value

    @property
    def assets(self):
        return self.snapshot.assets

    @property
    def tickets(self):
        return self.snapshot.tickets

    @property
    def maintenance_logs(self):
        return self.snapshot.maintenance_logs

    @property
    def features(self):
        return self.snapshot.features

    @property
    def anomalies(self):
        return self.snapshot.anomalies

    @property
    def risks(self):
        return self.snapshot.risks

    @property
    def preventive_status(self):
        return self.snapshot.preventive_status

    @property
    def recurring_issues(self):
        return self.snapshot.recurring_issues

    @property
    def maintenance_kpis(self):
        return self.snapshot.maintenance_kpis

    def get_health(self) -> dict[str, object]:
        return self.snapshot.get_health()

    def get_summary(self) -> dict[str, Any]:
        return self.analytics.get_summary()

    def list_assets(
        self,
        asset_type: str | None = None,
        location: str | None = None,
        criticality: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.analytics.list_assets(
            asset_type=asset_type,
            location=location,
            criticality=criticality,
            status=status,
        )

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        return self.analytics.get_asset(asset_id)

    def list_risks(
        self,
        risk_level: str | None = None,
        asset_type: str | None = None,
        location: str | None = None,
        date: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self.analytics.list_risks(
            risk_level=risk_level,
            asset_type=asset_type,
            location=location,
            date=date,
            limit=limit,
        )

    def list_top_risks(self, limit: int = 10, date: str | None = None) -> list[dict[str, Any]]:
        return self.analytics.list_top_risks(limit=limit, date=date)

    def get_asset_risk_history(self, asset_id: str) -> list[dict[str, Any]]:
        return self.analytics.get_asset_risk_history(asset_id)

    def list_anomalies(
        self,
        asset_type: str | None = None,
        anomaly_type: str | None = None,
        date: str | None = None,
        only_anomalies: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.analytics.list_anomalies(
            asset_type=asset_type,
            anomaly_type=anomaly_type,
            date=date,
            only_anomalies=only_anomalies,
            limit=limit,
        )

    def get_asset_anomaly_history(self, asset_id: str) -> list[dict[str, Any]]:
        return self.analytics.get_asset_anomaly_history(asset_id)

    def list_preventive_maintenance(
        self,
        maintenance_status: str | None = None,
        asset_type: str | None = None,
        criticality: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.analytics.list_preventive_maintenance(
            maintenance_status=maintenance_status,
            asset_type=asset_type,
            criticality=criticality,
        )

    def list_recurring_issues(
        self,
        asset_id: str | None = None,
        failure_category: str | None = None,
        recurrence_flag: bool | None = None,
    ) -> list[dict[str, Any]]:
        return self.analytics.list_recurring_issues(
            asset_id=asset_id,
            failure_category=failure_category,
            recurrence_flag=recurrence_flag,
        )

    def get_maintenance_kpis(self) -> dict[str, Any]:
        return self.analytics.get_maintenance_kpis()

    def list_tickets(
        self,
        asset_id: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        failure_category: str | None = None,
        technician_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.tickets_adapter.list_tickets(
            asset_id=asset_id,
            status=status,
            priority=priority,
            failure_category=failure_category,
            technician_id=technician_id,
            limit=limit,
        )

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        return self.tickets_adapter.get_ticket(ticket_id)

    def list_maintenance_logs(
        self,
        asset_id: str | None = None,
        maintenance_result: str | None = None,
        follow_up_required: bool | None = None,
        technician_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.maintenance.list_maintenance_logs(
            asset_id=asset_id,
            maintenance_result=maintenance_result,
            follow_up_required=follow_up_required,
            technician_id=technician_id,
            limit=limit,
        )

    def create_ticket(
        self,
        *,
        asset_id: str,
        issue_description: str,
        priority: str,
        failure_category: str,
        technician_id: str,
        manager_note: str | None = None,
        audit_context: AuditContext | None = None,
        actor: "CurrentUser | None" = None,
    ) -> dict[str, Any]:
        return self.tickets_adapter.create_ticket(
            asset_id=asset_id,
            issue_description=issue_description,
            priority=priority,
            failure_category=failure_category,
            technician_id=technician_id,
            manager_note=manager_note,
            audit_context=audit_context,
            actor=actor,
        )

    def update_ticket(
        self,
        ticket_id: str,
        updates: dict[str, Any],
        audit_context: AuditContext | None = None,
        actor: "CurrentUser | None" = None,
    ) -> dict[str, Any]:
        return self.tickets_adapter.update_ticket(
            ticket_id,
            updates,
            audit_context=audit_context,
            actor=actor,
        )

    def create_maintenance_log(
        self,
        *,
        ticket_id: str,
        asset_id: str,
        maintenance_date: date,
        inspection_result: str,
        actions_taken: str,
        parts_replaced: str | None,
        technician_note: str,
        maintenance_result: str,
        follow_up_required: bool,
        next_maintenance_date: date,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        return self.maintenance.create_maintenance_log(
            ticket_id=ticket_id,
            asset_id=asset_id,
            maintenance_date=maintenance_date,
            inspection_result=inspection_result,
            actions_taken=actions_taken,
            parts_replaced=parts_replaced,
            technician_note=technician_note,
            maintenance_result=maintenance_result,
            follow_up_required=follow_up_required,
            next_maintenance_date=next_maintenance_date,
            audit_context=audit_context,
        )

    def get_asset_details(self, asset_id: str, limit: int = 10) -> dict[str, Any]:
        return self.asset_context.get_asset_details(asset_id, limit=limit)

    def get_asset_context(self, asset_id: str, limit: int = 10) -> dict[str, Any]:
        return self.asset_context.get_asset_context(asset_id, limit=limit)

    def _analytics_paths(self) -> list[Path]:
        return self.snapshot._analytics_paths()

    def _analytics_available(self) -> bool:
        return self.snapshot._analytics_available()

    def _ensure_analytics_current(self) -> None:
        self.snapshot.ensure_analytics_current()

    def _analytics_dates_are_current(self) -> bool:
        return self.snapshot._analytics_dates_are_current()

    def _get_asset_record(self, asset_id: str):
        return self.analytics._get_asset_record(asset_id)

    def _get_ticket_stored_record(self, ticket_id: str):
        return self.tickets_adapter._get_ticket_stored_record(ticket_id)

    def _get_ticket_record(self, ticket_id: str) -> dict[str, Any]:
        return self.tickets_adapter.get_ticket(ticket_id)

    def _get_maintenance_log_record(self, log_id: str) -> dict[str, Any]:
        return self.maintenance._get_maintenance_log_record(log_id)
