from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from data_platform.generator import generate_scale_dataset
from data_platform.object_store import checksum


SEED = 20260823


def _file_checksums(manifest: dict[str, object]) -> dict[str, str]:
    entries = manifest["files"]
    assert isinstance(entries, list)
    return {
        str(entry["name"]): str(entry["sha256"]) for entry in entries if isinstance(entry, dict)
    }


def _work_order_rows(manifest: dict[str, object]) -> list[dict[str, str]]:
    entries = manifest["files"]
    assert isinstance(entries, list)
    rows: list[dict[str, str]] = []
    for entry in entries:
        assert isinstance(entry, dict)
        if entry.get("entity") != "work_orders":
            continue
        with Path(str(entry["path"])).open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def _entity_rows(manifest: dict[str, object], entity: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for entry in manifest["files"]:
        if entry.get("entity") != entity:
            continue
        with Path(str(entry["path"])).open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def test_small_dataset_is_deterministic_restartable_and_checksum_verified(
    tmp_path: Path,
) -> None:
    first = generate_scale_dataset(
        work_order_count=256,
        seed=SEED,
        run_id="deterministic-a",
        output_root=tmp_path,
        batch_size=1_000,
    )
    second_run = generate_scale_dataset(
        work_order_count=256,
        seed=SEED,
        run_id="deterministic-b",
        output_root=tmp_path,
        batch_size=1_000,
    )
    manifest_path = tmp_path / "deterministic-a" / "baseline" / "manifest.json"
    manifest_mtime = manifest_path.stat().st_mtime_ns

    restarted = generate_scale_dataset(
        work_order_count=256,
        seed=SEED,
        run_id="deterministic-a",
        output_root=tmp_path,
        batch_size=1_000,
    )

    assert restarted == first
    assert manifest_path.stat().st_mtime_ns == manifest_mtime
    assert _file_checksums(first) == _file_checksums(second_run)
    assert first["actual_work_orders"] == 256
    assert first["file_count"] == len(first["files"])
    for entry in first["files"]:
        path = Path(str(entry["path"]))
        assert checksum(path) == entry["sha256"]
        assert path.stat().st_size == entry["size_bytes"]


def test_small_dataset_contains_watermark_and_lifecycle_edge_cases(tmp_path: Path) -> None:
    manifest = generate_scale_dataset(
        work_order_count=256,
        seed=SEED,
        run_id="edge-cases",
        output_root=tmp_path,
        batch_size=1_000,
    )
    rows = _work_order_rows(manifest)

    assert len(rows) == 256
    assert len({row["id"] for row in rows}) == 256
    updated_counts = Counter(row["updated_at"] for row in rows)
    assert max(updated_counts.values()) > 1
    assert any(not row["assigned_to_user_id"] for row in rows)
    assert any(row["status"] == "cancelled" for row in rows)
    assert any(row["status"] in {"planned", "assigned", "in_progress", "on_hold"} for row in rows)

    for row in rows:
        created_at = datetime.fromisoformat(row["created_at"])
        updated_at = datetime.fromisoformat(row["updated_at"])
        assert created_at <= updated_at
        if row["started_at"]:
            started_at = datetime.fromisoformat(row["started_at"])
            assert created_at <= started_at
        if row["completed_at"]:
            completed_at = datetime.fromisoformat(row["completed_at"])
            assert row["started_at"]
            assert datetime.fromisoformat(row["started_at"]) <= completed_at
            assert row["status"] in {"completed", "verified"}


def test_restart_rejects_a_changed_generated_file(tmp_path: Path) -> None:
    manifest = generate_scale_dataset(
        work_order_count=8,
        seed=SEED,
        run_id="tamper-check",
        output_root=tmp_path,
        batch_size=1_000,
    )
    first_file = Path(str(manifest["files"][0]["path"]))
    first_file.write_text("changed after generation\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing or changed"):
        generate_scale_dataset(
            work_order_count=8,
            seed=SEED,
            run_id="tamper-check",
            output_root=tmp_path,
            batch_size=1_000,
        )


def test_zero_and_negative_counts_have_explicit_behavior(tmp_path: Path) -> None:
    manifest = generate_scale_dataset(
        work_order_count=0,
        seed=SEED,
        run_id="empty-baseline",
        output_root=tmp_path,
        batch_size=1_000,
    )

    assert manifest["actual_work_orders"] == 0
    assert not [entry for entry in manifest["files"] if entry["entity"] == "work_orders"]

    with pytest.raises(ValueError, match="non-negative"):
        generate_scale_dataset(
            work_order_count=-1,
            seed=SEED,
            run_id="invalid",
            output_root=tmp_path,
            batch_size=1_000,
        )


def test_incremental_new_and_update_rows_follow_baseline_watermark(tmp_path: Path) -> None:
    baseline = generate_scale_dataset(
        work_order_count=1_000,
        seed=SEED,
        run_id="incremental-contract",
        output_root=tmp_path,
        batch_size=1_000,
    )
    incremental = generate_scale_dataset(
        work_order_count=100,
        seed=SEED,
        run_id="incremental-contract",
        output_root=tmp_path,
        phase="incremental",
        batch_size=1_000,
        baseline_count=1_000,
        update_count=10,
    )

    baseline_rows = _work_order_rows(baseline)
    new_rows = _work_order_rows(incremental)
    update_rows = _entity_rows(incremental, "work_order_updates")
    baseline_ids = {row["id"] for row in baseline_rows}
    baseline_watermark = max(datetime.fromisoformat(row["updated_at"]) for row in baseline_rows)

    assert len(new_rows) == 100
    assert len(update_rows) == 10
    assert not ({row["id"] for row in new_rows} & baseline_ids)
    assert {row["id"] for row in update_rows} <= baseline_ids
    assert all(datetime.fromisoformat(row["updated_at"]) > baseline_watermark for row in new_rows)
    assert all(
        datetime.fromisoformat(row["updated_at"]) > baseline_watermark for row in update_rows
    )
    assert max(datetime.fromisoformat(row["updated_at"]) for row in update_rows) <= (
        datetime.now(timezone.utc) + timedelta(minutes=1)
    )

    restarted = generate_scale_dataset(
        work_order_count=100,
        seed=SEED,
        run_id="incremental-contract",
        output_root=tmp_path,
        phase="incremental",
        batch_size=1_000,
        baseline_count=1_000,
        update_count=10,
    )
    assert _file_checksums(restarted) == _file_checksums(incremental)
