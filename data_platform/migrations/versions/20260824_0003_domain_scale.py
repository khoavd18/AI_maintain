"""Add Stage 10 multi-domain source, raw, and audit contracts.

Revision ID: 20260824_dp0003
Revises: 20260824_dp0002
Create Date: 2026-08-24 14:00:00
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260824_dp0003"
down_revision: str | None = "20260824_dp0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create additive contracts without changing the application Alembic head."""

    op.execute("CREATE SCHEMA IF NOT EXISTS analytics_compat")
    op.execute(
        """
        CREATE TABLE analytics_compat.work_order_status_history (
            event_id uuid PRIMARY KEY,
            work_order_id uuid NOT NULL REFERENCES public.work_orders(id) ON DELETE RESTRICT,
            sequence_number integer NOT NULL CHECK (sequence_number > 0),
            status text NOT NULL CHECK (
                status IN (
                    'planned', 'assigned', 'in_progress', 'on_hold',
                    'completed', 'verified', 'cancelled'
                )
            ),
            transitioned_at timestamptz NOT NULL,
            source_available_at timestamptz NOT NULL,
            is_late_arriving boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT current_timestamp,
            UNIQUE (work_order_id, sequence_number)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_s10_status_work_order_time "
        "ON analytics_compat.work_order_status_history "
        "(work_order_id, transitioned_at, sequence_number)"
    )
    op.execute(
        "CREATE INDEX ix_s10_status_available_id "
        "ON analytics_compat.work_order_status_history (source_available_at, event_id)"
    )
    op.execute(
        """
        CREATE TABLE analytics_compat.work_order_cost_facts (
            work_order_id uuid PRIMARY KEY
                REFERENCES public.work_orders(id) ON DELETE RESTRICT,
            estimated_labor_cost numeric(14, 2) NOT NULL CHECK (estimated_labor_cost >= 0),
            actual_labor_cost numeric(14, 2) NOT NULL CHECK (actual_labor_cost >= 0),
            planned_part_cost numeric(14, 2) NOT NULL CHECK (planned_part_cost >= 0),
            actual_part_cost numeric(14, 2) NOT NULL CHECK (actual_part_cost >= 0),
            external_service_cost numeric(14, 2) NOT NULL
                CHECK (external_service_cost >= 0),
            total_estimated_cost numeric(14, 2) NOT NULL
                CHECK (total_estimated_cost >= 0),
            total_actual_cost numeric(14, 2) NOT NULL CHECK (total_actual_cost >= 0),
            cost_variance numeric(14, 2) NOT NULL,
            currency_code char(3) NOT NULL CHECK (currency_code = upper(currency_code)),
            source_updated_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT current_timestamp,
            CONSTRAINT ck_s10_cost_reconciliation CHECK (
                total_estimated_cost = estimated_labor_cost + planned_part_cost
                AND total_actual_cost = actual_labor_cost + actual_part_cost
                    + external_service_cost
                AND cost_variance = total_actual_cost - total_estimated_cost
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_s10_cost_updated_id "
        "ON analytics_compat.work_order_cost_facts (source_updated_at, work_order_id)"
    )
    op.execute(
        """
        CREATE TABLE analytics_compat.ticket_work_order_links (
            ticket_id text PRIMARY KEY
                REFERENCES public.maintenance_tickets(ticket_id) ON DELETE CASCADE,
            work_order_id uuid NOT NULL UNIQUE
                REFERENCES public.work_orders(id) ON DELETE RESTRICT,
            linked_at timestamptz NOT NULL,
            source_system text NOT NULL DEFAULT 'stage10_synthetic'
        )
        """
    )

    op.execute(
        """
        CREATE VIEW analytics_source.work_order_status_history AS
        SELECT
            h.event_id AS source_id,
            h.event_id,
            h.work_order_id,
            w.work_order_number,
            a.location_id AS site_id,
            w.asset_id,
            h.sequence_number,
            h.status,
            h.transitioned_at,
            lead(h.transitioned_at) OVER (
                PARTITION BY h.work_order_id ORDER BY h.sequence_number
            ) AS next_transitioned_at,
            h.is_late_arriving,
            h.source_available_at,
            h.created_at
        FROM analytics_compat.work_order_status_history AS h
        JOIN public.work_orders AS w ON w.id = h.work_order_id
        JOIN public.assets AS a ON a.asset_id = w.asset_id
        """
    )
    op.execute(
        """
        CREATE VIEW analytics_source.tickets AS
        SELECT
            t.ticket_id AS source_id,
            t.ticket_id,
            t.asset_id,
            a.location_id AS site_id,
            l.work_order_id,
            t.priority AS severity,
            t.priority,
            t.status,
            t.failure_category AS category,
            t.issue_description,
            t.assigned_user_id,
            t.technician_id,
            t.created_at AS opened_at,
            t.first_response_at,
            t.resolved_at,
            t.closed_at,
            t.manager_note AS resolution_summary,
            t.note AS technician_note,
            t.reopen_count,
            t.updated_at AS source_available_at,
            t.updated_at AS source_updated_at
        FROM public.maintenance_tickets AS t
        JOIN public.assets AS a ON a.asset_id = t.asset_id
        LEFT JOIN analytics_compat.ticket_work_order_links AS l
            ON l.ticket_id = t.ticket_id
        """
    )
    op.execute(
        """
        CREATE VIEW analytics_source.ticket_events AS
        SELECT
            e.id AS source_id,
            e.id AS event_id,
            e.ticket_id,
            'sla'::text AS event_domain,
            e.event_type,
            e.clock_type,
            e.occurrence_number,
            e.occurred_at,
            e.details,
            e.created_by_user_id,
            e.created_at AS source_available_at
        FROM public.ticket_sla_events AS e
        UNION ALL
        SELECT
            e.id AS source_id,
            e.id AS event_id,
            e.ticket_id,
            'escalation'::text AS event_domain,
            e.rule_code AS event_type,
            e.clock_type,
            e.occurrence_number,
            e.detected_at AS occurred_at,
            e.details,
            e.created_by_user_id,
            e.created_at AS source_available_at
        FROM public.ticket_escalation_events AS e
        """
    )
    op.execute(
        """
        CREATE VIEW analytics_source.spare_parts AS
        SELECT
            p.id AS source_id,
            p.id AS part_id,
            p.part_number,
            p.name_vi AS part_name,
            p.category_id,
            c.code AS category_code,
            p.unit_of_measure_id,
            u.code AS unit_code,
            p.lifecycle_status,
            p.minimum_stock,
            p.reorder_point,
            p.maximum_stock,
            p.unit_cost,
            p.currency_code,
            p.updated_at AS source_available_at,
            p.updated_at AS source_updated_at
        FROM public.spare_parts AS p
        JOIN public.part_categories AS c ON c.id = p.category_id
        JOIN public.units_of_measure AS u ON u.id = p.unit_of_measure_id
        """
    )
    op.execute(
        """
        CREATE VIEW analytics_source.inventory_movements AS
        SELECT
            m.id AS source_id,
            m.id AS movement_id,
            m.movement_number,
            m.operation_id,
            m.part_id,
            m.stock_location_id,
            m.quantity,
            m.movement_type,
            m.business_reference,
            m.actor_user_id,
            m.occurred_at,
            m.work_order_id,
            m.unit_cost_snapshot,
            m.resulting_on_hand_quantity,
            m.resulting_reserved_quantity,
            m.created_at AS source_available_at
        FROM public.inventory_movements AS m
        """
    )
    op.execute(
        """
        CREATE VIEW analytics_source.work_order_costs AS
        SELECT
            c.work_order_id AS source_id,
            c.work_order_id,
            w.work_order_number,
            a.location_id AS site_id,
            w.asset_id,
            c.estimated_labor_cost,
            c.actual_labor_cost,
            c.planned_part_cost,
            c.actual_part_cost,
            c.external_service_cost,
            c.total_estimated_cost,
            c.total_actual_cost,
            c.cost_variance,
            c.currency_code,
            c.source_updated_at AS source_available_at,
            c.source_updated_at
        FROM analytics_compat.work_order_cost_facts AS c
        JOIN public.work_orders AS w ON w.id = c.work_order_id
        JOIN public.assets AS a ON a.asset_id = w.asset_id
        """
    )

    _create_raw_tables()
    _create_audit_tables()

    op.execute(
        "CREATE INDEX ix_s10_tickets_updated_id "
        "ON public.maintenance_tickets (updated_at, ticket_id)"
    )
    op.execute(
        "CREATE INDEX ix_s10_ticket_sla_events_created_id "
        "ON public.ticket_sla_events (created_at, id)"
    )
    op.execute(
        "CREATE INDEX ix_s10_ticket_escalations_created_id "
        "ON public.ticket_escalation_events (created_at, id)"
    )
    op.execute(
        "CREATE INDEX ix_s10_spare_parts_updated_id "
        "ON public.spare_parts (updated_at, id)"
    )
    op.execute(
        "CREATE INDEX ix_s10_inventory_movements_created_id "
        "ON public.inventory_movements (created_at, id)"
    )
    op.execute(
        "COMMENT ON SCHEMA analytics_compat IS "
        "'Data Platform-owned compatibility facts absent from the application ORM'"
    )


def _create_raw_tables() -> None:
    op.execute(
        """
        CREATE TABLE raw.work_order_status_history (
            ingestion_batch_id uuid NOT NULL,
            event_id uuid NOT NULL,
            work_order_id uuid NOT NULL,
            work_order_number text NOT NULL,
            site_id uuid NOT NULL,
            asset_id text NOT NULL,
            sequence_number integer NOT NULL,
            status text NOT NULL,
            transitioned_at timestamptz NOT NULL,
            next_transitioned_at timestamptz,
            is_late_arriving boolean NOT NULL,
            source_available_at timestamptz NOT NULL,
            source_extracted_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (ingestion_batch_id, event_id),
            UNIQUE (event_id),
            CHECK (next_transitioned_at IS NULL OR next_transitioned_at >= transitioned_at)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_raw_s10_status_work_order_sequence "
        "ON raw.work_order_status_history (work_order_id, sequence_number)"
    )
    op.execute(
        """
        CREATE TABLE raw.tickets (
            ingestion_batch_id uuid NOT NULL,
            ticket_id text NOT NULL,
            asset_id text NOT NULL,
            site_id uuid NOT NULL,
            work_order_id uuid,
            severity text NOT NULL,
            priority text NOT NULL,
            status text NOT NULL,
            category text NOT NULL,
            issue_description text NOT NULL,
            assigned_user_id uuid,
            technician_id text NOT NULL,
            opened_at timestamptz NOT NULL,
            first_response_at timestamptz,
            resolved_at timestamptz,
            closed_at timestamptz,
            resolution_summary text,
            technician_note text,
            reopen_count integer NOT NULL,
            source_available_at timestamptz NOT NULL,
            source_extracted_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (ingestion_batch_id, ticket_id),
            UNIQUE (ticket_id, source_available_at),
            CHECK (resolved_at IS NULL OR resolved_at >= opened_at),
            CHECK (closed_at IS NULL OR closed_at >= resolved_at)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_raw_s10_tickets_latest "
        "ON raw.tickets (ticket_id, source_available_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE raw.ticket_events (
            ingestion_batch_id uuid NOT NULL,
            event_id uuid NOT NULL,
            ticket_id text NOT NULL,
            event_domain text NOT NULL CHECK (event_domain IN ('sla', 'escalation')),
            event_type text NOT NULL,
            clock_type text,
            occurrence_number integer NOT NULL CHECK (occurrence_number > 0),
            occurred_at timestamptz NOT NULL,
            details jsonb,
            created_by_user_id uuid NOT NULL,
            source_available_at timestamptz NOT NULL,
            source_extracted_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (ingestion_batch_id, event_id),
            UNIQUE (event_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_raw_s10_ticket_events_ticket_time "
        "ON raw.ticket_events (ticket_id, occurred_at)"
    )
    op.execute(
        """
        CREATE TABLE raw.spare_parts (
            ingestion_batch_id uuid NOT NULL,
            part_id uuid NOT NULL,
            part_number text NOT NULL,
            part_name text NOT NULL,
            category_id uuid NOT NULL,
            category_code text NOT NULL,
            unit_of_measure_id uuid NOT NULL,
            unit_code text NOT NULL,
            lifecycle_status text NOT NULL,
            minimum_stock numeric NOT NULL,
            reorder_point numeric NOT NULL,
            maximum_stock numeric,
            unit_cost numeric,
            currency_code text,
            source_available_at timestamptz NOT NULL,
            source_extracted_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (ingestion_batch_id, part_id),
            UNIQUE (part_id, source_available_at)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_raw_s10_parts_latest "
        "ON raw.spare_parts (part_id, source_available_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE raw.inventory_movements (
            ingestion_batch_id uuid NOT NULL,
            movement_id uuid NOT NULL,
            movement_number text NOT NULL,
            operation_id uuid NOT NULL,
            part_id uuid NOT NULL,
            stock_location_id uuid NOT NULL,
            quantity numeric NOT NULL CHECK (quantity > 0),
            movement_type text NOT NULL,
            business_reference text NOT NULL,
            actor_user_id uuid NOT NULL,
            occurred_at timestamptz NOT NULL,
            work_order_id uuid,
            unit_cost_snapshot numeric,
            resulting_on_hand_quantity numeric NOT NULL CHECK (
                resulting_on_hand_quantity >= 0
            ),
            resulting_reserved_quantity numeric NOT NULL CHECK (
                resulting_reserved_quantity >= 0
                AND resulting_reserved_quantity <= resulting_on_hand_quantity
            ),
            source_available_at timestamptz NOT NULL,
            source_extracted_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (ingestion_batch_id, movement_id),
            UNIQUE (movement_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_raw_s10_inventory_part_time "
        "ON raw.inventory_movements (part_id, occurred_at)"
    )
    op.execute(
        """
        CREATE TABLE raw.work_order_costs (
            ingestion_batch_id uuid NOT NULL,
            work_order_id uuid NOT NULL,
            work_order_number text NOT NULL,
            site_id uuid NOT NULL,
            asset_id text NOT NULL,
            estimated_labor_cost numeric(14, 2) NOT NULL,
            actual_labor_cost numeric(14, 2) NOT NULL,
            planned_part_cost numeric(14, 2) NOT NULL,
            actual_part_cost numeric(14, 2) NOT NULL,
            external_service_cost numeric(14, 2) NOT NULL,
            total_estimated_cost numeric(14, 2) NOT NULL,
            total_actual_cost numeric(14, 2) NOT NULL,
            cost_variance numeric(14, 2) NOT NULL,
            currency_code char(3) NOT NULL,
            source_available_at timestamptz NOT NULL,
            source_extracted_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (ingestion_batch_id, work_order_id),
            UNIQUE (work_order_id, source_available_at),
            CHECK (total_estimated_cost = estimated_labor_cost + planned_part_cost),
            CHECK (
                total_actual_cost = actual_labor_cost + actual_part_cost
                    + external_service_cost
            ),
            CHECK (cost_variance = total_actual_cost - total_estimated_cost)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_raw_s10_costs_latest "
        "ON raw.work_order_costs (work_order_id, source_available_at DESC)"
    )


def _create_audit_tables() -> None:
    op.execute(
        """
        CREATE TABLE audit.domain_watermarks (
            domain_name text PRIMARY KEY,
            source_available_at timestamptz NOT NULL,
            source_id text NOT NULL,
            version integer NOT NULL DEFAULT 1 CHECK (version > 0),
            batch_id uuid,
            advanced_at timestamptz NOT NULL DEFAULT current_timestamp
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit.domain_extraction_batches (
            batch_id uuid PRIMARY KEY,
            domain_name text NOT NULL,
            run_id text NOT NULL,
            phase text NOT NULL CHECK (phase IN ('baseline', 'incremental', 'empty')),
            status text NOT NULL CHECK (
                status IN ('extracted', 'raw_loaded', 'complete', 'empty', 'failed')
            ),
            lower_available_at timestamptz NOT NULL,
            lower_source_id text NOT NULL,
            upper_available_at timestamptz,
            upper_source_id text,
            row_count bigint NOT NULL CHECK (row_count >= 0),
            raw_inserted_count bigint CHECK (raw_inserted_count >= 0),
            object_key text NOT NULL,
            object_path text NOT NULL,
            object_sha256 char(64) NOT NULL,
            source_extracted_at timestamptz NOT NULL,
            raw_loaded_at timestamptz,
            completed_at timestamptz,
            error_message text,
            UNIQUE (domain_name, run_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit.domain_pipeline_runs (
            run_id text PRIMARY KEY,
            phase text NOT NULL CHECK (phase IN ('baseline', 'incremental', 'empty')),
            status text NOT NULL CHECK (status IN ('running', 'success', 'failed')),
            fault_domain text,
            started_at timestamptz NOT NULL DEFAULT current_timestamp,
            finished_at timestamptz,
            source_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
            raw_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
            warehouse_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
            retry_count integer NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
            failed_step text,
            error_message text,
            updated_at timestamptz NOT NULL DEFAULT current_timestamp
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit.stage10_dataset_load_chunks (
            dataset_run_id text NOT NULL,
            phase text NOT NULL,
            entity text NOT NULL,
            chunk_name text NOT NULL,
            file_sha256 char(64) NOT NULL,
            row_count bigint NOT NULL CHECK (row_count >= 0),
            loaded_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (dataset_run_id, phase, entity, chunk_name)
        )
        """
    )


def downgrade() -> None:
    """Remove only Data Platform-owned Stage 10 objects and measured indexes."""

    op.execute("DROP INDEX IF EXISTS public.ix_s10_inventory_movements_created_id")
    op.execute("DROP INDEX IF EXISTS public.ix_s10_spare_parts_updated_id")
    op.execute("DROP INDEX IF EXISTS public.ix_s10_ticket_escalations_created_id")
    op.execute("DROP INDEX IF EXISTS public.ix_s10_ticket_sla_events_created_id")
    op.execute("DROP INDEX IF EXISTS public.ix_s10_tickets_updated_id")
    op.execute("DROP TABLE IF EXISTS audit.stage10_dataset_load_chunks")
    op.execute("DROP TABLE IF EXISTS audit.domain_pipeline_runs")
    op.execute("DROP TABLE IF EXISTS audit.domain_extraction_batches")
    op.execute("DROP TABLE IF EXISTS audit.domain_watermarks")
    op.execute("DROP TABLE IF EXISTS raw.work_order_costs")
    op.execute("DROP TABLE IF EXISTS raw.inventory_movements")
    op.execute("DROP TABLE IF EXISTS raw.spare_parts")
    op.execute("DROP TABLE IF EXISTS raw.ticket_events")
    op.execute("DROP TABLE IF EXISTS raw.tickets")
    op.execute("DROP TABLE IF EXISTS raw.work_order_status_history")
    op.execute("DROP VIEW IF EXISTS analytics_source.work_order_costs")
    op.execute("DROP VIEW IF EXISTS analytics_source.inventory_movements")
    op.execute("DROP VIEW IF EXISTS analytics_source.spare_parts")
    op.execute("DROP VIEW IF EXISTS analytics_source.ticket_events")
    op.execute("DROP VIEW IF EXISTS analytics_source.tickets")
    op.execute("DROP VIEW IF EXISTS analytics_source.work_order_status_history")
    op.execute("DROP SCHEMA IF EXISTS analytics_compat CASCADE")
