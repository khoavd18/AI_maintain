from __future__ import annotations

from decimal import Decimal

from data_platform.domain_generator import (
    BASELINE_AVAILABLE_AT,
    _cost_values,
    _iter_movements,
    _stage9_work_order,
    _status_path,
    _third_ticket_event,
)


def test_status_paths_are_valid_and_end_in_current_status() -> None:
    expanded = {7}
    for index in (1, 2, 3, 7, 10, 100, 1_000):
        path = _status_path(index, expanded)
        assert path[0] == "planned"
        assert path[-1] == _stage9_work_order(index)["status"]
        assert all(left != right for left, right in zip(path, path[1:]))


def test_inventory_sequence_has_positive_quantity_and_nonnegative_stock() -> None:
    rows = list(_iter_movements(phase="baseline", start_part=1, end_part=1))
    incremental = list(_iter_movements(phase="incremental", start_part=1, end_part=1))

    assert len(rows) == 59
    assert len(incremental) == 1
    assert {row["id"] for row in rows}.isdisjoint({row["id"] for row in incremental})
    assert all(int(row["quantity"]) > 0 for row in rows + incremental)
    assert all(int(row["resulting_on_hand_quantity"]) >= 0 for row in rows + incremental)
    assert incremental[0]["movement_type"] == "receipt"


def test_cost_fixture_reconciles_exactly() -> None:
    for index in (1, 20, 1_000, 1_089_001, 1_100_000):
        row = _cost_values(index)
        estimated = Decimal(str(row["estimated_labor_cost"])) + Decimal(
            str(row["planned_part_cost"])
        )
        actual = (
            Decimal(str(row["actual_labor_cost"]))
            + Decimal(str(row["actual_part_cost"]))
            + Decimal(str(row["external_service_cost"]))
        )
        assert estimated == Decimal(str(row["total_estimated_cost"]))
        assert actual == Decimal(str(row["total_actual_cost"]))
        assert actual - estimated == Decimal(str(row["cost_variance"]))


def test_exact_escalation_selector_is_deterministic() -> None:
    kind, event = _third_ticket_event(4, available=BASELINE_AVAILABLE_AT)
    assert kind == "ticket_escalation_events"
    assert event["rule_code"] == "critical_priority"

    kind, event = _third_ticket_event(5, available=BASELINE_AVAILABLE_AT)
    assert kind == "ticket_sla_events"
    assert event["event_type"] == "first_response_recorded"
