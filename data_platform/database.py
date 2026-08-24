"""PostgreSQL connection helpers for the Data Platform runtime."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import Connection

from data_platform.config import DataPlatformSettings


@contextmanager
def connect(
    settings: DataPlatformSettings | None = None,
    *,
    read_only: bool = False,
) -> Iterator[Connection[Any]]:
    """Open a short-lived transaction with an explicit read/write contract."""

    resolved = (settings or DataPlatformSettings.from_env()).validated()
    connection = psycopg.connect(**resolved.psycopg_kwargs)
    try:
        if read_only:
            connection.execute("SET TRANSACTION READ ONLY")
        yield connection
        if read_only:
            connection.rollback()
        else:
            connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def check_database(settings: DataPlatformSettings | None = None) -> dict[str, object]:
    """Return non-secret connection evidence for preflight and health checks."""

    resolved = settings or DataPlatformSettings.from_env()
    with connect(resolved, read_only=True) as connection:
        row = connection.execute(
            """
            SELECT current_database(), current_setting('server_version'),
                   current_setting('TimeZone')
            """
        ).fetchone()
    if row is None:
        raise RuntimeError("Database preflight did not return server metadata.")
    if row[0] != resolved.database:
        raise RuntimeError("Connected database does not match fail-closed settings.")
    return {"database": row[0], "server_version": row[1], "timezone": row[2]}
