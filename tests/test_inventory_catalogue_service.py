"""Characterization tests for the extracted inventory catalogue use cases."""

from src.inventory_management.application.catalogue_service import (
    InventoryCatalogueService,
)
from src.repositories.contracts import StoredRecord
from src.security.permissions import Permission, Role
from tests.auth_helpers import build_test_user


class _CatalogueRepository:
    def list_categories(self, *, include_inactive: bool) -> list[StoredRecord]:
        return [StoredRecord({"code": "GENERATOR", "include_inactive": include_inactive})]

    def list_units(self, *, include_inactive: bool) -> list[StoredRecord]:
        return [StoredRecord({"code": "EA", "include_inactive": include_inactive})]


def test_catalogue_queries_preserve_options_and_read_projections() -> None:
    actor = build_test_user(Role.STOREKEEPER)
    repository = _CatalogueRepository()
    service = InventoryCatalogueService(
        lambda: repository,
        _require_permission,
        _require_any_read,
    )

    options = service.options(actor=actor)
    categories = service.list_categories(actor=actor, include_inactive=True)
    units = service.list_units(actor=actor, include_inactive=False)

    assert options["stock_states"]
    assert options["compatible_asset_types"]
    assert categories == [{"code": "GENERATOR", "include_inactive": True}]
    assert units == [{"code": "EA", "include_inactive": False}]


def _require_permission(actor, permission: Permission) -> None:
    if not actor.has(permission):
        raise AssertionError(permission)


def _require_any_read(actor) -> None:
    if not (actor.has(Permission.INVENTORY_READ) or actor.has(Permission.WORK_ORDER_PARTS_READ)):
        raise AssertionError("read permission required")
