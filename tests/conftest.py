"""Shared safeguards for PostgreSQL integration tests."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine.url import make_url

from src.database.migrations import upgrade_database
from src.database.session import build_engine


@pytest.fixture
def postgres_database_url() -> str:
    """Return only an explicitly isolated test database URL."""

    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is not configured")
    parsed = make_url(value)
    if parsed.drivername != "postgresql+psycopg":
        pytest.fail("TEST_DATABASE_URL must use postgresql+psycopg://")
    if not (parsed.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL database name must end with _test")
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
    }
    if not required.issubset(tables):
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE audit_logs, refresh_sessions, work_order_attachments, "
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
