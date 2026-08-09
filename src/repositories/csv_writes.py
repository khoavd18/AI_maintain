"""Narrow atomic CSV writes for the explicit compatibility repository."""

from __future__ import annotations

import csv
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CsvRepositoryError(RuntimeError):
    """Base error for local CSV repository operations."""


class CsvSchemaError(CsvRepositoryError):
    """Raised when a CSV file does not satisfy its minimum schema."""


class CsvWriteError(CsvRepositoryError):
    """Raised when an atomic file replacement cannot be completed."""


class DuplicateRecordError(CsvRepositoryError):
    """Raised when an identifier already exists."""


class RecordNotFoundError(CsvRepositoryError):
    """Raised when an update target cannot be found."""


@dataclass
class PreparedCsvWrite:
    """Fully validated file content staged for a safe replacement."""

    path: Path
    rows: list[dict[str, str]]
    fieldnames: list[str]
    record: dict[str, str]


class CsvWriteRepository:
    """Append or update one local CSV file through atomic replacement.

    The repository intentionally does not provide cross-process locking. It is
    suitable for the single-user portfolio workflow, not concurrent production use.
    """

    def __init__(
        self,
        path: Path,
        *,
        id_column: str,
        required_columns: set[str],
    ) -> None:
        self.path = path
        self.id_column = id_column
        self.required_columns = required_columns

    def append(self, record: dict[str, Any]) -> dict[str, str]:
        """Append a validated record and reject duplicate identifiers."""

        prepared = self.prepare_append(record)
        commit_csv_writes([prepared])
        return prepared.record

    def prepare_append(self, record: dict[str, Any]) -> PreparedCsvWrite:
        """Validate an append without replacing the target file yet."""

        rows, fieldnames = self._read()
        normalized = _normalize_record(record)
        identifier = normalized.get(self.id_column, "").strip()
        if not identifier:
            raise CsvSchemaError(f"Trường {self.id_column} không được để trống.")
        identifiers = self._identifiers(rows)
        if identifier in identifiers:
            raise DuplicateRecordError(f"{self.id_column} đã tồn tại: {identifier}")

        output_fields = _merge_fieldnames(fieldnames, normalized)
        rows.append(normalized)
        return PreparedCsvWrite(self.path, rows, output_fields, normalized)

    def append_generated(
        self,
        record: dict[str, Any],
        *,
        prefix: str,
        width: int = 6,
    ) -> dict[str, str]:
        """Generate the next canonical identifier and append it in one operation."""

        prepared = self.prepare_append_generated(record, prefix=prefix, width=width)
        commit_csv_writes([prepared])
        return prepared.record

    def prepare_append_generated(
        self,
        record: dict[str, Any],
        *,
        prefix: str,
        width: int = 6,
    ) -> PreparedCsvWrite:
        """Validate a generated-ID append without replacing the file yet."""

        rows, fieldnames = self._read()
        identifiers = self._identifiers(rows)
        identifier = _next_identifier(identifiers, prefix=prefix, width=width)
        normalized = _normalize_record({self.id_column: identifier, **record})
        if identifier in identifiers:
            raise DuplicateRecordError(f"{self.id_column} đã tồn tại: {identifier}")

        output_fields = _merge_fieldnames(fieldnames, normalized)
        rows.append(normalized)
        return PreparedCsvWrite(self.path, rows, output_fields, normalized)

    def update(self, identifier: str, updates: dict[str, Any]) -> dict[str, str]:
        """Update exactly one record without changing its identifier."""

        prepared = self.prepare_update(identifier, updates)
        commit_csv_writes([prepared])
        return prepared.record

    def prepare_update(
        self,
        identifier: str,
        updates: dict[str, Any],
    ) -> PreparedCsvWrite:
        """Validate an update without replacing the target file yet."""

        if self.id_column in updates:
            raise CsvSchemaError(f"Không được thay đổi {self.id_column}.")
        rows, fieldnames = self._read()
        self._identifiers(rows)
        matches = [row for row in rows if row.get(self.id_column, "") == identifier]
        if not matches:
            raise RecordNotFoundError(f"Không tìm thấy {self.id_column}: {identifier}")
        if len(matches) > 1:
            raise CsvSchemaError(f"Dữ liệu có {self.id_column} trùng lặp: {identifier}")

        normalized_updates = _normalize_record(updates)
        matches[0].update(normalized_updates)
        output_fields = _merge_fieldnames(fieldnames, normalized_updates)
        updated = dict(matches[0])
        return PreparedCsvWrite(self.path, rows, output_fields, updated)

    def _read(self) -> tuple[list[dict[str, str]], list[str]]:
        if not self.path.exists():
            raise CsvSchemaError(f"Không tìm thấy nguồn dữ liệu {self.path.name}.")
        try:
            with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = list(reader.fieldnames or [])
                rows = [dict(row) for row in reader]
        except (OSError, csv.Error) as exc:
            raise CsvSchemaError(f"Không thể đọc nguồn dữ liệu {self.path.name}.") from exc

        missing = self.required_columns - set(fieldnames)
        if missing:
            raise CsvSchemaError(f"Nguồn {self.path.name} thiếu cột bắt buộc: {sorted(missing)}")
        return rows, fieldnames

    def _identifiers(self, rows: list[dict[str, str]]) -> set[str]:
        identifiers = [row.get(self.id_column, "").strip() for row in rows]
        if any(not identifier for identifier in identifiers):
            raise CsvSchemaError(f"Nguồn {self.path.name} có {self.id_column} rỗng.")
        if len(set(identifiers)) != len(identifiers):
            raise CsvSchemaError(f"Nguồn {self.path.name} có {self.id_column} trùng lặp.")
        return set(identifiers)


