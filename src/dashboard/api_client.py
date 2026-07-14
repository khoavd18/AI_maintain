"""Small FastAPI client helpers for the Streamlit dashboard."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx
import pandas as pd

DEFAULT_API_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT_SECONDS = 10.0


class ApiClientError(RuntimeError):
    """Raised when the dashboard cannot read from the FastAPI backend."""


@dataclass(frozen=True)
class MaintenanceApiClient:
    """HTTP client for the CSV-backed maintenance intelligence API."""

    base_url: str = DEFAULT_API_BASE_URL
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    transport: httpx.BaseTransport | None = None

    def health(self) -> dict[str, Any]:
        """Return API health payload."""

        return self._get_object("/health")

    def get_summary(self) -> dict[str, Any]:
        """Return current maintenance summary metrics."""

        return self._get_object("/summary")

    def list_assets(
        self,
        *,
        asset_type: str | None = None,
        location: str | None = None,
        criticality: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return asset master rows enriched with latest analytics."""

        return self._get_records(
            "/assets",
            params={
                "asset_type": asset_type,
                "location": location,
                "criticality": criticality,
                "status": status,
            },
        )

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        """Return one asset master record."""

        return self._get_object(f"/assets/{asset_id}")

    def get_asset_details(self, asset_id: str, *, limit: int = 10) -> dict[str, Any]:
        """Return the consolidated manager-facing asset payload."""

        return self._get_object(
            f"/assets/{asset_id}/details",
            params={"limit": limit},
        )

    def list_risks(
        self,
        *,
        risk_level: str | None = None,
        asset_type: str | None = None,
        location: str | None = None,
        date: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return risk records from the API."""

        return self._get_records(
            "/assets/risk",
            params={
                "risk_level": risk_level,
                "asset_type": asset_type,
                "location": location,
                "date": date,
                "limit": limit,
            },
        )

    def list_top_risks(
        self,
        *,
        limit: int = 10,
        date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return top risky assets from the API."""

        return self._get_records(
            "/assets/risk/top",
            params={
                "limit": limit,
                "date": date,
            },
        )

    def get_asset_risk_history(self, asset_id: str) -> list[dict[str, Any]]:
        """Return risk history for one asset."""

        return self._get_records(f"/assets/risk/{asset_id}")

    def list_anomalies(
        self,
        *,
        asset_type: str | None = None,
        anomaly_type: str | None = None,
        date: str | None = None,
        only_anomalies: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return anomaly records from the API."""

        return self._get_records(
            "/assets/anomalies",
            params={
                "asset_type": asset_type,
                "anomaly_type": anomaly_type,
                "date": date,
                "only_anomalies": only_anomalies,
                "limit": limit,
            },
        )

    def get_asset_anomaly_history(self, asset_id: str) -> list[dict[str, Any]]:
        """Return anomaly history for one asset."""

        return self._get_records(f"/assets/anomalies/{asset_id}")

    def get_asset_context(self, asset_id: str) -> dict[str, Any]:
        """Return combined risk, anomaly, feature, and recommendation context."""

        return self._get_object(f"/assets/{asset_id}/context")

    def list_preventive_maintenance(
        self,
        *,
        maintenance_status: str | None = None,
        asset_type: str | None = None,
        criticality: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return preventive maintenance status rows."""

        return self._get_records(
            "/maintenance/preventive",
            params={
                "maintenance_status": maintenance_status,
                "asset_type": asset_type,
                "criticality": criticality,
            },
        )

    def list_recurring_issues(
        self,
        *,
        asset_id: str | None = None,
        failure_category: str | None = None,
        recurrence_flag: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Return recurring ticket groups."""

        return self._get_records(
            "/maintenance/recurring-issues",
            params={
                "asset_id": asset_id,
                "failure_category": failure_category,
                "recurrence_flag": recurrence_flag,
            },
        )

    def get_maintenance_kpis(self) -> dict[str, Any]:
        """Return the current maintenance KPI snapshot."""

        return self._get_object("/maintenance/kpis")

    def list_tickets(
        self,
        *,
        asset_id: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        failure_category: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return filtered maintenance tickets."""

        return self._get_records(
            "/tickets",
            params={
                "asset_id": asset_id,
                "status": status,
                "priority": priority,
                "failure_category": failure_category,
                "limit": limit,
            },
        )

    def list_maintenance_logs(
        self,
        *,
        asset_id: str | None = None,
        maintenance_result: str | None = None,
        follow_up_required: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return filtered maintenance logs."""

        return self._get_records(
            "/maintenance/logs",
            params={
                "asset_id": asset_id,
                "maintenance_result": maintenance_result,
                "follow_up_required": follow_up_required,
                "limit": limit,
            },
        )

    def ask_copilot(
        self,
        *,
        question: str,
        asset_id: str | None = None,
        top_k: int = 5,
        document_type: str | None = None,
        failure_category: str | None = None,
    ) -> dict[str, Any]:
        """Ask the RAG Maintenance Copilot."""

        return self._post_object(
            "/copilot/ask",
            json={
                "question": question,
                "asset_id": asset_id,
                "top_k": top_k,
                "document_type": document_type,
                "failure_category": failure_category,
            },
        )

    def _get_records(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        payload = self._get(path, params=params)
        if not isinstance(payload, list):
            raise ApiClientError(f"Expected a list response from {path}.")
        return [record for record in payload if isinstance(record, dict)]

    def _get_object(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._get(path, params=params)
        if not isinstance(payload, dict):
            raise ApiClientError(f"Expected an object response from {path}.")
        return payload

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url.rstrip('/')}{path}"
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.get(url, params=_clean_params(params or {}))
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            detail = _extract_error_detail(exc.response)
            raise ApiClientError(
                f"API request failed with status {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise ApiClientError(f"Could not connect to API at {self.base_url}: {exc}") from exc
        except ValueError as exc:
            raise ApiClientError("API response was not valid JSON.") from exc

    def _post_object(
        self,
        path: str,
        json: dict[str, Any],
    ) -> dict[str, Any]:
        payload = self._post(path, json=json)
        if not isinstance(payload, dict):
            raise ApiClientError(f"Expected an object response from {path}.")
        return payload

    def _post(self, path: str, json: dict[str, Any]) -> Any:
        url = f"{self.base_url.rstrip('/')}{path}"
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(url, json=_clean_params(json))
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            detail = _extract_error_detail(exc.response)
            raise ApiClientError(
                f"API request failed with status {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise ApiClientError(f"Could not connect to API at {self.base_url}: {exc}") from exc
        except ValueError as exc:
            raise ApiClientError("API response was not valid JSON.") from exc


def get_api_base_url() -> str:
    """Read the dashboard API base URL from the environment."""

    return os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")


def records_to_dataframe(records: list[dict[str, Any]] | dict[str, Any] | None) -> pd.DataFrame:
    """Convert API JSON records into a DataFrame for Streamlit display."""

    if records is None:
        return pd.DataFrame()
    if isinstance(records, dict):
        records = [records]
    return pd.DataFrame(records)


def _clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text
    if isinstance(payload, dict) and "detail" in payload:
        return str(payload["detail"])
    return str(payload)
