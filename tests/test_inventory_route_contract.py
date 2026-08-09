from __future__ import annotations

from fastapi.routing import APIRoute

from src.inventory_management.routes import (
    attachments,
    catalogue,
    reservations,
    stock,
    work_order_parts,
)


def test_inventory_route_modules_preserve_the_historical_contract() -> None:
    expected = [
        ("/inventory/options", "GET", "inventory_options"),
        ("/part-categories", "GET", "list_part_categories"),
        ("/part-categories", "POST", "create_part_category"),
        ("/units-of-measure", "GET", "list_units_of_measure"),
        ("/units-of-measure", "POST", "create_unit_of_measure"),
        ("/parts", "GET", "list_spare_parts"),
        ("/parts", "POST", "create_spare_part"),
        ("/parts/{part_id}", "GET", "get_spare_part"),
        ("/parts/{part_id}", "PATCH", "update_spare_part"),
        ("/parts/{part_id}/activate", "POST", "activate_spare_part"),
        ("/parts/{part_id}/deactivate", "POST", "deactivate_spare_part"),
        ("/parts/{part_id}/archive", "POST", "archive_spare_part"),
        ("/parts/{part_id}/restore", "POST", "restore_spare_part"),
        ("/parts/{part_id}/reorder-configurations", "POST", "upsert_reorder_configuration"),
        ("/parts/{part_id}/history", "GET", "spare_part_history"),
        ("/stock-locations", "GET", "list_stock_locations"),
        ("/stock-locations", "POST", "create_stock_location"),
        ("/stock-locations/{location_id}", "PATCH", "update_stock_location"),
        ("/stock-locations/{location_id}/activate", "POST", "activate_stock_location"),
        ("/stock-locations/{location_id}/deactivate", "POST", "deactivate_stock_location"),
        ("/stock-locations/{location_id}/archive", "POST", "archive_stock_location"),
        ("/stock-locations/{location_id}/restore", "POST", "restore_stock_location"),
        ("/inventory/balances", "GET", "list_inventory_balances"),
        ("/inventory/low-stock", "GET", "list_low_stock"),
        ("/inventory/movements", "GET", "list_inventory_movements"),
        ("/inventory/metrics", "GET", "inventory_metrics"),
        ("/inventory/opening-balances", "POST", "create_opening_balance"),
        ("/inventory/receipts", "POST", "receive_inventory_stock"),
        ("/inventory/transfers", "POST", "transfer_inventory_stock"),
        ("/inventory/adjustments", "POST", "adjust_inventory_stock"),
        ("/inventory/reservations", "GET", "list_stock_reservations"),
        ("/work-orders/{work_order_id}/parts", "GET", "get_work_order_parts"),
        ("/work-orders/{work_order_id}/part-requirements", "GET", "list_work_order_part_requirements"),
        ("/work-orders/{work_order_id}/part-requirements", "POST", "create_work_order_part_requirement"),
        ("/work-order-part-requirements/{requirement_id}/reservations", "POST", "reserve_requirement_stock"),
        ("/stock-reservations/{reservation_id}/release", "POST", "release_stock_reservation"),
        ("/stock-reservations/{reservation_id}/expire", "POST", "expire_stock_reservation"),
        ("/stock-reservations/{reservation_id}/replace", "POST", "replace_stock_reservation"),
        ("/work-orders/{work_order_id}/part-issues", "POST", "issue_work_order_part"),
        ("/part-issues/{issue_id}/consumptions", "POST", "consume_work_order_part"),
        ("/part-issues/{issue_id}/returns", "POST", "return_work_order_part"),
        ("/inventory/movements/{movement_id}/attachments", "GET", "list_inventory_evidence"),
        ("/inventory/movements/{movement_id}/attachments", "POST", "upload_inventory_evidence"),
        ("/inventory/movements/{movement_id}/attachments/{attachment_id}", "GET", "download_inventory_evidence"),
        ("/inventory/movements/{movement_id}/attachments/{attachment_id}", "DELETE", "delete_inventory_evidence"),
    ]
    modules = (catalogue, stock, reservations, work_order_parts, attachments)
    actual = [
        (route.path, method, route.name)
        for module in modules
        for route in module.router.routes
        if isinstance(route, APIRoute)
        for method in sorted(route.methods or ())
    ]
    assert sorted(actual) == sorted(expected)
