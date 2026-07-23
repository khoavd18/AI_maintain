"""Add canonical asset lifecycle, locations, attachments, and QR identity.

Revision ID: 20260718_0003
Revises: 20260718_0002
Create Date: 2026-07-18
"""

from collections.abc import Sequence
import hashlib
from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260718_0003"
down_revision: str | None = "20260718_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Extend the transactional schema without changing the analytics projection."""

    op.create_table(
        "locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("location_type", sa.String(length=30), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "location_type IN ('building', 'floor', 'room', 'area', 'plant')",
            name="ck_locations_type",
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id",
            name="ck_locations_not_self_parent",
        ),
        sa.CheckConstraint(
            "code = upper(btrim(code))",
            name="ck_locations_code_normalized",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["locations.id"],
            name="fk_locations_parent_id_locations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_locations_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_locations_updated_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_locations"),
        sa.UniqueConstraint("code", name="uq_locations_code"),
    )
    op.create_index("ix_locations_parent_id", "locations", ["parent_id"])
    op.create_index("ix_locations_is_active", "locations", ["is_active"])

    op.drop_constraint("ck_assets_status", "assets", type_="check")
    op.alter_column("assets", "status", new_column_name="operational_status")
    op.alter_column(
        "assets",
        "operational_status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
    op.execute(
        """
        UPDATE assets
        SET operational_status = CASE operational_status
            WHEN 'normal' THEN 'running'
            WHEN 'warning' THEN 'warning'
            ELSE 'fault'
        END
        """
    )
    op.create_check_constraint(
        "ck_assets_operational_status",
        "assets",
        "operational_status IN ('running', 'warning', 'fault', "
        "'under_maintenance', 'out_of_service')",
    )

    op.add_column(
        "assets",
        sa.Column(
            "asset_category",
            sa.String(length=40),
            server_default=sa.text("'other'"),
            nullable=False,
        ),
    )
    op.add_column("assets", sa.Column("manufacturer", sa.String(length=200), nullable=True))
    op.add_column("assets", sa.Column("model", sa.String(length=200), nullable=True))
    op.add_column("assets", sa.Column("serial_number", sa.String(length=150), nullable=True))
    op.add_column("assets", sa.Column("production_year", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "assets",
        sa.Column(
            "lifecycle_status",
            sa.String(length=20),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
    )
    op.add_column(
        "assets",
        sa.Column("lifecycle_status_before_archive", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("operational_status_before_archive", sa.String(length=30), nullable=True),
    )
    op.add_column("assets", sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "assets", sa.Column("commissioned_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("assets", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assets", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assets", sa.Column("archive_reason", sa.Text(), nullable=True))
    op.add_column(
        "assets",
        sa.Column(
            "ownership_type",
            sa.String(length=20),
            server_default=sa.text("'owned'"),
            nullable=False,
        ),
    )
    op.add_column("assets", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("warranty_start_date", sa.Date(), nullable=True))
    op.add_column("assets", sa.Column("warranty_end_date", sa.Date(), nullable=True))
    op.add_column(
        "assets", sa.Column("warranty_provider", sa.String(length=200), nullable=True)
    )
    op.add_column(
        "assets", sa.Column("warranty_reference", sa.String(length=200), nullable=True)
    )
    op.add_column(
        "assets",
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("assets", sa.Column("qr_token", postgresql.UUID(as_uuid=True), nullable=True))

    op.execute(
        """
        UPDATE assets
        SET asset_category = CASE asset_type
            WHEN 'hvac' THEN 'climate_control'
            WHEN 'pump' THEN 'water_system'
            WHEN 'generator' THEN 'power_system'
            ELSE 'other'
        END,
        installed_at = installation_date::timestamp AT TIME ZONE 'UTC'
        """
    )
    _backfill_qr_tokens()
    _seed_legacy_locations()
    op.alter_column("assets", "installed_at", nullable=False)
    op.alter_column("assets", "qr_token", nullable=False)

    op.create_foreign_key(
        "fk_assets_location_id_locations",
        "assets",
        "locations",
        ["location_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_assets_created_by_users",
        "assets",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_assets_updated_by_users",
        "assets",
        "users",
        ["updated_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint("uq_assets_qr_token", "assets", ["qr_token"])
    op.create_index("ix_assets_location_id", "assets", ["location_id"])
    op.create_index("ix_assets_lifecycle_status", "assets", ["lifecycle_status"])
    op.create_index("ix_assets_operational_status", "assets", ["operational_status"])
    op.create_index("ix_assets_manufacturer_model", "assets", ["manufacturer", "model"])
    op.create_index(
        "uq_assets_serial_number",
        "assets",
        ["serial_number"],
        unique=True,
        postgresql_where=sa.text("serial_number IS NOT NULL"),
    )
    _create_asset_checks()

    op.create_table(
        "asset_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "category IN ('asset_photo', 'technical_manual', 'warranty_document', "
            "'commissioning_record', 'inspection_document', 'other')",
            name="ck_asset_attachments_category",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_asset_attachments_size_positive"),
        sa.CheckConstraint(
            "length(checksum) = 64", name="ck_asset_attachments_checksum_length"
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.asset_id"],
            name="fk_asset_attachments_asset_id_assets",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name="fk_asset_attachments_uploaded_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by_user_id"],
            ["users.id"],
            name="fk_asset_attachments_deleted_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_asset_attachments"),
        sa.UniqueConstraint("storage_key", name="uq_asset_attachments_storage_key"),
    )
    op.create_index("ix_asset_attachments_asset_id", "asset_attachments", ["asset_id"])
    op.create_index(
        "ix_asset_attachments_active",
        "asset_attachments",
        ["asset_id", "deleted_at"],
    )
    op.create_index("ix_asset_attachments_checksum", "asset_attachments", ["checksum"])


def downgrade() -> None:
    """Remove lifecycle extensions while retaining a valid legacy status projection."""

    op.drop_table("asset_attachments")

    for constraint in (
        "ck_assets_archive_state",
        "ck_assets_warranty_chronology",
        "ck_assets_retirement_chronology",
        "ck_assets_commissioning_chronology",
        "ck_assets_production_year",
        "ck_assets_serial_number_normalized",
        "ck_assets_ownership_type",
        "ck_assets_category",
        "ck_assets_pre_archive_lifecycle_status",
        "ck_assets_pre_archive_operational_status",
        "ck_assets_lifecycle_status",
    ):
        op.drop_constraint(constraint, "assets", type_="check")
    op.drop_index("uq_assets_serial_number", table_name="assets")
    op.drop_index("ix_assets_manufacturer_model", table_name="assets")
    op.drop_index("ix_assets_operational_status", table_name="assets")
    op.drop_index("ix_assets_lifecycle_status", table_name="assets")
    op.drop_index("ix_assets_location_id", table_name="assets")
    op.drop_constraint("uq_assets_qr_token", "assets", type_="unique")
    op.drop_constraint("fk_assets_updated_by_users", "assets", type_="foreignkey")
    op.drop_constraint("fk_assets_created_by_users", "assets", type_="foreignkey")
    op.drop_constraint("fk_assets_location_id_locations", "assets", type_="foreignkey")

    for column in (
        "qr_token",
        "updated_by_user_id",
        "created_by_user_id",
        "warranty_reference",
        "warranty_provider",
        "warranty_end_date",
        "warranty_start_date",
        "description",
        "ownership_type",
        "archive_reason",
        "archived_at",
        "retired_at",
        "commissioned_at",
        "installed_at",
        "lifecycle_status_before_archive",
        "operational_status_before_archive",
        "lifecycle_status",
        "location_id",
        "production_year",
        "serial_number",
        "model",
        "manufacturer",
        "asset_category",
    ):
        op.drop_column("assets", column)

    op.drop_constraint("ck_assets_operational_status", "assets", type_="check")
    op.execute(
        """
        UPDATE assets
        SET operational_status = CASE operational_status
            WHEN 'running' THEN 'normal'
            WHEN 'fault' THEN 'fault'
            ELSE 'warning'
        END
        """
    )
    op.alter_column(
        "assets",
        "operational_status",
        existing_type=sa.String(length=30),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column("assets", "operational_status", new_column_name="status")
    op.create_check_constraint(
        "ck_assets_status",
        "assets",
        "status IN ('normal', 'warning', 'fault')",
    )
    op.drop_table("locations")


def _create_asset_checks() -> None:
    checks = {
        "ck_assets_lifecycle_status": (
            "lifecycle_status IN ('planned', 'active', 'inactive', 'retired', 'archived')"
        ),
        "ck_assets_pre_archive_lifecycle_status": (
            "lifecycle_status_before_archive IS NULL OR "
            "lifecycle_status_before_archive IN ('planned', 'active', 'inactive', 'retired')"
        ),
        "ck_assets_pre_archive_operational_status": (
            "operational_status_before_archive IS NULL OR "
            "operational_status_before_archive IN ('running', 'warning', 'fault', "
            "'under_maintenance', 'out_of_service')"
        ),
        "ck_assets_category": (
            "asset_category IN ('climate_control', 'water_system', 'power_system', 'other')"
        ),
        "ck_assets_ownership_type": "ownership_type IN ('owned', 'leased', 'managed')",
        "ck_assets_serial_number_normalized": (
            "serial_number IS NULL OR serial_number = upper(btrim(serial_number))"
        ),
        "ck_assets_production_year": (
            "production_year IS NULL OR production_year BETWEEN 1900 AND 2200"
        ),
        "ck_assets_commissioning_chronology": (
            "commissioned_at IS NULL OR commissioned_at >= installed_at"
        ),
        "ck_assets_retirement_chronology": (
            "retired_at IS NULL OR retired_at >= installed_at"
        ),
        "ck_assets_warranty_chronology": (
            "warranty_end_date IS NULL OR warranty_start_date IS NULL OR "
            "warranty_end_date >= warranty_start_date"
        ),
        "ck_assets_archive_state": (
            "((lifecycle_status = 'archived' AND archived_at IS NOT NULL "
            "AND archive_reason IS NOT NULL) OR "
            "(lifecycle_status <> 'archived' AND archived_at IS NULL "
            "AND archive_reason IS NULL))"
        ),
    }
    for name, condition in checks.items():
        op.create_check_constraint(name, "assets", condition)


def _backfill_qr_tokens() -> None:
    connection = op.get_bind()
    asset_ids = connection.execute(sa.text("SELECT asset_id FROM assets")).scalars()
    for asset_id in asset_ids:
        token = uuid5(NAMESPACE_URL, f"ai-maintenance-copilot:asset:{asset_id}")
        connection.execute(
            sa.text("UPDATE assets SET qr_token = :token WHERE asset_id = :asset_id"),
            {"token": token, "asset_id": asset_id},
        )


def _seed_legacy_locations() -> None:
    connection = op.get_bind()
    root_id = uuid5(NAMESPACE_URL, "ai-maintenance-copilot:location:facility-root")
    connection.execute(
        sa.text(
            """
            INSERT INTO locations (id, code, name, location_type, parent_id)
            VALUES (:id, 'FACILITY-ROOT', 'Cơ sở chính', 'building', NULL)
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {"id": root_id},
    )
    names = connection.execute(
        sa.text("SELECT DISTINCT location FROM assets ORDER BY location")
    ).scalars()
    for name in names:
        location_id, code = _location_identity(str(name))
        connection.execute(
            sa.text(
                """
                INSERT INTO locations (id, code, name, location_type, parent_id)
                VALUES (:id, :code, :name, 'area', :parent_id)
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {
                "id": location_id,
                "code": code,
                "name": name,
                "parent_id": root_id,
            },
        )
        connection.execute(
            sa.text(
                """
                UPDATE assets
                SET location_id = (SELECT id FROM locations WHERE code = :code)
                WHERE location = :name
                """
            ),
            {"code": code, "name": name},
        )


def _location_identity(name: str) -> tuple[UUID, str]:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:10].upper()
    location_id = uuid5(NAMESPACE_URL, f"ai-maintenance-copilot:location:{name}")
    return location_id, f"LOC-{digest}"
