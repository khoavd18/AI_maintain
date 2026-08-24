"""Measured Stage 9 query, relation-size, and resource benchmark harness."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import time
from typing import Any

from data_platform.config import DataPlatformSettings
from data_platform.database import connect


UTC = timezone.utc


@dataclass(frozen=True, slots=True)
class QueryCase:
    name: str
    sql: str
    parameters: tuple[object, ...] = ()


QUERY_CASES = (
    QueryCase(
        "work_orders_by_site_date",
        """
        SELECT site_id, date_trunc('month', created_at) AS month_start, count(*) AS rows
        FROM analytics_warehouse.fact_work_order
        WHERE site_id = (
            SELECT site_id FROM analytics_warehouse.fact_work_order
            WHERE site_id IS NOT NULL LIMIT 1
        )
          AND created_at >= %s::timestamptz
          AND created_at < %s::timestamptz
        GROUP BY site_id, date_trunc('month', created_at)
        ORDER BY month_start
        """,
        ("2024-01-01T00:00:00+00:00", "2026-08-23T00:00:00+00:00"),
    ),
    QueryCase(
        "latest_status_per_work_order",
        """
        SELECT DISTINCT ON (work_order_id)
               work_order_id, status, source_updated_at
        FROM raw.work_orders
        ORDER BY work_order_id, source_updated_at DESC
        LIMIT 1000
        """,
    ),
    QueryCase(
        "critical_open_work_orders",
        """
        SELECT work_order_id, work_order_number, site_id, asset_id, status, due_date
        FROM analytics_warehouse.fact_work_order
        WHERE priority = 'critical'
          AND status IN ('planned', 'assigned', 'in_progress', 'on_hold')
        ORDER BY due_date, work_order_id
        LIMIT 100
        """,
    ),
    QueryCase(
        "technician_workload",
        """
        SELECT assigned_technician_id,
               count(*) FILTER (
                   WHERE status IN ('assigned', 'in_progress', 'on_hold')
               ) AS active_work_orders,
               count(*) AS total_work_orders
        FROM analytics_warehouse.fact_work_order
        WHERE assigned_technician_id IS NOT NULL
        GROUP BY assigned_technician_id
        ORDER BY active_work_orders DESC, assigned_technician_id
        LIMIT 100
        """,
    ),
    QueryCase(
        "monthly_completion_rate",
        """
        SELECT site_id, month_start_date, total_work_orders,
               completed_work_orders, completion_rate_percent
        FROM analytics_marts.monthly_site_work_orders
        WHERE total_work_orders > 0
        ORDER BY month_start_date DESC, site_id
        LIMIT 240
        """,
    ),
    QueryCase(
        "cost_variance_availability",
        """
        SELECT count(*) AS total_work_orders,
               count(*) FILTER (
                   WHERE estimated_cost IS NOT NULL AND actual_cost IS NOT NULL
               ) AS cost_comparable_work_orders,
               sum(cost_variance) AS total_cost_variance
        FROM analytics_warehouse.fact_work_order
        """,
    ),
    QueryCase(
        "asset_failure_frequency",
        """
        SELECT asset_id, count(*) AS failure_related_work_orders,
               count(*) FILTER (WHERE priority = 'critical') AS critical_work_orders
        FROM analytics_warehouse.fact_work_order
        WHERE work_order_type IN ('corrective', 'emergency')
        GROUP BY asset_id
        ORDER BY failure_related_work_orders DESC, asset_id
        LIMIT 100
        """,
    ),
    QueryCase(
        "daily_mart",
        """
        SELECT site_id, created_date, total_work_orders, completed_work_orders,
               critical_work_orders, completion_rate_percent
        FROM analytics_marts.daily_site_work_orders
        WHERE created_date >= %s::date AND total_work_orders > 0
        ORDER BY created_date DESC, site_id
        LIMIT 500
        """,
        ("2026-01-01",),
    ),
    QueryCase(
        "monthly_mart",
        """
        SELECT month_start_date, sum(total_work_orders) AS total_work_orders,
               sum(completed_work_orders) AS completed_work_orders
        FROM analytics_marts.monthly_site_work_orders
        GROUP BY month_start_date
        ORDER BY month_start_date DESC
        LIMIT 60
        """,
    ),
    QueryCase(
        "incremental_watermark_query",
        """
        SELECT id, updated_at
        FROM public.work_orders
        WHERE (updated_at, id) > (%s::timestamptz, %s::uuid)
        ORDER BY updated_at, id
        LIMIT 50000
        """,
        ("2026-08-01T00:00:00+00:00", "00000000-0000-0000-0000-000000000000"),
    ),
)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _plan_nodes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def visit(node: dict[str, Any]) -> None:
        nodes.append(
            {
                "node_type": node.get("Node Type"),
                "relation_name": node.get("Relation Name"),
                "index_name": node.get("Index Name"),
                "actual_rows": node.get("Actual Rows"),
                "actual_loops": node.get("Actual Loops"),
                "rows_removed_by_filter": node.get("Rows Removed by Filter", 0),
                "shared_hit_blocks": node.get("Shared Hit Blocks", 0),
                "shared_read_blocks": node.get("Shared Read Blocks", 0),
                "temp_read_blocks": node.get("Temp Read Blocks", 0),
                "temp_written_blocks": node.get("Temp Written Blocks", 0),
            }
        )
        for child in node.get("Plans", []):
            visit(child)

    visit(plan)
    return nodes


def benchmark_queries(
    settings: DataPlatformSettings | None = None,
    *,
    executions: int = 5,
    warmups: int = 1,
    only: set[str] | None = None,
    label: str = "final",
) -> dict[str, Any]:
    """Measure closed queries repeatedly and retain EXPLAIN/BUFFERS evidence."""

    if executions < 3:
        raise ValueError("At least three executions are required for p50/p95 evidence.")
    resolved = settings or DataPlatformSettings.from_env()
    results: list[dict[str, Any]] = []
    cases = [case for case in QUERY_CASES if not only or case.name in only]
    with connect(resolved, read_only=True) as connection:
        for case in cases:
            for _ in range(warmups):
                connection.execute(case.sql, case.parameters).fetchall()
            durations: list[float] = []
            returned_rows = 0
            for _ in range(executions):
                started = time.perf_counter_ns()
                rows = connection.execute(case.sql, case.parameters).fetchall()
                durations.append((time.perf_counter_ns() - started) / 1_000_000)
                returned_rows = len(rows)
            explain_row = connection.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + case.sql,
                case.parameters,
            ).fetchone()
            if explain_row is None:
                raise RuntimeError(f"EXPLAIN returned no plan for {case.name}.")
            explain_payload = explain_row[0]
            if isinstance(explain_payload, str):
                explain_payload = json.loads(explain_payload)
            top = explain_payload[0]
            results.append(
                {
                    "name": case.name,
                    "executions": executions,
                    "warmups": warmups,
                    "returned_rows": returned_rows,
                    "durations_ms": [round(value, 6) for value in durations],
                    "p50_ms": round(statistics.median(durations), 6),
                    "p95_ms": round(_percentile(durations, 0.95), 6),
                    "min_ms": round(min(durations), 6),
                    "max_ms": round(max(durations), 6),
                    "planning_time_ms": top.get("Planning Time"),
                    "explain_execution_time_ms": top.get("Execution Time"),
                    "plan_nodes": _plan_nodes(top["Plan"]),
                    "explain": explain_payload,
                }
            )
    return {"label": label, "measured_at": datetime.now(UTC).isoformat(), "queries": results}


def collect_database_evidence(
    settings: DataPlatformSettings | None = None,
) -> dict[str, Any]:
    resolved = settings or DataPlatformSettings.from_env()
    with connect(resolved, read_only=True) as connection:
        database_size = int(
            connection.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        )
        relations = [
            {
                "relation": row[0],
                "table_bytes": int(row[1]),
                "index_bytes": int(row[2]),
                "total_bytes": int(row[3]),
                "estimated_rows": int(row[4]),
            }
            for row in connection.execute(
                """
                SELECT c.oid::regclass::text,
                       pg_relation_size(c.oid),
                       pg_indexes_size(c.oid),
                       pg_total_relation_size(c.oid),
                       greatest(c.reltuples, 0)::bigint
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind IN ('r', 'm')
                  AND n.nspname IN (
                      'public', 'raw', 'audit', 'analytics_staging',
                      'analytics_warehouse', 'analytics_marts'
                  )
                ORDER BY pg_total_relation_size(c.oid) DESC
                """
            ).fetchall()
        ]
        counts = {
            row[0]: int(row[1])
            for row in connection.execute(
                """
                SELECT layer, row_count FROM (
                    SELECT 'source_work_orders' AS layer, count(*)::bigint AS row_count
                    FROM analytics_source.work_orders
                    UNION ALL SELECT 'raw_versions', count(*) FROM raw.work_orders
                    UNION ALL SELECT 'raw_unique', count(DISTINCT work_order_id) FROM raw.work_orders
                    UNION ALL SELECT 'staging', count(*) FROM analytics_staging.stg_work_orders
                    UNION ALL SELECT 'fact', count(*) FROM analytics_warehouse.fact_work_order
                    UNION ALL SELECT 'daily_mart', count(*) FROM analytics_marts.daily_site_work_orders
                    UNION ALL SELECT 'monthly_mart', count(*) FROM analytics_marts.monthly_site_work_orders
                    UNION ALL SELECT 'maintenance_logs', count(*) FROM public.maintenance_logs
                ) AS layer_counts
                """
            ).fetchall()
        }
    return {"database_size_bytes": database_size, "layer_counts": counts, "relations": relations}


def collect_resource_evidence() -> dict[str, Any]:
    """Collect bounded local resource data without deleting or mutating anything."""

    disks = {}
    for drive in (Path("C:/"), Path("D:/")):
        if drive.exists():
            usage = shutil.disk_usage(drive)
            disks[str(drive)] = {
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
            }
    docker: dict[str, Any] = {}
    for key, command in {
        "system_df": ["docker", "system", "df", "--format", "{{json .}}"],
        "stats": [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
        ],
    }.items():
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        docker[key] = {
            "exit_code": completed.returncode,
            "lines": [
                json.loads(line)
                for line in completed.stdout.splitlines()
                if line.strip().startswith("{")
            ],
        }
    return {"captured_at": datetime.now(UTC).isoformat(), "disks": disks, "docker": docker}


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    query_parser = subparsers.add_parser("queries")
    query_parser.add_argument("--output", type=Path, required=True)
    query_parser.add_argument("--label", default="final")
    query_parser.add_argument("--executions", type=int, default=5)
    query_parser.add_argument("--only", action="append")
    evidence_parser = subparsers.add_parser("evidence")
    evidence_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "queries":
        payload = benchmark_queries(
            executions=args.executions,
            only=set(args.only) if args.only else None,
            label=args.label,
        )
    else:
        payload = {
            "database": collect_database_evidence(),
            "resources": collect_resource_evidence(),
        }
    write_report(args.output, payload)
    print(json.dumps({"output": str(args.output), "status": "written"}, sort_keys=True))


if __name__ == "__main__":
    main()
