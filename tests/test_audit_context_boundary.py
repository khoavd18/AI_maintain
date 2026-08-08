from pathlib import Path
from uuid import uuid4

from src.security.audit import AuditContext as CompatibilityAuditContext
from src.security.audit_context import AuditContext


def test_audit_context_compatibility_export_preserves_value_behavior() -> None:
    context = AuditContext(uuid4(), "Người vận hành", "request-001")

    assert CompatibilityAuditContext is AuditContext
    assert context == AuditContext(
        actor_user_id=context.actor_user_id,
        actor_display_name="Người vận hành",
        request_id="request-001",
    )


def test_repository_contracts_import_only_the_pure_audit_context() -> None:
    contracts_root = Path("src/repositories/contracts")

    for path in contracts_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "from src.security.audit import AuditContext" not in source
        assert "from src.security.audit_context import AuditContext" in source or path.name == "shared.py"
