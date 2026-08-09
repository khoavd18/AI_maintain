"""Shared safeguards for PostgreSQL integration tests."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from sqlalchemy import inspect, text

from src.database.migrations import upgrade_database
from src.database.session import build_engine
from src.database.test_database import validate_test_database_environment


@pytest.fixture
def postgres_database_url() -> str:
    """Return only an explicitly isolated test database URL."""

    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is not configured")
    try:
        validate_test_database_environment()
    except ValueError as exc:
        pytest.fail(str(exc))
    return value


@pytest.fixture
def clean_postgres_database(postgres_database_url: str) -> Generator[str, None, None]:
    """Migrate and truncate only the dedicated integration-test database."""

    upgrade_database(postgres_database_url)
    engine = build_engine(postgres_database_url)
    _truncate_transactional_tables(engine)
    try:
        yield postgres_database_url
    finally:
        _truncate_transactional_tables(engine)
        engine.dispose()


def _truncate_transactional_tables(engine) -> None:
    tables = set(inspect(engine).get_table_names())
    required = {
        "assets",
        "maintenance_tickets",
        "maintenance_logs",
        "users",
        "refresh_sessions",
        "audit_logs",
        "locations",
        "asset_attachments",
        "preventive_maintenance_plans",
        "checklist_templates",
        "checklist_template_items",
        "work_orders",
        "work_order_checklist_items",
        "work_order_attachments",
        "ticket_categories",
        "ticket_subcategories",
        "ticket_intake_sources",
        "support_groups",
        "business_calendars",
        "business_working_periods",
        "business_calendar_holidays",
        "sla_policies",
        "sla_policy_targets",
        "ticket_sla_states",
        "ticket_sla_events",
        "ticket_comments",
        "ticket_comment_attachments",
        "ticket_escalation_events",
        "part_categories",
        "units_of_measure",
        "spare_parts",
        "stock_locations",
        "inventory_positions",
        "part_reorder_configurations",
        "inventory_operations",
        "inventory_movements",
        "work_order_part_requirements",
        "stock_reservations",
        "stock_reservation_events",
        "work_order_part_issues",
        "work_order_part_consumptions",
        "work_order_part_returns",
        "inventory_attachments",
        "scheduled_jobs",
        "job_executions",
        "outbox_events",
        "outbox_delivery_attempts",
        "outbox_redrive_requests",
        "notifications",
        "notification_alert_states",
        "worker_heartbeats",
        "reliability_validation_records",
    }
    if not required.issubset(tables):
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE reliability_validation_records, worker_heartbeats, "
                "notifications, notification_alert_states, "
                "outbox_redrive_requests, "
                "outbox_delivery_attempts, outbox_events, job_executions, "
                "audit_logs, refresh_sessions, ticket_comment_attachments, "
                "inventory_attachments, work_order_part_returns, "
                "work_order_part_consumptions, work_order_part_issues, "
                "stock_reservation_events, stock_reservations, "
                "work_order_part_requirements, inventory_movements, "
                "part_reorder_configurations, inventory_positions, "
                "inventory_operations, spare_parts, stock_locations, "
                "part_categories, units_of_measure, "
                "ticket_sla_events, ticket_escalation_events, ticket_comments, "
                "ticket_sla_states, sla_policy_targets, sla_policies, "
                "business_calendar_holidays, business_working_periods, "
                "business_calendars, ticket_subcategories, ticket_categories, "
                "ticket_intake_sources, support_groups, work_order_attachments, "
                "work_order_checklist_items, maintenance_logs, work_orders, "
                "preventive_maintenance_plans, checklist_template_items, "
                "checklist_templates, asset_attachments, maintenance_tickets, "
                "assets, locations, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        connection.execute(text("ALTER SEQUENCE maintenance_ticket_id_seq RESTART WITH 1"))
        connection.execute(text("ALTER SEQUENCE maintenance_log_id_seq RESTART WITH 1"))
        connection.execute(text("ALTER SEQUENCE work_order_number_seq RESTART WITH 1"))
        connection.execute(text("ALTER SEQUENCE inventory_movement_number_seq RESTART WITH 1"))
        connection.execute(text("ALTER SEQUENCE stock_reservation_number_seq RESTART WITH 1"))
        connection.execute(text("ALTER SEQUENCE part_issue_number_seq RESTART WITH 1"))
        connection.execute(text("ALTER SEQUENCE part_return_number_seq RESTART WITH 1"))
        connection.execute(
            text(
                "INSERT INTO scheduled_jobs ("
                "job_key, job_type, enabled, interval_seconds, timezone, "
                "configuration_payload, next_run_at, concurrency_policy, "
                "max_attempts, retry_backoff_seconds, lease_seconds"
                ") VALUES "
                "('preventive_generation', 'preventive_generation', false, 3600, "
                "'Asia/Ho_Chi_Minh', '{}'::jsonb, now(), 'forbid_overlap', 3, 30, 300), "
                "('sla_escalation', 'sla_escalation', false, 300, "
                "'Asia/Ho_Chi_Minh', '{}'::jsonb, now(), 'forbid_overlap', 3, 30, 180), "
                "('analytics_refresh', 'analytics_refresh', false, 86400, "
                "'Asia/Ho_Chi_Minh', '{}'::jsonb, now(), 'forbid_overlap', 2, 120, 3600), "
                "('inventory_reorder_detection', 'inventory_reorder_detection', false, "
                "900, 'Asia/Ho_Chi_Minh', '{}'::jsonb, now(), 'forbid_overlap', 3, 30, 180) "
                "ON CONFLICT (job_key) DO UPDATE SET enabled = false, "
                "run_as_user_id = NULL, last_successful_run_at = NULL, "
                "next_run_at = now(), configuration_payload = '{}'::jsonb, "
                "updated_at = now(), version = 1"
            )
        )
