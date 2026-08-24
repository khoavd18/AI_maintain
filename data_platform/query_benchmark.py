"""Repeated Stage 10 analytical queries with PostgreSQL plan evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import time
from typing import Any
from uuid import UUID

from data_platform.config import DataPlatformSettings
from data_platform.database import connect


UTC = timezone.utc
SITE_ID = UUID("00020000-0000-0000-0000-000000000001")
WORK_ORDER_ID = UUID("00050000-0000-0000-0000-000000000001")

QUERIES: dict[str, tuple[str, dict[str, object]]] = {
    "latest_status": (
        """
        SELECT status, transitioned_at
        FROM analytics_warehouse.fact_work_order_status_duration
        WHERE work_order_id = %(work_order_id)s
        ORDER BY sequence_number DESC
        LIMIT 1
        """,
        {"work_order_id": WORK_ORDER_ID},
    ),
    "time_in_status": (
        """
        SELECT status, sum(duration_seconds)::bigint AS duration_seconds
        FROM analytics_warehouse.fact_work_order_status_duration
        WHERE site_id = %(site_id)s
        GROUP BY status
        ORDER BY duration_seconds DESC
        """,
        {"site_id": SITE_ID},
    ),
    "ticket_sla_breaches": (
        """
        SELECT priority, count(*)::bigint AS breach_count
        FROM analytics_warehouse.fact_ticket_sla
        WHERE site_id = %(site_id)s AND is_resolution_breached
        GROUP BY priority ORDER BY breach_count DESC
        """,
        {"site_id": SITE_ID},
    ),
    "escalated_unresolved_tickets": (
        """
        SELECT ticket_id, priority, opened_at
        FROM analytics_warehouse.fact_ticket_sla
        WHERE is_escalated AND resolved_at IS NULL
        ORDER BY opened_at LIMIT 100
        """,
        {},
    ),
    "inventory_balance": (
        """
        SELECT DISTINCT ON (part_id, stock_location_id)
            part_id, stock_location_id, resulting_on_hand_quantity,
            resulting_reserved_quantity
        FROM analytics_warehouse.fact_inventory_movement
        ORDER BY part_id, stock_location_id, occurred_at DESC
        LIMIT 100
        """,
        {},
    ),
    "high_consumption_parts": (
        """
        SELECT part_id, part_number, site_id, net_consumed_quantity
        FROM analytics_marts.inventory_consumption
        ORDER BY net_consumed_quantity DESC, part_id
        LIMIT 100
        """,
        {},
    ),
    "work_order_cost_variance": (
        """
        SELECT work_order_id, site_id, total_estimated_cost,
               total_actual_cost, cost_variance
        FROM analytics_warehouse.fact_work_order_cost
        WHERE cost_variance > 0
        ORDER BY cost_variance DESC LIMIT 100
        """,
        {},
    ),
    "site_reliability": (
        """
        SELECT * FROM analytics_marts.site_reliability
        ORDER BY completion_rate_percent, site_id LIMIT 100
        """,
        {},
    ),
    "combined_work_order_ticket_cost": (
        """
        SELECT
            w.work_order_id,
            w.work_order_number,
            t.ticket_id,
            t.is_resolution_breached,
            c.total_actual_cost,
            c.cost_variance
        FROM analytics_warehouse.fact_work_order w
        JOIN analytics_warehouse.fact_ticket_sla t USING (work_order_id)
        JOIN analytics_warehouse.fact_work_order_cost c USING (work_order_id)
        WHERE w.site_id = %(site_id)s
        ORDER BY c.cost_variance DESC LIMIT 100
        """,
        {"site_id": SITE_ID},
    ),
}


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.999999))]


def benchmark_queries(
    settings: DataPlatformSettings,
    *,
    repeats: int = 5,
) -> dict[str, Any]:
    """Collect warmed client timings and one EXPLAIN ANALYZE plan per query."""

    if not 3 <= repeats <= 20:
        raise ValueError("repeats must be between 3 and 20.")
    results: dict[str, Any] = {}
    with connect(settings.validated(), read_only=True) as connection:
        for name, (statement, parameters) in QUERIES.items():
            connection.execute(statement, parameters).fetchall()
            timings: list[float] = []
            row_count = 0
            for _ in range(repeats):
                started = time.perf_counter()
                rows = connection.execute(statement, parameters).fetchall()
                timings.append((time.perf_counter() - started) * 1_000)
                row_count = len(rows)
            plan_row = connection.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement,
                parameters,
            ).fetchone()
            results[name] = {
                "executions": repeats,
                "result_rows": row_count,
                "latency_ms": {
                    "minimum": round(min(timings), 4),
                    "p50": round(statistics.median(timings), 4),
                    "p95": round(_percentile(timings, 0.95), 4),
                    "maximum": round(max(timings), 4),
                },
                "plan": plan_row[0] if plan_row else None,
            }
        size_rows = connection.execute(
            """
            SELECT
                n.nspname || '.' || c.relname AS relation,
                pg_total_relation_size(c.oid) AS total_bytes,
                pg_relation_size(c.oid) AS table_bytes,
                pg_indexes_size(c.oid) AS index_bytes
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname IN (
                'analytics_compat', 'raw', 'analytics_warehouse', 'analytics_marts'
            ) AND c.relkind IN ('r', 'm')
            ORDER BY total_bytes DESC, relation
            """
        ).fetchall()
        database_size = int(
            connection.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        )
    return {
        "measured_at": datetime.now(UTC).isoformat(),
        "repeats": repeats,
        "queries": results,
        "database_size_bytes": database_size,
        "relations": [
            {
                "relation": row[0],
                "total_bytes": int(row[1]),
                "table_bytes": int(row[2]),
                "index_bytes": int(row[3]),
            }
            for row in size_rows
        ],
        "partitioning": {
            "implemented": False,
            "decision": (
                "Retained ordinary append-oriented tables: bounded incremental scans and "
                "measured indexes meet the laptop benchmark without partition-maintenance cost."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = benchmark_queries(DataPlatformSettings.from_env(), repeats=args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": args.output.as_posix(),
                "database_size_bytes": result["database_size_bytes"],
                "query_count": len(result["queries"]),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
