"""Checklist-template application operations for maintenance."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from src.maintenance_management.errors import MaintenanceConflictError, MaintenanceNotFoundError
from src.repositories.contracts import MaintenancePlanningRepository, StoredPage
from src.security.audit import AuditContext
from src.security.principal import CurrentUser


class MaintenanceTemplateService:
    """Own immutable checklist-template versions and repository command mapping."""

    def __init__(
        self,
        repository_provider: Callable[[], MaintenancePlanningRepository],
        normalized_code: Callable[..., str],
        plain_text: Callable[..., str],
        optional_plain_text: Callable[..., str | None],
        validate_items: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
        page_values: Callable[[StoredPage], dict[str, Any]],
    ) -> None:
        self._repository_provider = repository_provider
        self._normalized_code = normalized_code
        self._plain_text = plain_text
        self._optional_plain_text = optional_plain_text
        self._validate_items = validate_items
        self._page_values = page_values

    def list_templates(
        self,
        *,
        status: str | None,
        asset_type: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        page_result = self._repository_provider().list_templates(
            filters={"status": status, "asset_type": asset_type, "search": search},
            page=page,
            page_size=page_size,
        )
        return self._page_values(page_result)

    def get_template(self, template_id: UUID) -> dict[str, Any]:
        record = self._repository_provider().get_template(template_id)
        if record is None:
            raise MaintenanceNotFoundError(
                f"Không tìm thấy checklist template: {template_id}"
            )
        return dict(record.values)

    def create_template(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        code = self._normalized_code(request["code"], "code")
        items = self._validate_items(request["items"])
        values = {
            "code": code,
            "name": self._plain_text(request["name"], "name", max_length=200),
            "asset_type": request.get("asset_type"),
            "description": self._optional_plain_text(
                request.get("description"), "description", max_length=2000
            ),
            "version_number": 1,
            "status": "active",
            "created_by_user_id": actor.id,
            "archived_at": None,
        }
        return dict(
            self._repository_provider()
            .create_template(
                values,
                items,
                audit_action="checklist_template.created",
                audit_context=audit_context,
            )
            .values
        )

    def version_template(
        self,
        template_id: UUID,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        source = self.get_template(template_id)
        page = self._repository_provider().list_templates(
            filters={"search": source["code"]}, page=1, page_size=100
        )
        latest_version = max(
            int(item.values["version_number"])
            for item in page.items
            if item.values["code"] == source["code"]
        )
        raw_items = request.get("items") or [
            {
                key: item[key]
                for key in (
                    "sequence",
                    "instruction",
                    "response_type",
                    "is_required",
                    "safety_critical",
                    "allow_not_applicable",
                    "expected_unit",
                    "minimum_value",
                    "maximum_value",
                    "guidance",
                )
            }
            for item in source["items"]
        ]
        values = {
            "code": source["code"],
            "name": self._plain_text(
                request.get("name") or source["name"], "name", max_length=200
            ),
            "asset_type": request.get("asset_type", source["asset_type"]),
            "description": self._optional_plain_text(
                request.get("description", source["description"]),
                "description",
                max_length=2000,
            ),
            "version_number": latest_version + 1,
            "status": "active",
            "created_by_user_id": actor.id,
            "archived_at": None,
        }
        return dict(
            self._repository_provider()
            .create_template(
                values,
                self._validate_items(raw_items),
                audit_action="checklist_template.versioned",
                audit_context=audit_context,
            )
            .values
        )

    def archive_template(
        self,
        template_id: UUID,
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self.get_template(template_id)
        if current["status"] == "archived":
            raise MaintenanceConflictError("Checklist template đã được archive.")
        return dict(
            self._repository_provider()
            .archive_template(
                template_id,
                expected_version=expected_version,
                audit_context=audit_context,
            )
            .values
        )
