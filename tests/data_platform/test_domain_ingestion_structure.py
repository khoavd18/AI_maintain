from __future__ import annotations

import ast
from pathlib import Path

import pytest

import data_platform.domain_loader as historical_loader
import data_platform.domain_pipeline as historical_facade
import data_platform.ingestion.domains as domain_ingestion
from data_platform.ingestion.domains import catalog
from data_platform.ingestion.domains import cli
from data_platform.ingestion.domains import extraction
from data_platform.ingestion.domains import raw_loading
from data_platform.ingestion.domains import reconciliation
from data_platform.ingestion.domains import run_tracking
from data_platform.ingestion.domains import safety
from data_platform.ingestion.domains import source_validation
from data_platform.ingestion.domains.catalog import DomainSpec


REPOSITORY_ROOT = Path(__file__).parents[2]
IMPLEMENTATION_ROOT = REPOSITORY_ROOT / "data_platform" / "ingestion" / "domains"

EXPECTED_DOMAINS = (
    "work_order_status_history",
    "tickets",
    "ticket_events",
    "spare_parts",
    "inventory_movements",
    "work_order_costs",
)

EXPECTED_DOMAIN_SPECS = {
    "work_order_status_history": DomainSpec(
        source_view="analytics_source.work_order_status_history",
        raw_table="raw.work_order_status_history",
        columns=(
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
        identity_column="event_id",
        warehouse_relation="analytics_warehouse.fact_work_order_status_duration",
    ),
    "tickets": DomainSpec(
        source_view="analytics_source.tickets",
        raw_table="raw.tickets",
        columns=(
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
        identity_column="ticket_id",
        warehouse_relation="analytics_warehouse.fact_ticket_sla",
    ),
    "ticket_events": DomainSpec(
        source_view="analytics_source.ticket_events",
        raw_table="raw.ticket_events",
        columns=(
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
        identity_column="event_id",
        warehouse_relation="analytics_warehouse.fact_ticket_sla",
    ),
    "spare_parts": DomainSpec(
        source_view="analytics_source.spare_parts",
        raw_table="raw.spare_parts",
        columns=(
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
        identity_column="part_id",
        warehouse_relation="analytics_warehouse.dim_spare_part",
    ),
    "inventory_movements": DomainSpec(
        source_view="analytics_source.inventory_movements",
        raw_table="raw.inventory_movements",
        columns=(
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
        identity_column="movement_id",
        warehouse_relation="analytics_warehouse.fact_inventory_movement",
    ),
    "work_order_costs": DomainSpec(
        source_view="analytics_source.work_order_costs",
        raw_table="raw.work_order_costs",
        columns=(
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
        identity_column="work_order_id",
        warehouse_relation="analytics_warehouse.fact_work_order_cost",
    ),
}


def test_domain_catalog_is_closed_ordered_and_exact() -> None:
    assert catalog.DOMAINS == EXPECTED_DOMAINS
    assert tuple(catalog.DOMAIN_SPECS) == EXPECTED_DOMAINS
    assert catalog.DOMAIN_SPECS == EXPECTED_DOMAIN_SPECS

    for domain in EXPECTED_DOMAINS:
        assert catalog.domain_spec(domain) is catalog.DOMAIN_SPECS[domain]

    with pytest.raises(ValueError, match="Unsupported Stage 10 domain"):
        catalog.domain_spec("tickets ")


def test_capability_package_exports_are_exact_identity_re_exports() -> None:
    expected_exports = {
        "DOMAINS": catalog.DOMAINS,
        "DomainSpec": catalog.DomainSpec,
        "domain_spec": catalog.domain_spec,
    }

    assert domain_ingestion.__all__ == list(expected_exports)
    for name, implementation in expected_exports.items():
        assert getattr(domain_ingestion, name) is implementation


def test_historical_facade_preserves_import_identities_and_cli_delegation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_exports = {
        "DOMAINS": catalog.DOMAINS,
        "DomainSpec": catalog.DomainSpec,
        "EPOCH": extraction.EPOCH,
        "InjectedDomainFailure": raw_loading.InjectedDomainFailure,
        "LOGGER": extraction.LOGGER,
        "UTC": extraction.UTC,
        "ZERO_ID": extraction.ZERO_ID,
        "_SPECS": catalog.DOMAIN_SPECS,
        "_copy_raw_object": raw_loading.copy_raw_object,
        "_domain": catalog.domain_spec,
        "_existing_batch": extraction.existing_batch,
        "_relation_count": reconciliation.relation_count,
        "_sanitize": safety.sanitize_audit_message,
        "_validated_run_id": safety.validate_run_id,
        "_watermark": extraction.watermark,
        "complete_run": run_tracking.complete_run,
        "domain_source_counts": source_validation.domain_source_counts,
        "extract_domain": extraction.extract_domain,
        "fail_run": run_tracking.fail_run,
        "finalize_watermarks": reconciliation.finalize_watermarks,
        "load_raw_domain": raw_loading.load_raw_domain,
        "pipeline_state": run_tracking.pipeline_state,
        "reconcile_run": reconciliation.reconcile_run,
        "retry_run": run_tracking.retry_run,
        "start_run": run_tracking.start_run,
        "validate_domain_integrity": source_validation.validate_domain_integrity,
    }
    expected_all = [
        "DOMAINS",
        "DomainSpec",
        "EPOCH",
        "InjectedDomainFailure",
        "LOGGER",
        "UTC",
        "ZERO_ID",
        "complete_run",
        "domain_source_counts",
        "extract_domain",
        "fail_run",
        "finalize_watermarks",
        "load_raw_domain",
        "main",
        "pipeline_state",
        "reconcile_run",
        "retry_run",
        "start_run",
        "validate_domain_integrity",
    ]

    assert historical_facade.__all__ == expected_all
    for name, implementation in expected_exports.items():
        assert getattr(historical_facade, name) is implementation
    assert historical_facade._main is cli.main

    calls: list[str] = []
    monkeypatch.setattr(historical_facade, "_main", lambda: calls.append("main"))
    historical_facade.main()
    assert calls == ["main"]


def test_domain_loader_preserves_source_validation_imports() -> None:
    assert historical_loader.domain_source_counts is source_validation.domain_source_counts
    assert (
        historical_loader.validate_domain_integrity
        is source_validation.validate_domain_integrity
    )


@pytest.mark.parametrize(
    "run_id",
    [
        "manual__2026-08-27T10:20:30Z",
        "scheduled.run_2026-08-27",
        "x" * 200,
    ],
)
def test_run_id_validation_accepts_only_the_stable_safe_shape(run_id: str) -> None:
    assert safety.validate_run_id(run_id) == run_id


@pytest.mark.parametrize(
    "run_id",
    ["", "contains whitespace", "../escape", "path/segment", "line\nbreak", "x" * 201],
)
def test_run_id_validation_rejects_unsafe_values(run_id: str) -> None:
    with pytest.raises(ValueError, match="unsupported characters"):
        safety.validate_run_id(run_id)


def test_audit_sanitization_redacts_credentials_and_bounds_one_line() -> None:
    message = (
        " failed\npassword=hunter2; token:abc123 "
        "postgresql://scale_user:uri-secret@localhost:5432/analytics "
    )

    sanitized = safety.sanitize_audit_message(message)

    assert sanitized == (
        "failed password=<redacted>; token=<redacted> "
        "postgresql://scale_user:<redacted>@localhost:5432/analytics"
    )
    assert "hunter2" not in sanitized
    assert "abc123" not in sanitized
    assert "uri-secret" not in sanitized
    assert safety.sanitize_audit_message("x" * 1_100) == "x" * 1_000
    assert safety.sanitize_audit_message("bounded", limit=4) == "boun"


def test_cli_parser_preserves_the_closed_command_and_option_catalog() -> None:
    parser = cli.build_parser()
    command_action = next(action for action in parser._actions if action.dest == "command")
    subparsers = command_action.choices
    assert subparsers is not None

    expected_options = {
        "start": ("--run-id", "--phase", "--fault-domain"),
        "extract": ("--run-id", "--phase", "--domain"),
        "load-raw": ("--run-id", "--domain", "--fault-domain"),
        "reconcile": ("--run-id",),
        "finalize": ("--run-id",),
        "complete": ("--run-id",),
        "audit-fail": ("--run-id", "--step", "--error"),
        "audit-retry": ("--run-id", "--step", "--error"),
        "state": ("--run-id",),
        "validate": (),
    }

    assert tuple(subparsers) == tuple(expected_options)
    assert {
        command: tuple(
            option
            for action in subparser._actions
            for option in action.option_strings
            if option not in {"-h", "--help"}
        )
        for command, subparser in subparsers.items()
    } == expected_options


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (
            ["start", "--run-id", "run-1", "--phase", "incremental"],
            {
                "command": "start",
                "run_id": "run-1",
                "phase": "incremental",
                "fault_domain": "",
            },
        ),
        (
            [
                "extract",
                "--run-id",
                "run-1",
                "--phase",
                "baseline",
                "--domain",
                "tickets",
            ],
            {
                "command": "extract",
                "run_id": "run-1",
                "phase": "baseline",
                "domain": "tickets",
            },
        ),
        (
            [
                "load-raw",
                "--run-id",
                "run-1",
                "--domain",
                "spare_parts",
                "--fault-domain",
                "spare_parts",
            ],
            {
                "command": "load-raw",
                "run_id": "run-1",
                "domain": "spare_parts",
                "fault_domain": "spare_parts",
            },
        ),
        (["reconcile", "--run-id", "run-1"], {"command": "reconcile", "run_id": "run-1"}),
        (["finalize", "--run-id", "run-1"], {"command": "finalize", "run_id": "run-1"}),
        (["complete", "--run-id", "run-1"], {"command": "complete", "run_id": "run-1"}),
        (
            ["audit-fail", "--run-id", "run-1", "--step", "extract", "--error", "failed"],
            {
                "command": "audit-fail",
                "run_id": "run-1",
                "step": "extract",
                "error": "failed",
            },
        ),
        (
            ["audit-retry", "--run-id", "run-1", "--step", "load-raw"],
            {
                "command": "audit-retry",
                "run_id": "run-1",
                "step": "load-raw",
                "error": "",
            },
        ),
        (["state", "--run-id", "run-1"], {"command": "state", "run_id": "run-1"}),
        (["validate"], {"command": "validate"}),
    ],
)
def test_cli_parser_preserves_command_arguments(
    arguments: list[str],
    expected: dict[str, object],
) -> None:
    assert vars(cli.build_parser().parse_args(arguments)) == expected


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_domain_implementation_never_imports_the_historical_facade() -> None:
    violations = {
        str(path.relative_to(REPOSITORY_ROOT)): sorted(imported)
        for path in IMPLEMENTATION_ROOT.rglob("*.py")
        if (
            imported := {
                module
                for module in _imported_modules(path)
                if module == "data_platform.domain_pipeline"
                or module.startswith("data_platform.domain_pipeline.")
            }
        )
    }

    assert violations == {}
