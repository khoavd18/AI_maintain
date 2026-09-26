from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from data_platform.config import DataPlatformSettings
from data_platform.ingestion.domains import raw_loading, reconciliation
from data_platform.ingestion.domains.catalog import DOMAINS


UTC = timezone.utc
BATCH_ID = UUID("30000000-0000-0000-0000-000000000001")


class _Result:
    def __init__(
        self,
        *,
        row: tuple[Any, ...] | None = None,
        rows: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self._row = row
        self._rows = rows or []

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _FinalizationConnection:
    def __init__(self, rows: list[tuple[Any, ...]], events: list[str]) -> None:
        self._rows = rows
        self._events = events

    def execute(
        self,
        statement: str,
        parameters: tuple[object, ...] | None = None,
    ) -> _Result:
        normalized = " ".join(statement.split())
        if normalized.startswith("SELECT domain_name, batch_id, status"):
            self._events.append("lock_all_batches")
            return _Result(rows=self._rows)
        if normalized.startswith("UPDATE audit.domain_extraction_batches"):
            self._events.append(f"complete_batch:{parameters[0]}")
        return _Result()


class _FinalizationFactory:
    def __init__(self, connection: _FinalizationConnection, events: list[str]) -> None:
        self._connection = connection
        self._events = events
        self.calls = 0

    @contextmanager
    def __call__(self, settings: DataPlatformSettings):
        assert settings.database.endswith("_scale")
        self.calls += 1
        self._events.append("transaction_enter")
        try:
            yield self._connection
        except BaseException:
            self._events.append("transaction_rollback")
            raise
        else:
            self._events.append("transaction_commit")


def _empty_domain_rows(*, invalid_domain: str | None = None) -> list[tuple[Any, ...]]:
    now = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    return [
        (
            domain,
            UUID(int=index + 1),
            "extracted" if domain == invalid_domain else "empty",
            0,
            now,
            "",
            None,
            None,
        )
        for index, domain in enumerate(sorted(DOMAINS))
    ]


def test_domain_watermarks_finalize_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    factory = _FinalizationFactory(
        _FinalizationConnection(_empty_domain_rows(), events),
        events,
    )
    monkeypatch.setattr(reconciliation, "connect", factory)

    result = reconciliation.finalize_watermarks("run-finalize", DataPlatformSettings())

    assert factory.calls == 1
    assert result == {
        "run_id": "run-finalize",
        "advanced": {domain: False for domain in sorted(DOMAINS)},
    }
    assert events[0:2] == ["transaction_enter", "lock_all_batches"]
    assert events[-1] == "transaction_commit"
    assert len([event for event in events if event.startswith("complete_batch:")]) == len(
        DOMAINS
    )


def test_domain_watermark_validation_failure_rolls_back_all_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    factory = _FinalizationFactory(
        _FinalizationConnection(
            _empty_domain_rows(invalid_domain="tickets"),
            events,
        ),
        events,
    )
    monkeypatch.setattr(reconciliation, "connect", factory)

    with pytest.raises(RuntimeError, match="not finalizable"):
        reconciliation.finalize_watermarks("run-invalid", DataPlatformSettings())

    assert factory.calls == 1
    assert events[-1] == "transaction_rollback"
    assert "transaction_commit" not in events


class _RawConnection:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def execute(
        self,
        statement: str,
        parameters: tuple[object, ...] | None = None,
    ) -> _Result:
        normalized = " ".join(statement.split())
        if normalized.startswith("UPDATE audit.domain_extraction_batches"):
            self._events.append("batch_audit_update")
        return _Result()


class _RawFactory:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.calls: list[bool] = []

    @contextmanager
    def __call__(self, settings: DataPlatformSettings, *, read_only: bool = False):
        assert settings.database.endswith("_scale")
        self.calls.append(read_only)
        label = "read" if read_only else "write"
        self._events.append(f"{label}_transaction_enter")
        try:
            yield _RawConnection(self._events)
        except BaseException:
            self._events.append(f"{label}_transaction_rollback")
            raise
        else:
            self._events.append(f"{label}_transaction_commit")


def test_raw_rows_and_batch_audit_share_one_write_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    object_path = tmp_path / "tickets.csv"
    object_path.write_text("header\nrow\n", encoding="utf-8")
    events: list[str] = []
    factory = _RawFactory(events)
    batch = {
        "batch_id": BATCH_ID,
        "row_count": 3,
        "object_path": str(object_path),
        "object_sha256": "expected",
        "error_message": None,
    }
    monkeypatch.setattr(raw_loading, "connect", factory)
    monkeypatch.setattr(raw_loading, "existing_batch", lambda *_args: batch)
    monkeypatch.setattr(raw_loading, "checksum", lambda _path: "expected")

    def _copy(*_args: object) -> int:
        events.append("raw_copy_and_insert")
        return 3

    monkeypatch.setattr(raw_loading, "copy_raw_object", _copy)

    result = raw_loading.load_raw_domain(
        "run-load",
        "tickets",
        settings=DataPlatformSettings(),
    )

    assert factory.calls == [True, False]
    assert result["status"] == "raw_loaded"
    assert events.index("write_transaction_enter") < events.index("raw_copy_and_insert")
    assert events.index("raw_copy_and_insert") < events.index("batch_audit_update")
    assert events.index("batch_audit_update") < events.index("write_transaction_commit")
