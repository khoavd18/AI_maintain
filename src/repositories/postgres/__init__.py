"""Composed PostgreSQL repository capabilities.

The package keeps the historical ``src.repositories.postgres`` maintenance
repository import stable while providing domain-specific PostgreSQL
capabilities below this namespace.
"""

from src.repositories.postgres.legacy import PostgresMaintenanceRepository

__all__ = ["PostgresMaintenanceRepository"]
