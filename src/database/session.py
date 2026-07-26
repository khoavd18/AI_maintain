"""SQLAlchemy engine and session helpers."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config.settings import get_settings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


class DatabaseConnectionError(RuntimeError):
    """Raised when the configured PostgreSQL primary store is unavailable."""


def build_engine(
    database_url: str | None = None,
    *,
    connect_timeout_seconds: int | None = None,
) -> Engine:
    """Create a SQLAlchemy engine for the configured database."""

    settings = get_settings()
    resolved_url = database_url or settings.database_url
    parsed_url = make_url(resolved_url)
    if parsed_url.drivername == "postgresql":
        raise ValueError("DATABASE_URL must select the psycopg driver explicitly.")
    connect_args: dict[str, object] = {}
    if parsed_url.drivername == "postgresql+psycopg":
        connect_args["connect_timeout"] = (
            connect_timeout_seconds or settings.database_connect_timeout_seconds
        )
        connect_args["options"] = " ".join(
            (
                f"-c statement_timeout={settings.database_statement_timeout_seconds * 1000}",
                f"-c lock_timeout={settings.database_lock_timeout_seconds * 1000}",
                "-c idle_in_transaction_session_timeout="
                f"{settings.database_idle_transaction_timeout_seconds * 1000}",
            )
        )
    return create_engine(
        resolved_url,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        connect_args=connect_args,
    )


@lru_cache
def get_engine(database_url: str | None = None) -> Engine:
    """Return a cached SQLAlchemy engine."""

    return build_engine(database_url)


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """Create a session factory for the requested database URL."""

    return sessionmaker(
        bind=get_engine(database_url),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


def verify_database_connection(engine: Engine | None = None) -> None:
    """Fail clearly when PostgreSQL cannot serve the configured runtime."""

    selected_engine = engine or get_engine()
    try:
        with selected_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except (OperationalError, SQLAlchemyError) as exc:
        raise DatabaseConnectionError(
            "PostgreSQL primary storage is unavailable. Check DATABASE_URL and "
            "start PostgreSQL before running the API."
        ) from exc


def clear_database_caches() -> None:
    """Clear cached engines after configuration changes in tests or tooling."""

    get_engine.cache_clear()


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for FastAPI dependencies or scripts."""

    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
