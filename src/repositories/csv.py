"""Explicit CSV compatibility adapter for demo fixtures and isolated tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.repositories.csv_writes import (
    CsvSchemaError,
    CsvWriteRepository,
    commit_csv_writes,
)
from src.repositories.contracts import StoredRecord
from src.security.audit import AuditContext

TICKET_REQUIRED_COLUMNS = {
    "ticket_id",
    "asset_id",
    "issue_description",
    "priority",
    "status",
    "failure_category",
    "created_at",
    "resolved_at",
    "technician_id",
}
MAINTENANCE_LOG_REQUIRED_COLUMNS = {
    "log_id",
    "ticket_id",
    "asset_id",
    "maintenance_date",
    "maintenance_type",
    "technician_id",
    "inspection_result",
    "actions_taken",
    "parts_replaced",
    "technician_note",
    "maintenance_result",
    "follow_up_required",
    "next_maintenance_date",
}
ASSET_REQUIRED_COLUMNS = {
    "asset_id",
    "asset_name",
    "asset_type",
    "location",
    "criticality",
    "status",
    "installation_date",
    "last_maintenance_date",
    "maintenance_interval_days",
    "next_maintenance_date",
}


class CsvMaintenanceRepository:
    """Keep the former single-user CSV workflow behind the repository contract."""

    backend_name = "csv"

    def __init__(
        self,
        *,
        asset_path: Path,
        ticket_path: Path,
        maintenance_log_path: Path,
    ) -> None:
        self.asset_path = asset_path
        self.ticket_path = ticket_path
        self.maintenance_log_path = maintenance_log_path

    def check_health(self) -> None:
        self._asset_frame()
        self._ticket_frame()
        self._maintenance_log_frame()

    def list_assets(self) -> list[StoredRecord]:
        return _stored_records(self._asset_frame())

    def get_asset(self, asset_id: str) -> StoredRecord | None:
        return _find_record(self._asset_frame(), "asset_id", asset_id)

    def list_tickets(self) -> list[StoredRecord]:
        return _stored_records(self._ticket_frame())

    def get_ticket(self, ticket_id: str) -> StoredRecord | None:
        return _find_record(self._ticket_frame(), "ticket_id", ticket_id)

    def create_ticket(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext | None = None,
    ) -> StoredRecord:
        del audit_context
        repository = CsvWriteRepository(
            self.ticket_path,
            id_column="ticket_id",
            required_columns=TICKET_REQUIRED_COLUMNS,
        )
        record = repository.append_generated(values, prefix="TCK")
        return StoredRecord(_ticket_values(record))

    def update_ticket(
        self,
        ticket_id: str,
        updates: dict[str, Any],
        *,
        expected_version: int | None,
        audit_context: AuditContext | None = None,
    ) -> StoredRecord:
        del expected_version, audit_context
        repository = CsvWriteRepository(
            self.ticket_path,
            id_column="ticket_id",
            required_columns=TICKET_REQUIRED_COLUMNS,
        )
        repository.update(ticket_id, updates)
        record = self.get_ticket(ticket_id)
        if record is None:  # pragma: no cover - guarded by CsvWriteRepository
            raise RuntimeError(f"Không tìm thấy ticket vừa cập nhật: {ticket_id}")
        return record

    def list_maintenance_logs(self) -> list[StoredRecord]:
        return _stored_records(self._maintenance_log_frame())

    def get_maintenance_log(self, log_id: str) -> StoredRecord | None:
        return _find_record(self._maintenance_log_frame(), "log_id", log_id)

    def snapshot(self) -> dict[str, list[StoredRecord]]:
        return {
            "assets": self.list_assets(),
            "maintenance_tickets": self.list_tickets(),
            "maintenance_logs": self.list_maintenance_logs(),
        }

    def create_maintenance_log(
        self,
        values: dict[str, Any],
        *,
        last_maintenance_date: date,
        next_maintenance_date: date,
        expected_asset_version: int | None,
        expected_ticket_version: int | None,
        audit_context: AuditContext | None = None,
    ) -> StoredRecord:
        del expected_asset_version, expected_ticket_version, audit_context
        log_repository = CsvWriteRepository(
            self.maintenance_log_path,
            id_column="log_id",
            required_columns=MAINTENANCE_LOG_REQUIRED_COLUMNS,
        )
        log_write = log_repository.prepare_append_generated(values, prefix="LOG")
        asset_repository = CsvWriteRepository(
            self.asset_path,
            id_column="asset_id",
            required_columns=ASSET_REQUIRED_COLUMNS,
        )
        asset_write = asset_repository.prepare_update(
            str(values["asset_id"]),
            {
                "last_maintenance_date": last_maintenance_date.isoformat(),
                "next_maintenance_date": next_maintenance_date.isoformat(),
            },
        )
        commit_csv_writes([log_write, asset_write])
        record = self.get_maintenance_log(log_write.record["log_id"])
        if record is None:  # pragma: no cover - guarded by atomic write
            raise RuntimeError(
                f"Không tìm thấy maintenance log vừa tạo: {log_write.record['log_id']}"
            )
        return record

    def _asset_frame(self) -> pd.DataFrame:
        frame = _read_csv(self.asset_path, ASSET_REQUIRED_COLUMNS)
        if not frame.empty:
            frame["maintenance_interval_days"] = pd.to_numeric(
                frame["maintenance_interval_days"], errors="raise"
            ).astype(int)
        return frame

    def _ticket_frame(self) -> pd.DataFrame:
        frame = _read_csv(self.ticket_path, TICKET_REQUIRED_COLUMNS)
        for column in ["manager_note", "note"]:
            if column not in frame.columns:
                frame[column] = None
            else:
                frame[column] = frame[column].map(_optional_text)
        if "resolved_at" in frame.columns:
            frame["resolved_at"] = frame["resolved_at"].map(_optional_text)
        return frame

    def _maintenance_log_frame(self) -> pd.DataFrame:
        frame = _read_csv(self.maintenance_log_path, MAINTENANCE_LOG_REQUIRED_COLUMNS)
        if "ticket_id" in frame.columns:
            frame["ticket_id"] = frame["ticket_id"].map(_optional_text)
        if "parts_replaced" in frame.columns:
            frame["parts_replaced"] = frame["parts_replaced"].map(_optional_text)
        if "follow_up_required" in frame.columns:
            frame["follow_up_required"] = frame["follow_up_required"].map(_as_bool)
        return frame


def _read_csv(path: Path, required_columns: set[str]) -> pd.DataFrame:
    if not path.exists():
        raise CsvSchemaError(f"Không tìm thấy nguồn dữ liệu {path.name}.")
    try:
        frame = pd.read_csv(path, keep_default_na=False)
    except (OSError, pd.errors.ParserError) as exc:
        raise CsvSchemaError(f"Không thể đọc nguồn dữ liệu {path.name}.") from exc
    missing = required_columns - set(frame.columns)
    if missing:
        raise CsvSchemaError(f"Nguồn {path.name} thiếu cột bắt buộc: {sorted(missing)}")
    return frame


def _stored_records(frame: pd.DataFrame) -> list[StoredRecord]:
    return [StoredRecord(_clean_values(row)) for row in frame.to_dict(orient="records")]


def _find_record(
    frame: pd.DataFrame,
    id_column: str,
    identifier: str,
) -> StoredRecord | None:
    matches = frame[frame[id_column].astype(str) == identifier]
    if matches.empty:
        return None
    return StoredRecord(_clean_values(matches.iloc[0].to_dict()))


def _ticket_values(record: dict[str, Any]) -> dict[str, Any]:
    values = _clean_values(record)
    values.setdefault("manager_note", None)
    values.setdefault("note", None)
    values["resolved_at"] = _optional_text(values.get("resolved_at"))
    return values


def _clean_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: None if value is None or (isinstance(value, float) and pd.isna(value)) else value
        for key, value in values.items()
    }


def _optional_text(value: object) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"Giá trị boolean không hợp lệ: {value!r}")
    return normalized == "true"
