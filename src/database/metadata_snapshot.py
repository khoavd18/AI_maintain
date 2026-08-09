"""Deterministic SQLAlchemy metadata snapshots for refactor equivalence checks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import Enum as SqlEnum
from sqlalchemy.schema import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from src.database import models  # noqa: F401  # register every mapped class
from src.database.session import Base


def snapshot_metadata() -> dict[str, Any]:
    """Return tables, columns, relationships, constraints, indexes, and enums."""

    tables: list[dict[str, Any]] = []
    enums: set[tuple[str, tuple[str, ...]]] = set()
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        columns = []
        for column in table.columns:
            type_name = str(column.type)
            if isinstance(column.type, SqlEnum):
                enums.add((column.type.name or "", tuple(column.type.enums)))
            columns.append(
                {
                    "name": column.name,
                    "type": type_name,
                    "nullable": column.nullable,
                    "primary_key": column.primary_key,
                    "default": _default_value(column.default),
                    "server_default": _default_value(column.server_default),
                }
            )
        tables.append(
            {
                "name": table.name,
                "schema": table.schema,
                "columns": columns,
                "primary_key": sorted(column.name for column in table.primary_key.columns),
                "foreign_keys": sorted(
                    {
                        f"{constraint.name or ''}:{_foreign_key_targets(constraint)}"
                        for constraint in table.constraints
                        if isinstance(constraint, ForeignKeyConstraint)
                    }
                ),
                "unique_constraints": sorted(
                    f"{constraint.name or ''}:{','.join(column.name for column in constraint.columns)}"
                    for constraint in table.constraints
                    if isinstance(constraint, UniqueConstraint)
                ),
                "check_constraints": sorted(
                    f"{constraint.name or ''}:{str(constraint.sqltext)}"
                    for constraint in table.constraints
                    if isinstance(constraint, CheckConstraint)
                ),
                "indexes": sorted(
                    {
                        f"{index.name or ''}:{index.unique}:{','.join(column.name for column in index.columns)}:{_index_where(index)}"
                        for index in table.indexes
                    }
                ),
            }
        )
    return {
        "tables": tables,
        "enums": [
            {"name": name, "values": list(values)}
            for name, values in sorted(enums)
        ],
    }


def metadata_fingerprint(snapshot: dict[str, Any] | None = None) -> str:
    """Return a stable digest suitable for before/after model comparisons."""

    payload = json.dumps(snapshot or snapshot_metadata(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _default_value(value: Any) -> str | None:
    if value is None:
        return None
    argument = getattr(value, "arg", value)
    if callable(argument):
        return argument.__qualname__
    return str(argument)


def _index_where(index: Any) -> str | None:
    where = index.dialect_options.get("postgresql", {}).get("where")
    return None if where is None else str(where)


def _foreign_key_targets(constraint: ForeignKeyConstraint) -> str:
    return ",".join(
        f"{element.parent.name}->{element.target_fullname}"
        for element in constraint.elements
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    snapshot = snapshot_metadata()
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
