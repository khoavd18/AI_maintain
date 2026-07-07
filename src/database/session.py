"""SQLAlchemy engine and session helpers."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config.settings import get_settings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


def build_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured database."""

    return create_engine(database_url or get_settings().database_url, pool_pre_ping=True)


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


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for FastAPI dependencies or scripts."""

    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
