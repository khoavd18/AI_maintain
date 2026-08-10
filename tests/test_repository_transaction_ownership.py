"""Static guard for transaction-heavy repository ownership retained by design."""

from __future__ import annotations

import ast
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]

FAMILIES = {
    "src/repositories/postgres_inventory.py": {
        "transfer_stock": {"_locked_positions", "_movement_record", "_audit"},
        "reserve_stock": {"_locked_position", "_reservation_event", "_audit"},
        "issue_stock": {
            "_locked_position",
            "_new_movement",
            "_reservation_event",
            "_audit",
            "enqueue_outbox_event",
        },
    },
    "src/repositories/postgres_maintenance.py": {
        "complete_work_order": {"_audit", "enqueue_outbox_event"},
        "generate_plan_occurrences": {"_audit", "enqueue_outbox_event"},
    },
    "src/repositories/postgres_tickets.py": {
        "mutate_ticket": {"_append_sla_events", "_audit", "enqueue_outbox_event"},
        "record_escalations": {"_audit", "enqueue_outbox_event"},
    },
    "src/repositories/postgres_operations.py": {
        "claim_execution": {"with_for_update"},
        "complete_execution": {"_locked_running_execution"},
        "claim_outbox_event": {"with_for_update"},
    },
}


def _call_names(function: ast.FunctionDef) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            result.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            result.add(node.func.attr)
    return result


def test_atomic_mutation_families_retain_session_and_transaction_ownership() -> None:
    for relative_path, expected_methods in FAMILIES.items():
        tree = ast.parse(
            (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8"),
            filename=relative_path,
        )
        methods = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        for method_name, required_calls in expected_methods.items():
            assert method_name in methods, f"{relative_path} lost {method_name}"
            calls = _call_names(methods[method_name])
            assert {"session_factory", "begin"}.issubset(calls), (
                f"{relative_path}:{method_name} no longer owns one repository transaction"
            )
            assert required_calls.issubset(calls), (
                f"{relative_path}:{method_name} split lock/history/audit/outbox ownership"
            )


def test_application_capability_modules_do_not_acquire_repository_sessions_or_row_locks() -> None:
    application_roots = (
        REPOSITORY_ROOT / "src" / "inventory_management" / "application",
        REPOSITORY_ROOT / "src" / "maintenance_management" / "application",
        REPOSITORY_ROOT / "src" / "ticket_management" / "application",
    )
    violations: dict[str, set[str]] = {}
    forbidden = {"session_factory", "begin", "with_for_update", "commit", "rollback"}
    for root in application_roots:
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            observed = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
            if observed.intersection(forbidden):
                violations[str(path.relative_to(REPOSITORY_ROOT))] = observed.intersection(
                    forbidden
                )
    assert violations == {}
