"""Secret-free deployment and release-decision contract for the internal pilot.

The validator is deliberately infrastructure-neutral.  It validates the small JSON
contract in ``deployment/`` and accepts environment, release identity, migration
identity, and reachability observations as injected values.  Findings contain only
field or service names; supplied environment values are never returned.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from .constants import CONDITIONAL_GO, GO
from .contract import validate_deployment_manifest, validate_pilot_contract

def main(argv: Sequence[str] | None = None) -> int:
    """Validate the checked-in contract without printing environment values."""

    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=repository_root / "deployment" / "pilot_manifest.json",
        type=Path,
    )
    parser.add_argument(
        "--ownership",
        default=repository_root / "deployment" / "operational_ownership.json",
        type=Path,
    )
    parser.add_argument(
        "--limitations",
        default=repository_root / "deployment" / "known_limitations.json",
        type=Path,
    )
    parser.add_argument(
        "--release-record",
        default=repository_root / "deployment" / "pilot_release_record.json",
        type=Path,
    )
    parser.add_argument("--actual-commit")
    parser.add_argument("--actual-tag")
    parser.add_argument("--actual-tag-target-commit")
    parser.add_argument("--actual-migration-revision")
    parser.add_argument(
        "--skip-environment",
        action="store_true",
        help="Skip runtime environment presence checks for static contract review.",
    )
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Validate only the deployment manifest and its repository bindings.",
    )
    args = parser.parse_args(argv)
    common = {
        "environment": None if args.skip_environment else os.environ,
        "actual_commit": args.actual_commit,
        "actual_tag": args.actual_tag,
        "actual_tag_target_commit": args.actual_tag_target_commit,
        "actual_migration_revision": args.actual_migration_revision,
        "repository_root": repository_root,
    }
    if args.manifest_only:
        report = validate_deployment_manifest(args.manifest, **common)
    else:
        report = validate_pilot_contract(
            args.manifest,
            args.ownership,
            args.limitations,
            args.release_record,
            **common,
        )
    # ASCII escapes keep this safe on Windows operator consoles with legacy encodings.
    print(json.dumps(report.as_dict(), ensure_ascii=True, indent=2))
    return 0 if report.decision in {GO, CONDITIONAL_GO} else 2


if __name__ == "__main__":
    raise SystemExit(main())

