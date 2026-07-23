"""Add spare-parts inventory and work-order stock control.

Revision ID: 20260723_0006
Revises: 20260723_0005
Create Date: 2026-07-23 13:22:37.311241
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260723_0006"
down_revision: str | None = "20260723_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the Product Milestone 6 inventory schema."""

    op.execute("CREATE SEQUENCE inventory_movement_number_seq START WITH 1 INCREMENT BY 1")
    op.execute("CREATE SEQUENCE stock_reservation_number_seq START WITH 1 INCREMENT BY 1")
    op.execute("CREATE SEQUENCE part_issue_number_seq START WITH 1 INCREMENT BY 1")
    op.execute("CREATE SEQUENCE part_return_number_seq START WITH 1 INCREMENT BY 1")
    op.create_table('inventory_operations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=100), nullable=False),
    sa.Column('operation_type', sa.String(length=40), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('result_type', sa.String(length=50), nullable=True),
    sa.Column('result_id', sa.String(length=100), nullable=True),
    sa.Column('actor_user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("operation_type IN ('opening_balance', 'receipt', 'reserve', 'release_reservation', 'expire_reservation', 'replace_reservation', 'issue', 'consume', 'return', 'transfer', 'adjustment_increase', 'adjustment_decrease', 'damaged_scrapped')", name='ck_inventory_operations_type'),
    sa.CheckConstraint('length(request_hash) = 64', name='ck_inventory_operations_request_hash'),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key', name='uq_inventory_operations_key')
    )
    op.create_index('ix_inventory_operations_actor', 'inventory_operations', ['actor_user_id'], unique=False)
    op.create_index('ix_inventory_operations_created_at', 'inventory_operations', ['created_at'], unique=False)
    op.create_table('part_categories',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name_vi', sa.String(length=200), nullable=False),
    sa.Column('name_en', sa.String(length=200), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('updated_by_user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint('code = upper(btrim(code))', name='ck_part_categories_code'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_part_categories_code')
    )
    op.create_index('ix_part_categories_active', 'part_categories', ['is_active'], unique=False)
    op.create_table('stock_locations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('location_type', sa.String(length=30), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('lifecycle_status', sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
    sa.Column('lifecycle_status_before_archive', sa.String(length=20), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('archive_reason', sa.Text(), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('updated_by_user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint("((lifecycle_status = 'archived' AND archived_at IS NOT NULL AND archive_reason IS NOT NULL) OR (lifecycle_status <> 'archived' AND archived_at IS NULL AND archive_reason IS NULL))", name='ck_stock_locations_archive_state'),
    sa.CheckConstraint("lifecycle_status IN ('active', 'inactive', 'archived')", name='ck_stock_locations_lifecycle'),
    sa.CheckConstraint("lifecycle_status_before_archive IS NULL OR lifecycle_status_before_archive IN ('active', 'inactive')", name='ck_stock_locations_pre_archive'),
    sa.CheckConstraint("location_type IN ('main_store', 'engineering_store', 'technician_van', 'maintenance_room', 'quarantine', 'other')", name='ck_stock_locations_type'),
    sa.CheckConstraint('code = upper(btrim(code))', name='ck_stock_locations_code'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_stock_locations_code')
    )
    op.create_index('ix_stock_locations_lifecycle', 'stock_locations', ['lifecycle_status'], unique=False)
    op.create_index('ix_stock_locations_type', 'stock_locations', ['location_type'], unique=False)
    op.create_table('units_of_measure',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name_vi', sa.String(length=120), nullable=False),
    sa.Column('name_en', sa.String(length=120), nullable=True),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('quantity_precision', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('updated_by_user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint('code = upper(btrim(code))', name='ck_units_of_measure_code'),
    sa.CheckConstraint('quantity_precision BETWEEN 0 AND 3', name='ck_units_of_measure_precision'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_units_of_measure_code')
    )
    op.create_index('ix_units_of_measure_active', 'units_of_measure', ['is_active'], unique=False)
    op.create_table('spare_parts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('part_number', sa.String(length=80), nullable=False),
    sa.Column('name_vi', sa.String(length=200), nullable=False),
    sa.Column('name_en', sa.String(length=200), nullable=True),
    sa.Column('category_id', sa.UUID(), nullable=False),
    sa.Column('unit_of_measure_id', sa.UUID(), nullable=False),
    sa.Column('manufacturer_reference', sa.String(length=200), nullable=True),
    sa.Column('compatible_asset_types', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('lifecycle_status', sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
    sa.Column('lifecycle_status_before_archive', sa.String(length=20), nullable=True),
    sa.Column('minimum_stock', sa.Numeric(precision=18, scale=3), server_default=sa.text('0'), nullable=False),
    sa.Column('reorder_point', sa.Numeric(precision=18, scale=3), server_default=sa.text('0'), nullable=False),
    sa.Column('maximum_stock', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('unit_cost', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('currency_code', sa.String(length=3), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('archive_reason', sa.Text(), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('updated_by_user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint("((lifecycle_status = 'archived' AND archived_at IS NOT NULL AND archive_reason IS NOT NULL) OR (lifecycle_status <> 'archived' AND archived_at IS NULL AND archive_reason IS NULL))", name='ck_spare_parts_archive_state'),
    sa.CheckConstraint("jsonb_typeof(compatible_asset_types) = 'array'", name='ck_spare_parts_asset_types'),
    sa.CheckConstraint("lifecycle_status IN ('active', 'inactive', 'archived')", name='ck_spare_parts_lifecycle'),
    sa.CheckConstraint("lifecycle_status_before_archive IS NULL OR lifecycle_status_before_archive IN ('active', 'inactive')", name='ck_spare_parts_pre_archive'),
    sa.CheckConstraint('minimum_stock >= 0 AND reorder_point >= minimum_stock AND (maximum_stock IS NULL OR maximum_stock >= reorder_point)', name='ck_spare_parts_thresholds'),
    sa.CheckConstraint('part_number = upper(btrim(part_number))', name='ck_spare_parts_number'),
    sa.CheckConstraint('unit_cost IS NULL OR unit_cost >= 0', name='ck_spare_parts_unit_cost'),
    sa.ForeignKeyConstraint(['category_id'], ['part_categories.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['unit_of_measure_id'], ['units_of_measure.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('part_number', name='uq_spare_parts_number')
    )
    op.create_index('ix_spare_parts_category', 'spare_parts', ['category_id'], unique=False)
    op.create_index('ix_spare_parts_lifecycle', 'spare_parts', ['lifecycle_status'], unique=False)
    op.create_index('ix_spare_parts_name_vi', 'spare_parts', ['name_vi'], unique=False)
    op.create_index('ix_spare_parts_uom', 'spare_parts', ['unit_of_measure_id'], unique=False)
    op.create_table('inventory_positions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('part_id', sa.UUID(), nullable=False),
    sa.Column('stock_location_id', sa.UUID(), nullable=False),
    sa.Column('on_hand_quantity', sa.Numeric(precision=18, scale=3), server_default=sa.text('0'), nullable=False),
    sa.Column('reserved_quantity', sa.Numeric(precision=18, scale=3), server_default=sa.text('0'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint('on_hand_quantity >= 0 AND reserved_quantity >= 0 AND reserved_quantity <= on_hand_quantity', name='ck_inventory_positions_quantities'),
    sa.ForeignKeyConstraint(['part_id'], ['spare_parts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['stock_location_id'], ['stock_locations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('part_id', 'stock_location_id', name='uq_inventory_position_part_location')
    )
    op.create_index('ix_inventory_positions_location', 'inventory_positions', ['stock_location_id'], unique=False)
    op.create_index('ix_inventory_positions_part', 'inventory_positions', ['part_id'], unique=False)
    op.create_table('part_reorder_configurations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('part_id', sa.UUID(), nullable=False),
    sa.Column('stock_location_id', sa.UUID(), nullable=False),
    sa.Column('minimum_stock', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('reorder_point', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('maximum_stock', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('updated_by_user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint('minimum_stock >= 0 AND reorder_point >= minimum_stock AND (maximum_stock IS NULL OR maximum_stock >= reorder_point)', name='ck_part_reorder_thresholds'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['part_id'], ['spare_parts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['stock_location_id'], ['stock_locations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('part_id', 'stock_location_id', name='uq_part_reorder_part_location')
    )
    op.create_index('ix_part_reorder_location', 'part_reorder_configurations', ['stock_location_id'], unique=False)
    op.create_index('ix_part_reorder_part', 'part_reorder_configurations', ['part_id'], unique=False)
    op.create_table('inventory_movements',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('movement_number', sa.String(length=50), nullable=False),
    sa.Column('operation_id', sa.UUID(), nullable=False),
    sa.Column('part_id', sa.UUID(), nullable=False),
    sa.Column('stock_location_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('unit_of_measure_id', sa.UUID(), nullable=False),
    sa.Column('movement_type', sa.String(length=40), nullable=False),
    sa.Column('business_reference', sa.String(length=160), nullable=False),
    sa.Column('actor_user_id', sa.UUID(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('work_order_id', sa.UUID(), nullable=True),
    sa.Column('source_location_id', sa.UUID(), nullable=True),
    sa.Column('destination_location_id', sa.UUID(), nullable=True),
    sa.Column('transfer_group_id', sa.UUID(), nullable=True),
    sa.Column('unit_cost_snapshot', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('resulting_on_hand_quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('resulting_reserved_quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('idempotency_key', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("((movement_type IN ('transfer_out', 'transfer_in') AND transfer_group_id IS NOT NULL AND source_location_id IS NOT NULL AND destination_location_id IS NOT NULL AND source_location_id <> destination_location_id) OR (movement_type NOT IN ('transfer_out', 'transfer_in') AND transfer_group_id IS NULL))", name='ck_inventory_movements_transfer'),
    sa.CheckConstraint("movement_type IN ('opening_balance', 'receipt', 'issue', 'return', 'transfer_out', 'transfer_in', 'adjustment_increase', 'adjustment_decrease', 'damaged_scrapped')", name='ck_inventory_movements_type'),
    sa.CheckConstraint('quantity > 0', name='ck_inventory_movements_quantity'),
    sa.CheckConstraint('resulting_on_hand_quantity >= 0 AND resulting_reserved_quantity >= 0 AND resulting_reserved_quantity <= resulting_on_hand_quantity', name='ck_inventory_movements_result'),
    sa.CheckConstraint('unit_cost_snapshot IS NULL OR unit_cost_snapshot >= 0', name='ck_inventory_movements_cost'),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['destination_location_id'], ['stock_locations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operation_id'], ['inventory_operations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['part_id'], ['spare_parts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_location_id'], ['stock_locations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['stock_location_id'], ['stock_locations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['unit_of_measure_id'], ['units_of_measure.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('movement_number', name='uq_inventory_movements_number'),
    sa.UniqueConstraint('operation_id', 'movement_type', name='uq_inventory_movement_operation')
    )
    op.create_index('ix_inventory_movements_location', 'inventory_movements', ['stock_location_id', 'occurred_at'], unique=False)
    op.create_index('ix_inventory_movements_part', 'inventory_movements', ['part_id', 'occurred_at'], unique=False)
    op.create_index('ix_inventory_movements_transfer', 'inventory_movements', ['transfer_group_id'], unique=False)
    op.create_index('ix_inventory_movements_work_order', 'inventory_movements', ['work_order_id'], unique=False)
    op.create_table('work_order_part_requirements',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('work_order_id', sa.UUID(), nullable=False),
    sa.Column('part_id', sa.UUID(), nullable=False),
    sa.Column('planned_quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('required_by_date', sa.Date(), nullable=True),
    sa.Column('source_stock_location_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=30), server_default=sa.text("'planned'"), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('updated_by_user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint("status IN ('planned', 'partially_reserved', 'reserved', 'partially_issued', 'issued', 'partially_consumed', 'fulfilled', 'cancelled')", name='ck_wo_part_requirements_status'),
    sa.CheckConstraint('planned_quantity > 0', name='ck_wo_part_requirements_quantity'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['part_id'], ['spare_parts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_stock_location_id'], ['stock_locations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('work_order_id', 'part_id', 'source_stock_location_id', name='uq_wo_part_requirement_line')
    )
    op.create_index('ix_wo_part_requirements_part', 'work_order_part_requirements', ['part_id'], unique=False)
    op.create_index('ix_wo_part_requirements_status', 'work_order_part_requirements', ['status'], unique=False)
    op.create_index('ix_wo_part_requirements_work_order', 'work_order_part_requirements', ['work_order_id'], unique=False)
    op.create_table('inventory_attachments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('movement_id', sa.UUID(), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('media_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=False),
    sa.Column('uploaded_by_user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by_user_id', sa.UUID(), nullable=True),
    sa.CheckConstraint("category IN ('adjustment_evidence', 'damage_evidence', 'receipt_evidence', 'transfer_evidence', 'other')", name='ck_inventory_attachments_category'),
    sa.CheckConstraint('length(checksum) = 64', name='ck_inventory_attachments_checksum'),
    sa.CheckConstraint('size_bytes > 0', name='ck_inventory_attachments_size'),
    sa.ForeignKeyConstraint(['deleted_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['movement_id'], ['inventory_movements.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_key', name='uq_inventory_attachments_storage_key')
    )
    op.create_index('ix_inventory_attachments_active', 'inventory_attachments', ['movement_id', 'deleted_at'], unique=False)
    op.create_index('ix_inventory_attachments_movement', 'inventory_attachments', ['movement_id'], unique=False)
    op.create_table('stock_reservations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('reservation_number', sa.String(length=50), nullable=False),
    sa.Column('operation_id', sa.UUID(), nullable=False),
    sa.Column('requirement_id', sa.UUID(), nullable=False),
    sa.Column('work_order_id', sa.UUID(), nullable=False),
    sa.Column('part_id', sa.UUID(), nullable=False),
    sa.Column('stock_location_id', sa.UUID(), nullable=False),
    sa.Column('occurrence_number', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('status', sa.String(length=30), server_default=sa.text("'active'"), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('replaced_by_reservation_id', sa.UUID(), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint("status IN ('active', 'partially_issued', 'fulfilled', 'released', 'expired', 'replaced')", name='ck_stock_reservations_status'),
    sa.CheckConstraint('occurrence_number > 0', name='ck_stock_reservations_occurrence'),
    sa.CheckConstraint('quantity > 0', name='ck_stock_reservations_quantity'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operation_id'], ['inventory_operations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['part_id'], ['spare_parts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['replaced_by_reservation_id'], ['stock_reservations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['requirement_id'], ['work_order_part_requirements.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['stock_location_id'], ['stock_locations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('operation_id', name='uq_stock_reservations_operation'),
    sa.UniqueConstraint('requirement_id', 'occurrence_number', name='uq_stock_reservation_requirement_occurrence'),
    sa.UniqueConstraint('reservation_number', name='uq_stock_reservations_number')
    )
    op.create_index('ix_stock_reservations_position', 'stock_reservations', ['part_id', 'stock_location_id'], unique=False)
    op.create_index('ix_stock_reservations_requirement', 'stock_reservations', ['requirement_id'], unique=False)
    op.create_index('ix_stock_reservations_work_order', 'stock_reservations', ['work_order_id'], unique=False)
    op.create_index('uq_stock_reservation_active_requirement', 'stock_reservations', ['requirement_id'], unique=True, postgresql_where=sa.text("status IN ('active', 'partially_issued')"))
    op.create_table('stock_reservation_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('reservation_id', sa.UUID(), nullable=False),
    sa.Column('operation_id', sa.UUID(), nullable=False),
    sa.Column('event_type', sa.String(length=30), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('actor_user_id', sa.UUID(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("event_type IN ('reserved', 'released', 'expired', 'replaced', 'issued', 'fulfilled')", name='ck_stock_reservation_events_type'),
    sa.CheckConstraint('quantity > 0', name='ck_stock_reservation_events_quantity'),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operation_id'], ['inventory_operations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reservation_id'], ['stock_reservations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('operation_id', 'event_type', name='uq_reservation_event_operation')
    )
    op.create_index('ix_stock_reservation_events_reservation', 'stock_reservation_events', ['reservation_id', 'occurred_at'], unique=False)
    op.create_table('work_order_part_issues',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('issue_number', sa.String(length=50), nullable=False),
    sa.Column('operation_id', sa.UUID(), nullable=False),
    sa.Column('work_order_id', sa.UUID(), nullable=False),
    sa.Column('requirement_id', sa.UUID(), nullable=True),
    sa.Column('reservation_id', sa.UUID(), nullable=True),
    sa.Column('part_id', sa.UUID(), nullable=False),
    sa.Column('stock_location_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('reserved_quantity_used', sa.Numeric(precision=18, scale=3), server_default=sa.text('0'), nullable=False),
    sa.Column('issued_to_user_id', sa.UUID(), nullable=True),
    sa.Column('issued_by_user_id', sa.UUID(), nullable=False),
    sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('movement_id', sa.UUID(), nullable=False),
    sa.CheckConstraint('quantity > 0 AND reserved_quantity_used >= 0 AND reserved_quantity_used <= quantity', name='ck_wo_part_issues_quantity'),
    sa.ForeignKeyConstraint(['issued_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['issued_to_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['movement_id'], ['inventory_movements.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operation_id'], ['inventory_operations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['part_id'], ['spare_parts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['requirement_id'], ['work_order_part_requirements.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reservation_id'], ['stock_reservations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['stock_location_id'], ['stock_locations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('issue_number', name='uq_wo_part_issues_number'),
    sa.UniqueConstraint('movement_id', name='uq_wo_part_issues_movement'),
    sa.UniqueConstraint('operation_id', name='uq_wo_part_issues_operation')
    )
    op.create_index('ix_wo_part_issues_requirement', 'work_order_part_issues', ['requirement_id'], unique=False)
    op.create_index('ix_wo_part_issues_reservation', 'work_order_part_issues', ['reservation_id'], unique=False)
    op.create_index('ix_wo_part_issues_work_order', 'work_order_part_issues', ['work_order_id', 'issued_at'], unique=False)
    op.create_table('work_order_part_consumptions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('operation_id', sa.UUID(), nullable=False),
    sa.Column('issue_id', sa.UUID(), nullable=False),
    sa.Column('work_order_id', sa.UUID(), nullable=False),
    sa.Column('part_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('consumed_by_user_id', sa.UUID(), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.CheckConstraint('quantity > 0', name='ck_wo_part_consumptions_quantity'),
    sa.ForeignKeyConstraint(['consumed_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['issue_id'], ['work_order_part_issues.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operation_id'], ['inventory_operations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['part_id'], ['spare_parts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('operation_id', name='uq_wo_part_consumptions_operation')
    )
    op.create_index('ix_wo_part_consumptions_issue', 'work_order_part_consumptions', ['issue_id', 'consumed_at'], unique=False)
    op.create_index('ix_wo_part_consumptions_work_order', 'work_order_part_consumptions', ['work_order_id'], unique=False)
    op.create_table('work_order_part_returns',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('return_number', sa.String(length=50), nullable=False),
    sa.Column('operation_id', sa.UUID(), nullable=False),
    sa.Column('issue_id', sa.UUID(), nullable=False),
    sa.Column('work_order_id', sa.UUID(), nullable=False),
    sa.Column('part_id', sa.UUID(), nullable=False),
    sa.Column('stock_location_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('returned_by_user_id', sa.UUID(), nullable=False),
    sa.Column('returned_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('movement_id', sa.UUID(), nullable=False),
    sa.CheckConstraint('quantity > 0', name='ck_wo_part_returns_quantity'),
    sa.ForeignKeyConstraint(['issue_id'], ['work_order_part_issues.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['movement_id'], ['inventory_movements.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operation_id'], ['inventory_operations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['part_id'], ['spare_parts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['returned_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['stock_location_id'], ['stock_locations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('movement_id', name='uq_wo_part_returns_movement'),
    sa.UniqueConstraint('operation_id', name='uq_wo_part_returns_operation'),
    sa.UniqueConstraint('return_number', name='uq_wo_part_returns_number')
    )
    op.create_index('ix_wo_part_returns_issue', 'work_order_part_returns', ['issue_id', 'returned_at'], unique=False)
    op.create_index('ix_wo_part_returns_work_order', 'work_order_part_returns', ['work_order_id'], unique=False)
    op.execute(
        """
        CREATE FUNCTION reject_inventory_history_mutation() RETURNS trigger AS $$
        BEGIN
            IF current_setting('app.demo_reset', true) = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'inventory history is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table_name in (
        "inventory_movements",
        "stock_reservation_events",
        "work_order_part_issues",
        "work_order_part_consumptions",
        "work_order_part_returns",
    ):
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_append_only
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_inventory_history_mutation()
            """
        )


def downgrade() -> None:
    """Remove PM6 inventory entities without changing PM1-PM5 data."""

    for table_name in (
        "work_order_part_returns",
        "work_order_part_consumptions",
        "work_order_part_issues",
        "stock_reservation_events",
        "inventory_movements",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table_name}_append_only ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS reject_inventory_history_mutation()")
    op.drop_index('ix_wo_part_returns_work_order', table_name='work_order_part_returns')
    op.drop_index('ix_wo_part_returns_issue', table_name='work_order_part_returns')
    op.drop_table('work_order_part_returns')
    op.drop_index('ix_wo_part_consumptions_work_order', table_name='work_order_part_consumptions')
    op.drop_index('ix_wo_part_consumptions_issue', table_name='work_order_part_consumptions')
    op.drop_table('work_order_part_consumptions')
    op.drop_index('ix_wo_part_issues_work_order', table_name='work_order_part_issues')
    op.drop_index('ix_wo_part_issues_reservation', table_name='work_order_part_issues')
    op.drop_index('ix_wo_part_issues_requirement', table_name='work_order_part_issues')
    op.drop_table('work_order_part_issues')
    op.drop_index('ix_stock_reservation_events_reservation', table_name='stock_reservation_events')
    op.drop_table('stock_reservation_events')
    op.drop_index('uq_stock_reservation_active_requirement', table_name='stock_reservations', postgresql_where=sa.text("status IN ('active', 'partially_issued')"))
    op.drop_index('ix_stock_reservations_work_order', table_name='stock_reservations')
    op.drop_index('ix_stock_reservations_requirement', table_name='stock_reservations')
    op.drop_index('ix_stock_reservations_position', table_name='stock_reservations')
    op.drop_table('stock_reservations')
    op.drop_index('ix_inventory_attachments_movement', table_name='inventory_attachments')
    op.drop_index('ix_inventory_attachments_active', table_name='inventory_attachments')
    op.drop_table('inventory_attachments')
    op.drop_index('ix_wo_part_requirements_work_order', table_name='work_order_part_requirements')
    op.drop_index('ix_wo_part_requirements_status', table_name='work_order_part_requirements')
    op.drop_index('ix_wo_part_requirements_part', table_name='work_order_part_requirements')
    op.drop_table('work_order_part_requirements')
    op.drop_index('ix_inventory_movements_work_order', table_name='inventory_movements')
    op.drop_index('ix_inventory_movements_transfer', table_name='inventory_movements')
    op.drop_index('ix_inventory_movements_part', table_name='inventory_movements')
    op.drop_index('ix_inventory_movements_location', table_name='inventory_movements')
    op.drop_table('inventory_movements')
    op.drop_index('ix_part_reorder_part', table_name='part_reorder_configurations')
    op.drop_index('ix_part_reorder_location', table_name='part_reorder_configurations')
    op.drop_table('part_reorder_configurations')
    op.drop_index('ix_inventory_positions_part', table_name='inventory_positions')
    op.drop_index('ix_inventory_positions_location', table_name='inventory_positions')
    op.drop_table('inventory_positions')
    op.drop_index('ix_spare_parts_uom', table_name='spare_parts')
    op.drop_index('ix_spare_parts_name_vi', table_name='spare_parts')
    op.drop_index('ix_spare_parts_lifecycle', table_name='spare_parts')
    op.drop_index('ix_spare_parts_category', table_name='spare_parts')
    op.drop_table('spare_parts')
    op.drop_index('ix_units_of_measure_active', table_name='units_of_measure')
    op.drop_table('units_of_measure')
    op.drop_index('ix_stock_locations_type', table_name='stock_locations')
    op.drop_index('ix_stock_locations_lifecycle', table_name='stock_locations')
    op.drop_table('stock_locations')
    op.drop_index('ix_part_categories_active', table_name='part_categories')
    op.drop_table('part_categories')
    op.drop_index('ix_inventory_operations_created_at', table_name='inventory_operations')
    op.drop_index('ix_inventory_operations_actor', table_name='inventory_operations')
    op.drop_table('inventory_operations')
    op.execute("DROP SEQUENCE part_return_number_seq")
    op.execute("DROP SEQUENCE part_issue_number_seq")
    op.execute("DROP SEQUENCE stock_reservation_number_seq")
    op.execute("DROP SEQUENCE inventory_movement_number_seq")
