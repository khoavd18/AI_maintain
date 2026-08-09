"""Upgrade or explicitly reset the canonical PostgreSQL schema with Alembic."""

import argparse

from src.database.migrations import downgrade_database, upgrade_database


def init_database(
    database_url: str | None = None,
    drop_existing: bool = False,
) -> None:
    """Apply migrations; `drop_existing` remains an explicit test-tool compatibility flag."""

    if drop_existing:
        downgrade_database(database_url=database_url, revision="base")
    upgrade_database(database_url=database_url, revision="head")


def main() -> None:
    """Run canonical migrations from the command line."""

    parser = argparse.ArgumentParser(
        description="Apply Alembic migrations for maintenance transactional storage."
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL from the environment.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Explicitly downgrade to base before upgrading; deletes transactional data.",
    )
    args = parser.parse_args()

    init_database(database_url=args.database_url, drop_existing=args.reset)
    print("Database migrations are at head.")


if __name__ == "__main__":
    main()
