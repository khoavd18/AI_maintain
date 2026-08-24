"""Stage 10 multi-domain ingestion with atomic watermark finalization."""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

from data_platform.domain_pipeline import DOMAINS
from data_platform.orchestration.airflow_callbacks import (
    record_domain_pipeline_failure,
    record_domain_task_retry,
)


PROJECT_ROOT = "/opt/maintenance-platform"
DBT_PROJECT_DIR = f"{PROJECT_ROOT}/data_platform/dbt/maintenance_analytics"
DBT_PROFILES_DIR = f"{PROJECT_ROOT}/data_platform/dbt/profiles"
RUN_ENV = {
    "STAGE10_RUN_ID": "{{ run_id }}",
    "STAGE10_PHASE": "{{ dag_run.conf.get('phase', 'incremental') }}",
    "STAGE10_FAULT_DOMAIN": "{{ dag_run.conf.get('fault_domain', '') }}",
}


def domain_command(command: str, *, domain: str | None = None) -> str:
    """Build a metadata-only command; row payloads never enter XCom."""

    arguments = [
        "python -m data_platform.domain_pipeline",
        command,
        '--run-id "$STAGE10_RUN_ID"',
    ]
    if command in {"start", "extract"}:
        arguments.append('--phase "$STAGE10_PHASE"')
    if domain:
        arguments.append(f"--domain {domain}")
    if command in {"start", "load-raw"}:
        arguments.append('--fault-domain "$STAGE10_FAULT_DOMAIN"')
    return " ".join(arguments)


with DAG(
    dag_id="maintenance_domain_scale_pipeline",
    description="Stage 10 domain extraction, dbt, reconciliation, and atomic watermarks.",
    schedule=None,
    start_date=pendulum.datetime(2026, 8, 24, tz="Asia/Ho_Chi_Minh"),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=2,
    dagrun_timeout=timedelta(hours=12),
    on_failure_callback=record_domain_pipeline_failure,
    default_args={
        "owner": "data_engineering",
        "retries": 1,
        "retry_delay": timedelta(seconds=30),
        "email_on_failure": False,
        "email_on_retry": False,
        "on_retry_callback": record_domain_task_retry,
    },
    tags=["maintenance", "stage10", "domain-scale", "postgres", "dbt"],
) as dag:
    start = BashOperator(
        task_id="start_domain_pipeline_audit",
        bash_command=domain_command("start"),
        env=RUN_ENV,
        append_env=True,
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(minutes=5),
    )
    check_source = BashOperator(
        task_id="check_source_database",
        bash_command="python -m data_platform.pipeline check-source",
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(minutes=5),
    )

    raw_loads = []
    for domain in DOMAINS:
        extract = BashOperator(
            task_id=f"extract_{domain}",
            bash_command=domain_command("extract", domain=domain),
            env=RUN_ENV,
            append_env=True,
            cwd=PROJECT_ROOT,
            do_xcom_push=False,
            execution_timeout=timedelta(hours=2),
        )
        load = BashOperator(
            task_id=f"load_raw_{domain}",
            bash_command=domain_command("load-raw", domain=domain),
            env=RUN_ENV,
            append_env=True,
            cwd=PROJECT_ROOT,
            do_xcom_push=False,
            execution_timeout=timedelta(hours=2),
        )
        start >> check_source >> extract >> load
        raw_loads.append(load)

    dbt_run = BashOperator(
        task_id="dbt_run_domain_models",
        bash_command=(
            f"dbt run --project-dir {DBT_PROJECT_DIR} "
            f"--profiles-dir {DBT_PROFILES_DIR} --target scale --no-partial-parse"
        ),
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(hours=4),
    )
    dbt_test = BashOperator(
        task_id="dbt_test_domain_models",
        bash_command=(
            f"dbt test --project-dir {DBT_PROJECT_DIR} "
            f"--profiles-dir {DBT_PROFILES_DIR} --target scale --no-partial-parse"
        ),
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(hours=2),
    )
    reconcile = BashOperator(
        task_id="reconcile_domain_layers",
        bash_command=domain_command("reconcile"),
        env=RUN_ENV,
        append_env=True,
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(minutes=30),
    )
    finalize = BashOperator(
        task_id="finalize_domain_watermarks",
        bash_command=domain_command("finalize"),
        env=RUN_ENV,
        append_env=True,
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(minutes=10),
    )
    complete = BashOperator(
        task_id="complete_domain_pipeline_audit",
        bash_command=domain_command("complete"),
        env=RUN_ENV,
        append_env=True,
        cwd=PROJECT_ROOT,
        do_xcom_push=False,
        execution_timeout=timedelta(minutes=5),
    )

    raw_loads >> dbt_run >> dbt_test >> reconcile >> finalize >> complete
