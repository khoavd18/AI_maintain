"""Unit tests for deterministic inventory quantity and stock-state rules."""

from decimal import Decimal

from src.inventory_management.domain import (
    StockState,
    available_quantity,
    derive_stock_state,
    reorder_suggestion,
)


def test_available_quantity_is_on_hand_less_reserved() -> None:
    assert available_quantity(Decimal("12.500"), Decimal("3.250")) == Decimal(
        "9.250"
    )


def test_stock_state_precedence_is_deterministic() -> None:
    common = {
        "minimum_stock": Decimal("3"),
        "reorder_point": Decimal("5"),
        "maximum_stock": Decimal("20"),
    }
    assert (
        derive_stock_state(
            on_hand=Decimal("4"),
            reserved=Decimal("4"),
            **common,
        )
        is StockState.OUT_OF_STOCK
    )
    assert (
        derive_stock_state(
            on_hand=Decimal("4"),
            reserved=Decimal("2"),
            **common,
        )
        is StockState.LOW_STOCK
    )
    assert (
        derive_stock_state(
            on_hand=Decimal("6"),
            reserved=Decimal("1"),
            **common,
        )
        is StockState.AT_REORDER_POINT
    )
    assert (
        derive_stock_state(
            on_hand=Decimal("21"),
            reserved=Decimal("0"),
            **common,
        )
        is StockState.OVERSTOCK
    )
    assert (
        derive_stock_state(
            on_hand=Decimal("10"),
            reserved=Decimal("1"),
            **common,
        )
        is StockState.HEALTHY
    )


def test_reorder_suggestion_uses_configured_target() -> None:
    assert reorder_suggestion(
        available=Decimal("4"),
        reorder_point=Decimal("5"),
        maximum_stock=Decimal("12"),
    ) == Decimal("8")
    assert reorder_suggestion(
        available=Decimal("6"),
        reorder_point=Decimal("5"),
        maximum_stock=Decimal("12"),
    ) == Decimal("0")
    assert reorder_suggestion(
        available=Decimal("2"),
        reorder_point=Decimal("5"),
        maximum_stock=None,
    ) == Decimal("3")
