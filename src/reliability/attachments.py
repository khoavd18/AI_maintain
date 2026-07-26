"""Read-only attachment metadata/byte integrity assessment."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select

from src.asset_management.storage import LocalAttachmentStorage
from src.config.settings import get_settings
from src.database.models import (
    AssetAttachment,
    InventoryAttachment,
    WorkOrderAttachment,
)
from src.database.session import get_session_factory


def assess_attachment_integrity(
    *,
    database_url: str,
    storage_root: Path,
) -> dict[str, Any]:
    """Check active metadata references without deleting or exposing paths."""

    storage = LocalAttachmentStorage(storage_root)
    statuses: Counter[str] = Counter()
    referenced_keys: set[str] = set()
    factory = get_session_factory(database_url)
    with factory() as session:
        records = []
        for model in (AssetAttachment, WorkOrderAttachment, InventoryAttachment):
            records.extend(
                session.execute(
                    select(model.storage_key, model.checksum).where(
                        model.deleted_at.is_(None)
                    )
                ).all()
            )
    for storage_key, checksum in records:
        key = str(storage_key)
        referenced_keys.add(key)
        statuses[
            storage.check_integrity(key, expected_checksum=str(checksum))
        ] += 1
    return {
        "active_metadata_count": len(records),
        "ok_count": statuses["ok"],
        "invalid_key_count": statuses["invalid_key"],
        "missing_byte_count": statuses["missing"],
        "unreadable_byte_count": statuses["unreadable"],
        "checksum_mismatch_count": statuses["checksum_mismatch"],
        "orphan_byte_count": storage.count_orphan_files(referenced_keys),
        "malware_scan_performed": False,
        "destructive_cleanup_performed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--storage-root", type=Path)
    args = parser.parse_args()
    settings = get_settings()
    database_url = os.getenv(args.database_url_env) or settings.database_url
    result = assess_attachment_integrity(
        database_url=database_url,
        storage_root=args.storage_root or settings.attachment_storage_root,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
