"""Create the versioned source contract, raw layer, and pipeline audit state.

Revision ID: 20260824_dp0001
Revises: None
Create Date: 2026-08-24 12:00:00
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260824_dp0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add only Data Platform-owned schemas; leave application tables intact."""

    op.execute("CREATE SCHEMA IF NOT EXISTS analytics_source")
    op.execute("CREATE SCHEMA IF NOT EXISTS raw")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")

    op.execute(
        """
        CREATE VIEW analytics_source.sites AS
        SELECT
            l.id AS site_id,
            l.code AS site_code,
            l.name AS site_name,
            l.location_type,
            l.parent_id AS parent_site_id,
            l.is_active,
            l.created_at,
            l.updated_at
        FROM public.locations AS l
        """
    )
    op.execute(
        """
        CREATE VIEW analytics_source.assets AS
        SELECT
            a.asset_id,
            a.asset_name,
            a.location_id AS site_id,
            a.manufacturer,
            a.model,
            a.asset_type,
            a.criticality,
            a.lifecycle_status,
            a.operational_status,
            a.installed_at,
            a.created_at,
            a.updated_at
        FROM public.assets AS a
        """
    )
    op.execute(
        """
        CREATE VIEW analytics_source.technicians AS
        SELECT
            u.id AS technician_id,
            u.technician_id AS employee_code,
            u.display_name,
            u.role,
            u.is_active,
            u.created_at,
            u.updated_at
        FROM public.users AS u
        WHERE u.role = 'technician'
        """
    )
    op.execute(
        """
        CREATE VIEW analytics_source.work_orders AS
        SELECT
            w.id AS work_order_id,
            w.work_order_number,
            a.location_id AS site_id,
            w.asset_id,
            w.assigned_to_user_id AS assigned_technician_id,
            w.work_order_type,
            w.priority,
            w.status,
            w.title,
            w.description,
            w.created_at,
            w.scheduled_start_at,
            w.started_at,
            w.completed_at,
            w.due_date,
            w.estimated_duration_minutes,
            w.labor_minutes,
            w.completion_summary AS resolution_note,
            NULL::numeric(14, 2) AS estimated_cost,
            NULL::numeric(14, 2) AS actual_cost,
            w.updated_at
        FROM public.work_orders AS w
        JOIN public.assets AS a ON a.asset_id = w.asset_id
        """
    )
    op.execute(
        """
        CREATE VIEW analytics_source.maintenance_logs AS
        SELECT
            ml.log_id,
            ml.work_order_id,
            ml.asset_id,
            ml.maintenance_date,
            ml.maintenance_type,
            ml.technician_id,
            ml.inspection_result,
            ml.actions_taken,
            ml.technician_note,
            ml.maintenance_result,
            ml.created_at,
            ml.updated_at
        FROM public.maintenance_logs AS ml
        """
    )

    op.execute(
        """
        CREATE TABLE raw.sites (
            ingestion_batch_id uuid NOT NULL,
            site_id uuid NOT NULL,
            site_code text NOT NULL,
            site_name text NOT NULL,
            location_type text NOT NULL,
            parent_site_id uuid,
            is_active boolean NOT NULL,
            source_created_at timestamptz NOT NULL,
            source_updated_at timestamptz NOT NULL,
            source_extracted_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (ingestion_batch_id, site_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE raw.assets (
            ingestion_batch_id uuid NOT NULL,
            asset_id text NOT NULL,
            asset_name text NOT NULL,
            site_id uuid,
            manufacturer text,
            model text,
            asset_type text NOT NULL,
            criticality text NOT NULL,
            lifecycle_status text NOT NULL,
            operational_status text NOT NULL,
            installed_at timestamptz NOT NULL,
            source_created_at timestamptz NOT NULL,
            source_updated_at timestamptz NOT NULL,
            source_extracted_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (ingestion_batch_id, asset_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE raw.technicians (
            ingestion_batch_id uuid NOT NULL,
            technician_id uuid NOT NULL,
            employee_code text,
            display_name text NOT NULL,
            role text NOT NULL,
            is_active boolean NOT NULL,
            source_created_at timestamptz NOT NULL,
            source_updated_at timestamptz NOT NULL,
            source_extracted_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (ingestion_batch_id, technician_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE raw.work_orders (
            ingestion_batch_id uuid NOT NULL,
            work_order_id uuid NOT NULL,
            work_order_number text NOT NULL,
            site_id uuid,
            asset_id text NOT NULL,
            assigned_technician_id uuid,
            work_order_type text NOT NULL,
            priority text NOT NULL,
            status text NOT NULL,
            title text NOT NULL,
            description text,
            created_at timestamptz NOT NULL,
            scheduled_start_at timestamptz,
            started_at timestamptz,
            completed_at timestamptz,
            due_date date NOT NULL,
            estimated_duration_minutes integer NOT NULL,
            labor_minutes integer,
            resolution_note text,
            estimated_cost numeric(14, 2),
            actual_cost numeric(14, 2),
            source_updated_at timestamptz NOT NULL,
            source_extracted_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT current_timestamp,
            source_system text NOT NULL DEFAULT 'ai_maintenance_copilot',
            PRIMARY KEY (ingestion_batch_id, work_order_id),
            CONSTRAINT uq_raw_work_order_source_version
                UNIQUE (work_order_id, source_updated_at),
            CONSTRAINT ck_raw_work_order_chronology CHECK (
                created_at <= source_updated_at
                AND (started_at IS NULL OR started_at >= created_at)
                AND (completed_at IS NULL OR (
                    started_at IS NOT NULL AND completed_at >= started_at
                ))
            ),
            CONSTRAINT ck_raw_work_order_costs CHECK (
                (estimated_cost IS NULL OR estimated_cost >= 0)
                AND (actual_cost IS NULL OR actual_cost >= 0)
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_raw_work_orders_latest "
        "ON raw.work_orders (work_order_id, source_updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_raw_work_orders_site_created ON raw.work_orders (site_id, created_at)"
    )
    op.execute(
        "CREATE INDEX ix_raw_work_orders_status_priority ON raw.work_orders (status, priority)"
    )

    op.execute(
        """
        CREATE TABLE audit.pipeline_watermarks (
            pipeline_name text PRIMARY KEY,
            updated_at timestamptz NOT NULL,
            work_order_id uuid NOT NULL,
            version integer NOT NULL DEFAULT 1 CHECK (version > 0),
            advanced_at timestamptz NOT NULL DEFAULT current_timestamp,
            batch_id uuid
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit.extraction_batches (
            batch_id uuid PRIMARY KEY,
            pipeline_name text NOT NULL,
            run_id text NOT NULL,
            status text NOT NULL CHECK (
                status IN ('extracted', 'loaded', 'empty', 'failed')
            ),
            lower_updated_at timestamptz NOT NULL,
            lower_work_order_id uuid NOT NULL,
            upper_updated_at timestamptz,
            upper_work_order_id uuid,
            row_count bigint NOT NULL CHECK (row_count >= 0),
            object_key text NOT NULL,
            object_path text NOT NULL,
            object_sha256 char(64) NOT NULL,
            source_extracted_at timestamptz NOT NULL,
            loaded_at timestamptz,
            error_message text,
            UNIQUE (pipeline_name, run_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit.pipeline_run_audit (
            dag_id text NOT NULL,
            dag_run_id text NOT NULL,
            run_type text NOT NULL,
            status text NOT NULL CHECK (status IN ('running', 'success', 'failed')),
            started_at timestamptz NOT NULL,
            finished_at timestamptz,
            source_work_order_count bigint,
            raw_work_order_count bigint,
            staging_work_order_count bigint,
            fact_work_order_count bigint,
            failed_task_id text,
            error_type text,
            error_message text,
            updated_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (dag_id, dag_run_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit.pipeline_task_event (
            dag_id text NOT NULL,
            dag_run_id text NOT NULL,
            task_id text NOT NULL,
            event_type text NOT NULL CHECK (event_type IN ('retry', 'failure')),
            try_number integer NOT NULL CHECK (try_number >= 0),
            event_message text,
            event_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (dag_id, dag_run_id, task_id, event_type, try_number)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit.dataset_load_chunks (
            benchmark_run_id text NOT NULL,
            phase text NOT NULL,
            entity text NOT NULL,
            chunk_name text NOT NULL,
            file_sha256 char(64) NOT NULL,
            row_count bigint NOT NULL CHECK (row_count >= 0),
            loaded_at timestamptz NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (benchmark_run_id, phase, entity, chunk_name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit.scale_load_runs (
            benchmark_run_id text NOT NULL,
            phase text NOT NULL,
            manifest_sha256 char(64) NOT NULL,
            status text NOT NULL CHECK (status IN ('loading', 'success', 'failed')),
            requested_work_orders bigint NOT NULL,
            loaded_work_orders bigint NOT NULL DEFAULT 0,
            started_at timestamptz NOT NULL DEFAULT current_timestamp,
            finished_at timestamptz,
            error_message text,
            PRIMARY KEY (benchmark_run_id, phase)
        )
        """
    )

    op.execute(
        "COMMENT ON SCHEMA analytics_source IS "
        "'Versioned read-only compatibility contract over application source tables'"
    )
    op.execute(
        "COMMENT ON COLUMN analytics_source.work_orders.estimated_cost IS "
        "'Unavailable in the target OLTP domain; intentionally NULL'"
    )
    op.execute(
        "COMMENT ON COLUMN analytics_source.work_orders.actual_cost IS "
        "'Unavailable in the target OLTP domain; intentionally NULL'"
    )


def downgrade() -> None:
    """Remove Data Platform-owned objects without touching application rows."""

    op.execute("DROP SCHEMA IF EXISTS audit CASCADE")
    op.execute("DROP SCHEMA IF EXISTS raw CASCADE")
    op.execute("DROP SCHEMA IF EXISTS analytics_source CASCADE")
