"""Read-only capacity gate for the isolated Stage 9 benchmark."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any


GIB = 1024**3


def _host_available_memory() -> int | None:
    if os.name == "nt":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.available_physical)
        return None
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    return None


def _docker_memory_limit() -> int | None:
    completed = subprocess.run(
        ["docker", "info", "--format", "{{.MemTotal}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode or not completed.stdout.strip().isdigit():
        return None
    return int(completed.stdout.strip())


def projected_footprint(work_order_count: int) -> dict[str, int]:
    """Conservative projection based on the verified 100,004-row reference DB."""

    scale = work_order_count / 1_100_000
    logical_database = math.ceil(2.675 * GIB * scale)
    steady_database = math.ceil(12 * GIB * scale)
    generated_csv = math.ceil(4 * GIB * scale)
    wal_and_temp = math.ceil(8 * GIB * scale)
    image_and_build = 8 * GIB
    c_peak = steady_database + wal_and_temp + image_and_build + 5 * GIB
    d_peak = generated_csv + 5 * GIB
    return {
        "reference_linear_database_floor_bytes": logical_database,
        "steady_database_budget_bytes": steady_database,
        "generated_csv_budget_bytes": generated_csv,
        "wal_and_temp_budget_bytes": wal_and_temp,
        "image_and_build_budget_bytes": image_and_build,
        "required_c_free_bytes": c_peak,
        "required_d_free_bytes": d_peak,
    }


def run_preflight(work_order_count: int) -> dict[str, Any]:
    if work_order_count < 1:
        raise ValueError("Projected work-order count must be positive.")
    footprint = projected_footprint(work_order_count)
    c_usage = shutil.disk_usage(Path("C:/"))
    d_usage = shutil.disk_usage(Path("D:/"))
    host_available = _host_available_memory()
    docker_limit = _docker_memory_limit()
    checks = {
        "c_disk_margin": c_usage.free >= footprint["required_c_free_bytes"],
        "d_disk_margin": d_usage.free >= footprint["required_d_free_bytes"],
        # The generator is streaming and stayed below a small bounded working
        # set in characterization; Docker capacity is gated independently.
        "host_streaming_memory": host_available is None or host_available >= GIB,
        "docker_memory_limit": docker_limit is not None and docker_limit >= 6 * GIB,
    }
    result = {
        "projected_work_orders": work_order_count,
        "footprint": footprint,
        "actual": {
            "c_free_bytes": c_usage.free,
            "d_free_bytes": d_usage.free,
            "host_available_memory_bytes": host_available,
            "docker_memory_limit_bytes": docker_limit,
        },
        "checks": checks,
        "safe_to_proceed": all(checks.values()),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-order-count", type=int, default=1_100_000)
    args = parser.parse_args()
    result = run_preflight(args.work_order_count)
    print(json.dumps(result, sort_keys=True))
    if not result["safe_to_proceed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
