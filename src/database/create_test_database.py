"""Create the dedicated local PostgreSQL integration-test database if missing."""

from __future__ import annotations

import argparse
import os

import psycopg
from psycopg import sql
from sqlalchemy.engine.url import make_url

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://maintenance:maintenance@localhost:5432/"
    "maintenance_copilot_test"
)


def create_test_database(database_url: str) -> bool:
    """Create an `_test` database without modifying an existing database."""

    parsed = make_url(database_url)
    database_name = parsed.database or ""
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("TEST_DATABASE_URL must use postgresql+psycopg://")
    if not database_name.endswith("_test"):
        raise ValueError("Test database name must end with _test")

    admin_url = parsed.set(drivername="postgresql", database="postgres")
    connection_url = admin_url.render_as_string(hide_password=False)
    with psycopg.connect(connection_url, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (database_name,),
        ).fetchone()
        if exists:
            return False
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a dedicated PostgreSQL database for integration tests."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL),
    )
    args = parser.parse_args()

    created = create_test_database(args.database_url)
    print("Created test database." if created else "Test database already exists.")


if __name__ == "__main__":
    main()
