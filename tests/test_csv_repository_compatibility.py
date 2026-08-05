"""Compatibility checks for the relocated atomic CSV implementation."""

from src.api import csv_repository as legacy_csv_repository
from src.repositories import csv_writes


def test_legacy_csv_repository_imports_share_the_canonical_implementation() -> None:
    assert legacy_csv_repository.CsvRepositoryError is csv_writes.CsvRepositoryError
    assert legacy_csv_repository.CsvSchemaError is csv_writes.CsvSchemaError
    assert legacy_csv_repository.CsvWriteError is csv_writes.CsvWriteError
    assert legacy_csv_repository.CsvWriteRepository is csv_writes.CsvWriteRepository
    assert legacy_csv_repository.DuplicateRecordError is csv_writes.DuplicateRecordError
    assert legacy_csv_repository.PreparedCsvWrite is csv_writes.PreparedCsvWrite
    assert legacy_csv_repository.RecordNotFoundError is csv_writes.RecordNotFoundError
    assert legacy_csv_repository.commit_csv_writes is csv_writes.commit_csv_writes