def _normalize_record(record: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in record.items():
        if value is None:
            normalized[key] = ""
        elif isinstance(value, bool):
            normalized[key] = str(value).lower()
        else:
            normalized[key] = str(value)
    return normalized


def _merge_fieldnames(fieldnames: list[str], record: dict[str, str]) -> list[str]:
    return [*fieldnames, *(key for key in record if key not in fieldnames)]


def _next_identifier(identifiers: set[str], *, prefix: str, width: int) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    sequence = [
        int(match.group(1))
        for identifier in identifiers
        if (match := pattern.fullmatch(identifier)) is not None
    ]
    next_number = max(sequence, default=0) + 1
    candidate = f"{prefix}-{next_number:0{width}d}"
    while candidate in identifiers:
        next_number += 1
        candidate = f"{prefix}-{next_number:0{width}d}"
    return candidate


def commit_csv_writes(writes: list[PreparedCsvWrite]) -> None:
    """Replace one or more staged CSVs and roll back handled failures."""

    if not writes:
        return
    paths = [write.path.resolve() for write in writes]
    if len(set(paths)) != len(paths):
        raise CsvSchemaError("Một transaction không được ghi cùng CSV nhiều lần.")

    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for write in writes:
            write.path.parent.mkdir(parents=True, exist_ok=True)
            staged[write.path] = _stage_csv(write)
        for write in writes:
            backups[write.path] = _backup_file(write.path)
        for write in writes:
            os.replace(staged[write.path], write.path)
            replaced.append(write.path)
    except Exception as exc:
        rollback_failed = False
        for path in reversed(replaced):
            try:
                os.replace(backups[path], path)
            except OSError:
                rollback_failed = True
        _remove_paths([*staged.values(), *backups.values()])
        names = ", ".join(write.path.name for write in writes)
        if rollback_failed:
            raise CsvWriteError(
                f"Không thể hoàn tác đầy đủ thao tác ghi {names}; cần kiểm tra CSV nguồn."
            ) from exc
        raise CsvWriteError(
            f"Không thể ghi an toàn {names}; các file gốc không bị thay đổi."
        ) from exc
    else:
        _remove_paths([*staged.values(), *backups.values()])


def _stage_csv(write: PreparedCsvWrite) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{write.path.name}.",
        suffix=".tmp",
        dir=write.path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=write.fieldnames,
                extrasaction="raise",
            )
            writer.writeheader()
            writer.writerows(write.rows)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return temporary_path


def _backup_file(path: Path) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".bak",
        dir=path.parent,
    )
    os.close(descriptor)
    backup_path = Path(temporary_name)
    try:
        shutil.copy2(path, backup_path)
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise
    return backup_path


def _remove_paths(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
