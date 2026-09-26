"""Closed domain catalogue for the multi-domain ELT workflow."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DomainSpec:
    """Source, raw, identity, and warehouse contract for one domain."""

    source_view: str
    raw_table: str
    columns: tuple[str, ...]
    identity_column: str
    warehouse_relation: str


DOMAIN_SPECS = {
    "work_order_status_history": DomainSpec(
        "analytics_source.work_order_status_history",
        "raw.work_order_status_history",
        (
            "event_id",
            "work_order_id",
            "work_order_number",
            "site_id",
            "asset_id",
            "sequence_number",
            "status",
            "transitioned_at",
            "next_transitioned_at",
            "is_late_arriving",
            "source_available_at",
        ),
        "event_id",
        "analytics_warehouse.fact_work_order_status_duration",
    ),
    "tickets": DomainSpec(
        "analytics_source.tickets",
        "raw.tickets",
        (
            "ticket_id",
            "asset_id",
            "site_id",
            "work_order_id",
            "severity",
            "priority",
            "status",
            "category",
            "issue_description",
            "assigned_user_id",
            "technician_id",
            "opened_at",
            "first_response_at",
            "resolved_at",
            "closed_at",
            "resolution_summary",
            "technician_note",
            "reopen_count",
            "source_available_at",
        ),
        "ticket_id",
        "analytics_warehouse.fact_ticket_sla",
    ),
    "ticket_events": DomainSpec(
        "analytics_source.ticket_events",
        "raw.ticket_events",
        (
            "event_id",
            "ticket_id",
            "event_domain",
            "event_type",
            "clock_type",
            "occurrence_number",
            "occurred_at",
            "details",
            "created_by_user_id",
            "source_available_at",
        ),
        "event_id",
        "analytics_warehouse.fact_ticket_sla",
    ),
    "spare_parts": DomainSpec(
        "analytics_source.spare_parts",
        "raw.spare_parts",
        (
            "part_id",
            "part_number",
            "part_name",
            "category_id",
            "category_code",
            "unit_of_measure_id",
            "unit_code",
            "lifecycle_status",
            "minimum_stock",
            "reorder_point",
            "maximum_stock",
            "unit_cost",
            "currency_code",
            "source_available_at",
        ),
        "part_id",
        "analytics_warehouse.dim_spare_part",
    ),
    "inventory_movements": DomainSpec(
        "analytics_source.inventory_movements",
        "raw.inventory_movements",
        (
            "movement_id",
            "movement_number",
            "operation_id",
            "part_id",
            "stock_location_id",
            "quantity",
            "movement_type",
            "business_reference",
            "actor_user_id",
            "occurred_at",
            "work_order_id",
            "unit_cost_snapshot",
            "resulting_on_hand_quantity",
            "resulting_reserved_quantity",
            "source_available_at",
        ),
        "movement_id",
        "analytics_warehouse.fact_inventory_movement",
    ),
    "work_order_costs": DomainSpec(
        "analytics_source.work_order_costs",
        "raw.work_order_costs",
        (
            "work_order_id",
            "work_order_number",
            "site_id",
            "asset_id",
            "estimated_labor_cost",
            "actual_labor_cost",
            "planned_part_cost",
            "actual_part_cost",
            "external_service_cost",
            "total_estimated_cost",
            "total_actual_cost",
            "cost_variance",
            "currency_code",
            "source_available_at",
        ),
        "work_order_id",
        "analytics_warehouse.fact_work_order_cost",
    ),
}

DOMAINS = tuple(DOMAIN_SPECS)


def domain_spec(domain: str) -> DomainSpec:
    """Return the closed contract for ``domain`` or fail safely."""

    try:
        return DOMAIN_SPECS[domain]
    except KeyError:
        raise ValueError(f"Unsupported Stage 10 domain: {domain!r}") from None
