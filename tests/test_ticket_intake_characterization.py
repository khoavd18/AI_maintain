from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.repositories.contracts import StoredRecord
from src.security.audit_context import AuditContext
from src.security.permissions import Role
from src.ticket_management.errors import TicketNotFoundError
from src.ticket_management.service import TicketWorkflowService
from tests.auth_helpers import build_test_user


class _AssetFirstRepository:
    backend_name = "stub"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_asset(self, asset_id: str) -> StoredRecord | None:
        self.calls.append(f"asset:{asset_id}")
        return None


def test_intake_validates_asset_before_reference_ids() -> None:
    repository = _AssetFirstRepository()
    service = TicketWorkflowService(repository)  # type: ignore[arg-type]
    actor = build_test_user(Role.HELPDESK)
    context = AuditContext(actor.id, actor.display_name, "intake-order")

    with pytest.raises(TicketNotFoundError, match="asset"):
        service.intake(
            {
                "asset_id": "ASSET-MISSING",
                "issue_description": "A valid description",
                "category_id": "not-a-uuid",
                "impact": "high",
                "urgency": "immediate",
            },
            actor=actor,
            audit_context=context,
            now=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )

    assert repository.calls == ["asset:ASSET-MISSING"]


def test_intake_application_service_has_no_persistence_implementation_dependency() -> None:
    source = Path(
        "src/ticket_management/application/intake_service.py"
    ).read_text(encoding="utf-8")

    assert "sqlalchemy" not in source.lower()
    assert "session_factory" not in source
    assert "create_ticket" in source
