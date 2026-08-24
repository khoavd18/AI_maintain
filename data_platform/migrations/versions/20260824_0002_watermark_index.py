"""Add the measured tuple-watermark source index.

Revision ID: 20260824_dp0002
Revises: 20260824_dp0001
Create Date: 2026-08-24 12:05:00
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260824_dp0002"
down_revision: str | None = "20260824_dp0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Support ``(updated_at, id)`` extraction after benchmark evidence."""

    op.create_index(
        "ix_work_orders_updated_at_id",
        "work_orders",
        ["updated_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_work_orders_updated_at_id", table_name="work_orders")
