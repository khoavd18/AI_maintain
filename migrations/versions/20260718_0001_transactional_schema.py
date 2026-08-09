"""Create canonical asset, ticket, and maintenance log tables.

Revision ID: 20260718_0001
Revises:
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260718_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the PostgreSQL-primary transactional schema."""

    op.execute("CREATE SEQUENCE maintenance_ticket_id_seq START WITH 1 INCREMENT BY 1")
    op.execute("CREATE SEQUENCE maintenance_log_id_seq START WITH 1 INCREMENT BY 1")

    op.create_table(
        "assets",
        sa.Column("asset_id", sa.String(length=50), nullable=False),
        sa.Column("asset_name", sa.String(length=200), nullable=False),
        sa.Column("asset_type", sa.String(length=40), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("criticality", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("installation_date", sa.Date(), nullable=False),
        sa.Column("last_maintenance_date", sa.Date(), nullable=False),
        sa.Column("maintenance_interval_days", sa.Integer(), nullable=False),
        sa.Column("next_maintenance_date", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "asset_type IN ('hvac', 'pump', 'generator')",
            name="ck_assets_asset_type",
        ),
        sa.CheckConstraint(
            "criticality IN ('low', 'medium', 'high', 'critical')",
            name="ck_assets_criticality",
        ),
        sa.CheckConstraint(
            "status IN ('normal', 'warning', 'fault')",
            name="ck_assets_status",
        ),
        sa.CheckConstraint(
            "maintenance_interval_days > 0",
            name="ck_assets_maintenance_interval_positive",
        ),
        sa.CheckConstraint(
            "next_maintenance_date >= last_maintenance_date",
            name="ck_assets_maintenance_chronology",
        ),
        sa.PrimaryKeyConstraint("asset_id", name="pk_assets"),
    )
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"])
    op.create_index("ix_assets_location", "assets", ["location"])
    op.create_index(
        "ix_assets_next_maintenance_date",
        "assets",
        ["next_maintenance_date"],
    )

    op.create_table(
        "maintenance_tickets",
        sa.Column("ticket_id", sa.String(length=50), nullable=False),
        sa.Column("asset_id", sa.String(length=50), nullable=False),
        sa.Column("issue_description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("failure_category", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("technician_id", sa.String(length=50), nullable=False),
        sa.Column("manager_note", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name="ck_tickets_priority",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved')",
            name="ck_tickets_status",
        ),
        sa.CheckConstraint(
            "failure_category IN ('cooling_issue', 'vibration_issue', "
            "'electrical_issue', 'pressure_issue', 'runtime_issue', "
            "'sensor_issue', 'false_alarm', 'no_failure')",
            name="ck_tickets_failure_category",
        ),
        sa.CheckConstraint(
            "((status = 'resolved' AND resolved_at IS NOT NULL) OR "
            "(status <> 'resolved' AND resolved_at IS NULL))",
            name="ck_tickets_resolution_state",
        ),
        sa.CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= created_at",
            name="ck_tickets_resolution_chronology",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.asset_id"],
            name="fk_tickets_asset_id_assets",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("ticket_id", name="pk_maintenance_tickets"),
        sa.UniqueConstraint(
            "ticket_id",
            "asset_id",
            name="uq_tickets_ticket_asset",
        ),
    )
    op.create_index("ix_tickets_asset_id", "maintenance_tickets", ["asset_id"])
    op.create_index("ix_tickets_status", "maintenance_tickets", ["status"])
    op.create_index("ix_tickets_created_at", "maintenance_tickets", ["created_at"])

    op.create_table(
        "maintenance_logs",
        sa.Column("log_id", sa.String(length=50), nullable=False),
        sa.Column("ticket_id", sa.String(length=50), nullable=True),
        sa.Column("asset_id", sa.String(length=50), nullable=False),
        sa.Column("maintenance_date", sa.Date(), nullable=False),
        sa.Column("maintenance_type", sa.String(length=30), nullable=False),
        sa.Column("technician_id", sa.String(length=50), nullable=False),
        sa.Column("inspection_result", sa.Text(), nullable=False),
        sa.Column("actions_taken", sa.Text(), nullable=False),
        sa.Column("parts_replaced", sa.Text(), nullable=True),
        sa.Column("technician_note", sa.Text(), nullable=False),
        sa.Column("maintenance_result", sa.String(length=30), nullable=False),
        sa.Column("follow_up_required", sa.Boolean(), nullable=False),
        sa.Column("next_maintenance_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "maintenance_type IN ('preventive', 'corrective', 'inspection', 'emergency')",
            name="ck_logs_maintenance_type",
        ),
        sa.CheckConstraint(
            "maintenance_result IN ('resolved', 'partially_resolved', "
            "'monitoring_required', 'vendor_required')",
            name="ck_logs_maintenance_result",
        ),
        sa.CheckConstraint(
            "((maintenance_result = 'resolved' AND follow_up_required = false) OR "
            "(maintenance_result <> 'resolved' AND follow_up_required = true))",
            name="ck_logs_follow_up_result",
        ),
        sa.CheckConstraint(
            "next_maintenance_date > maintenance_date",
            name="ck_logs_maintenance_chronology",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.asset_id"],
            name="fk_logs_asset_id_assets",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "asset_id"],
            ["maintenance_tickets.ticket_id", "maintenance_tickets.asset_id"],
            name="fk_logs_ticket_asset",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("log_id", name="pk_maintenance_logs"),
    )
    op.create_index("ix_logs_asset_id", "maintenance_logs", ["asset_id"])
    op.create_index("ix_logs_ticket_id", "maintenance_logs", ["ticket_id"])
    op.create_index(
        "ix_logs_maintenance_date",
        "maintenance_logs",
        ["maintenance_date"],
    )


def downgrade() -> None:
    """Remove the canonical transactional schema."""

    op.drop_table("maintenance_logs")
    op.drop_table("maintenance_tickets")
    op.drop_table("assets")
    op.execute("DROP SEQUENCE maintenance_log_id_seq")
    op.execute("DROP SEQUENCE maintenance_ticket_id_seq")
