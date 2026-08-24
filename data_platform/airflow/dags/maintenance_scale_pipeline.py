"""Unified, retry-safe maintenance analytics pipeline for the scale runtime."""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

from data_platform.orchestration.airflow_callbacks import (
    record_pipeline_failure,
    record_task_retry,
)


PROJECT_ROOT = "/opt/maintenance-platform"
DBT_PROJECT_DIR = f"{PROJECT_ROOT}/data_platform/dbt/maintenance_analytics"
DBT_PROFILES_DIR = f"{PROJECT_ROOT}/data_platform/dbt/profiles"
RUN_ENV = {"DATA_PLATFORM_RUN_ID": "{{ run_id }}"}


def pipeline_command(command: str, *arguments: str) -> str:
    """Build a shell command that passes only the templated run identifier."""

    suffix = " ".join(arguments)
    return (
        "python -m data_platform.pipeline "
        f'{command} --run-id "$DATA_PLATFORM_RUN_ID"'
        f"{(' ' + suffix) if suffix else ''}"
    )


with DAG(
    dag_id="maintenance_scale_pipeline",
    description="Extract, transform, test, reconcile, and audit maintenance scale data.",
    schedule=None,
    start_date=pendulum.datetime(2026, 8, 24, tz="Asia/Ho_Chi_Minh"),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    dagrun_timeout=timedelta(hours=8),
    on_failure_callback=record_pipeline_failure,
    default_args={
        "owner": "data_engineering",
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=10),
        "email_on_failure": False,
        "email_on_retry": False,
        "on_retry_callback": record_task_retry,
    },
    tags=["maintenance", "scale", "postgres", "dbt", "audit"],
) as dag:
    start_pipeline_audit = BashOperator(
        task_id="start_pipeline_audit",
        bash_command=pipeline_command("audit-start"),
        env=RUN_ENV,
        append_env=True,
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(minutes=5),
    )

    check_source_database = BashOperator(
        task_id="check_source_database",
        bash_command="python -m data_platform.pipeline check-source",
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(minutes=5),
    )

    snapshot_dimensions = BashOperator(
        task_id="snapshot_dimensions",
        bash_command=pipeline_command("snapshot-dimensions"),
        env=RUN_ENV,
        append_env=True,
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(minutes=30),
    )

    extract_work_orders = BashOperator(
        task_id="extract_work_orders_incremental",
        bash_command=pipeline_command("extract"),
        env=RUN_ENV,
        append_env=True,
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(minutes=90),
    )

    load_work_orders_raw = BashOperator(
        task_id="load_work_orders_raw",
        bash_command=pipeline_command("load-raw"),
        env=RUN_ENV,
        append_env=True,
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(minutes=90),
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=(
            f"dbt run --project-dir {DBT_PROJECT_DIR} "
            f"--profiles-dir {DBT_PROFILES_DIR} --target scale --no-partial-parse"
        ),
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(hours=2),
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            f"dbt test --project-dir {DBT_PROJECT_DIR} "
            f"--profiles-dir {DBT_PROFILES_DIR} --target scale --no-partial-parse"
        ),
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(hours=1),
    )

    reconcile = BashOperator(
        task_id="reconcile",
        bash_command=pipeline_command("reconcile"),
        env=RUN_ENV,
        append_env=True,
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(minutes=30),
    )

    complete_pipeline_audit = BashOperator(
        task_id="complete_pipeline_audit",
        bash_command=pipeline_command("audit-complete"),
        env=RUN_ENV,
        append_env=True,
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(minutes=5),
    )

    (
        start_pipeline_audit
        >> check_source_database
        >> snapshot_dimensions
        >> extract_work_orders
        >> load_work_orders_raw
        >> dbt_run
        >> dbt_test
        >> reconcile
        >> complete_pipeline_audit
    )
