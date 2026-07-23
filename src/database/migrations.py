"""Small programmatic boundary around the repository Alembic configuration."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from src.config.settings import get_settings

ALEMBIC_CONFIG_PATH = Path(__file__).resolve().parents[2] / "alembic.ini"


def alembic_config(database_url: str | None = None) -> Config:
    """Build an Alembic config without writing credentials to repository files."""

    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.set_main_option(
        "sqlalchemy.url",
        (database_url or get_settings().database_url).replace("%", "%%"),
    )
    return config


def upgrade_database(database_url: str | None = None, revision: str = "head") -> None:
    """Upgrade a database to the requested revision."""

    command.upgrade(alembic_config(database_url), revision)


def downgrade_database(database_url: str | None = None, revision: str = "-1") -> None:
    """Downgrade a database to the requested revision."""

    command.downgrade(alembic_config(database_url), revision)
