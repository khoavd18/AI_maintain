"""Create the structured database schema for the AI Maintenance Copilot."""

import argparse

from sqlalchemy import Engine

from src.database import models  # noqa: F401
from src.database.session import Base, build_engine


def init_database(database_url: str | None = None, drop_existing: bool = False) -> None:
    """Create database tables, optionally dropping existing tables first."""

    engine: Engine = build_engine(database_url)
    if drop_existing:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def main() -> None:
    """Run schema creation from the command line."""

    parser = argparse.ArgumentParser(description="Initialize maintenance copilot database schema.")
    parser.add_argument("--database-url", default=None, help="Override DATABASE_URL from the environment.")
    parser.add_argument("--drop-existing", action="store_true", help="Drop existing tables before creation.")
    args = parser.parse_args()

    init_database(database_url=args.database_url, drop_existing=args.drop_existing)
    print("Database schema is ready.")


if __name__ == "__main__":
    main()
