"""Alembic environment for the canonical PostgreSQL transactional schema."""

from logging.config import fileConfig

from alembic import context

from src.config.settings import get_settings
from src.database import models  # noqa: F401
from src.database.session import Base, build_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_DATA_PLATFORM_OWNED_INDEXES = frozenset(
    {
        "ix_work_orders_updated_at_id",
        "ix_s10_inventory_movements_created_id",
        "ix_s10_spare_parts_updated_id",
        "ix_s10_ticket_escalations_created_id",
        "ix_s10_ticket_sla_events_created_id",
        "ix_s10_tickets_updated_id",
    }
)


def _include_application_object(
    _object: object,
    name: str | None,
    type_: str,
    reflected: bool,
    _compare_to: object | None,
) -> bool:
    """Keep Data Platform-owned public objects out of application autogenerate."""

    if not reflected:
        return True
    if type_ == "table" and name == "data_platform_alembic_version":
        return False
    return not (type_ == "index" and name in _DATA_PLATFORM_OWNED_INDEXES)


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url").replace("%%", "%")
    value = configured or get_settings().database_url
    if not value.startswith("postgresql+psycopg://"):
        raise RuntimeError("Canonical migrations require postgresql+psycopg://.")
    return value


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""

    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_include_application_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in a database transaction."""

    connectable = build_engine(_database_url())
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            transaction_per_migration=True,
            include_object=_include_application_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
