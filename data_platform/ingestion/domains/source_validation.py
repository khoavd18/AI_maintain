"""Read-only source counts and integrity gates for domain ingestion."""

from __future__ import annotations

from data_platform.config import DataPlatformSettings
from data_platform.database import connect


def domain_source_counts(settings: DataPlatformSettings | None = None) -> dict[str, int]:
    """Return exact unique source counts from the isolated scale database."""

    resolved = (settings or DataPlatformSettings.from_env()).validated()
    with connect(resolved, read_only=True) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM public.work_orders),
                (SELECT count(*) FROM analytics_compat.work_order_status_history),
                (SELECT count(*) FROM public.maintenance_tickets),
                (
                    (SELECT count(*) FROM public.ticket_sla_events)
                    + (SELECT count(*) FROM public.ticket_escalation_events)
                ),
                (SELECT count(*) FROM public.spare_parts),
                (SELECT count(*) FROM public.inventory_movements),
                (SELECT count(*) FROM analytics_compat.work_order_cost_facts)
            """
        ).fetchone()
    if row is None:
        raise RuntimeError("Stage 10 count query returned no row.")
    keys = (
        "work_orders",
        "work_order_status_history",
        "tickets",
        "ticket_events",
        "spare_parts",
        "inventory_movements",
        "work_order_costs",
    )
    return dict(zip(keys, map(int, row), strict=True))


def validate_domain_integrity(
    settings: DataPlatformSettings | None = None,
) -> dict[str, int]:
    """Return zero-valued integrity checks or fail with their exact counts."""

    resolved = (settings or DataPlatformSettings.from_env()).validated()
    queries = {
        "status_final_mismatch": """
            SELECT count(*) FROM (
                SELECT DISTINCT ON (h.work_order_id) h.work_order_id, h.status
                FROM analytics_compat.work_order_status_history h
                ORDER BY h.work_order_id, h.sequence_number DESC
            ) latest
            JOIN public.work_orders w ON w.id = latest.work_order_id
            WHERE latest.status <> w.status
        """,
        "status_consecutive_duplicates": """
            SELECT count(*) FROM (
                SELECT status, lag(status) OVER (
                    PARTITION BY work_order_id ORDER BY sequence_number
                ) AS prior_status
                FROM analytics_compat.work_order_status_history
            ) x WHERE status = prior_status
        """,
        "status_negative_duration": """
            SELECT count(*) FROM (
                SELECT transitioned_at, lead(transitioned_at) OVER (
                    PARTITION BY work_order_id ORDER BY sequence_number
                ) AS next_at
                FROM analytics_compat.work_order_status_history
            ) x WHERE next_at < transitioned_at
        """,
        "ticket_resolution_evidence": """
            SELECT count(*) FROM public.maintenance_tickets
            WHERE status IN ('resolved', 'closed')
              AND (resolved_at IS NULL OR nullif(btrim(manager_note), '') IS NULL)
        """,
        "ticket_orphan_events": """
            SELECT count(*) FROM analytics_source.ticket_events e
            LEFT JOIN public.maintenance_tickets t ON t.ticket_id = e.ticket_id
            WHERE t.ticket_id IS NULL
        """,
        "inventory_operation_mismatch": """
            SELECT abs(
                (SELECT count(*) FROM public.inventory_movements)
                - (SELECT count(*) FROM public.inventory_operations)
            )
        """,
        "inventory_invalid_balance": """
            SELECT count(*) FROM public.inventory_positions
            WHERE on_hand_quantity < 0 OR reserved_quantity < 0
               OR reserved_quantity > on_hand_quantity
        """,
        "cost_reconciliation": """
            SELECT count(*) FROM analytics_compat.work_order_cost_facts
            WHERE total_estimated_cost <> estimated_labor_cost + planned_part_cost
               OR total_actual_cost <> actual_labor_cost + actual_part_cost
                    + external_service_cost
               OR cost_variance <> total_actual_cost - total_estimated_cost
        """,
    }
    results: dict[str, int] = {}
    with connect(resolved, read_only=True) as connection:
        for name, statement in queries.items():
            row = connection.execute(statement).fetchone()
            results[name] = int(row[0]) if row else -1
    violations = {name: count for name, count in results.items() if count != 0}
    if violations:
        raise RuntimeError(f"Stage 10 integrity violations: {violations}")
    return results
