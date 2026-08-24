from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from data_platform import pipeline
from data_platform.config import DataPlatformSettings
from data_platform.object_store import checksum


UTC = timezone.utc
BATCH_ID = UUID("20000000-0000-0000-0000-000000000001")
UPPER_ID = UUID("20000000-0000-0000-0000-000000000099")
UPPER_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


class _Result:
    def __init__(self, row: tuple[Any, ...] | None = None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _Copy:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def __enter__(self) -> _Copy:
        self._events.append("copy_enter")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._events.append("copy_exit")

    def write(self, block: bytes) -> None:
        assert isinstance(block, bytes)


class _CopyCursor:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def copy(self, statement: str) -> _Copy:
        assert statement.startswith("COPY stage9_raw_work_orders")
        return _Copy(self._events)


class _LoadConnection:
    def __init__(
        self,
        *,
        batch: tuple[Any, ...],
        copied_count: int,
        events: list[str],
        fail_on_audit_update: bool = False,
    ) -> None:
        self._batch = batch
        self._copied_count = copied_count
        self._events = events
        self._fail_on_audit_update = fail_on_audit_update
        self.statements: list[str] = []

    def execute(
        self,
        statement: str,
        parameters: tuple[object, ...] | None = None,
    ) -> _Result:
        normalized = " ".join(statement.split())
        self.statements.append(normalized)
        if "SELECT batch_id, status, row_count" in normalized:
            return _Result(self._batch)
        if normalized == "SELECT count(*) FROM stage9_raw_work_orders":
            return _Result((self._copied_count,))
        if normalized.startswith("INSERT INTO raw.work_orders"):
            self._events.append("raw_insert")
        if normalized.startswith("INSERT INTO audit.pipeline_watermarks"):
            self._events.append("watermark_upsert")
        if normalized.startswith("SELECT updated_at, work_order_id") and "FOR UPDATE" in normalized:
            return _Result((pipeline.EPOCH, pipeline.ZERO_UUID))
        if normalized.startswith("UPDATE audit.pipeline_watermarks"):
            self._events.append("watermark_update")
        if normalized.startswith("UPDATE audit.extraction_batches"):
            self._events.append("audit_update")
            if self._fail_on_audit_update:
                raise RuntimeError("simulated downstream audit failure")
        return _Result()

    def cursor(self) -> _CopyCursor:
        return _CopyCursor(self._events)


class _LoadConnectionFactory:
    def __init__(self, connection: _LoadConnection, events: list[str]) -> None:
        self.connection = connection
        self.events = events

    @contextmanager
    def __call__(self, settings: DataPlatformSettings):
        assert settings.database.endswith("_scale")
        self.events.append("transaction_enter")
        try:
            yield self.connection
        except BaseException:
            self.events.append("transaction_rollback")
            raise
        else:
            self.events.append("transaction_commit")


class _WatermarkConnection:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self.row = row
        self.parameters: tuple[object, ...] | None = None

    def execute(self, statement: str, parameters: tuple[object, ...]) -> _Result:
        assert "audit.pipeline_watermarks" in statement
        self.parameters = parameters
        return _Result(self.row)


def _batch(path: Path, *, row_count: int) -> tuple[Any, ...]:
    return (
        BATCH_ID,
        "extracted",
        row_count,
        str(path),
        str(path),
        checksum(path),
        UPPER_TIME if row_count else None,
        UPPER_ID if row_count else None,
    )


def test_incremental_query_uses_strict_tuple_watermark_and_stable_order() -> None:
    normalized = " ".join(pipeline._EXTRACT_QUERY.split())

    assert "WHERE (updated_at, work_order_id) > (%s::timestamptz, %s::uuid)" in normalized
    assert "ORDER BY updated_at, work_order_id" in normalized


def test_missing_and_existing_watermarks_preserve_both_tuple_components() -> None:
    missing = _WatermarkConnection(None)
    assert pipeline._watermark(missing) == (pipeline.EPOCH, pipeline.ZERO_UUID)
    assert missing.parameters == (pipeline.PIPELINE_NAME,)

    existing = _WatermarkConnection((UPPER_TIME, UPPER_ID))
    assert pipeline._watermark(existing) == (UPPER_TIME, UPPER_ID)


def test_audit_message_sanitization_redacts_credentials_and_bounds_length() -> None:
    secret = "do-not-leak"
    message = (
        "  failed\n password=do-not-leak; "
        "postgresql+psycopg://scale_user:do-not-leak@localhost:25432/db  " + "x" * 2_000
    )

    sanitized = pipeline._sanitize(message, limit=180)

    assert "\n" not in sanitized
    assert secret not in sanitized
    assert "password=<redacted>" in sanitized
    assert ":<redacted>@" in sanitized
    assert len(sanitized) <= 180


def test_raw_load_and_watermark_are_ordered_in_one_successful_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "batch.csv"
    path.write_bytes(b"header\nrow\n")
    events: list[str] = []
    connection = _LoadConnection(batch=_batch(path, row_count=1), copied_count=1, events=events)
    factory = _LoadConnectionFactory(connection, events)
    monkeypatch.setattr(pipeline, "connect", factory)

    result = pipeline.load_raw_batch("run-1", DataPlatformSettings())

    assert result["status"] == "loaded"
    assert events.index("raw_insert") < events.index("watermark_upsert")
    assert events.index("watermark_upsert") < events.index("audit_update")
    assert events.index("audit_update") < events.index("transaction_commit")
    assert "transaction_rollback" not in events


def test_downstream_failure_rolls_back_the_transaction_that_touched_watermark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "batch.csv"
    path.write_bytes(b"header\nrow\n")
    events: list[str] = []
    connection = _LoadConnection(
        batch=_batch(path, row_count=1),
        copied_count=1,
        events=events,
        fail_on_audit_update=True,
    )
    factory = _LoadConnectionFactory(connection, events)
    monkeypatch.setattr(pipeline, "connect", factory)

    with pytest.raises(RuntimeError, match="downstream audit failure"):
        pipeline.load_raw_batch("run-rollback", DataPlatformSettings())

    assert "watermark_upsert" in events
    assert "transaction_rollback" in events
    assert "transaction_commit" not in events


def test_empty_batch_does_not_advance_the_watermark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "empty.csv"
    path.write_bytes(b"header\n")
    events: list[str] = []
    connection = _LoadConnection(batch=_batch(path, row_count=0), copied_count=0, events=events)
    factory = _LoadConnectionFactory(connection, events)
    monkeypatch.setattr(pipeline, "connect", factory)

    result = pipeline.load_raw_batch("run-empty", DataPlatformSettings())

    assert result["status"] == "empty"
    assert "watermark_upsert" not in events
    assert events[-1] == "transaction_commit"
