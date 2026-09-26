"""Command-line adapter for the multi-domain ingestion workflow."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Sequence

from data_platform.ingestion.domains.catalog import DOMAINS
from data_platform.ingestion.domains.extraction import extract_domain
from data_platform.ingestion.domains.raw_loading import load_raw_domain
from data_platform.ingestion.domains.reconciliation import (
    finalize_watermarks,
    reconcile_run,
)
from data_platform.ingestion.domains.run_tracking import (
    complete_run,
    fail_run,
    pipeline_state,
    retry_run,
    start_run,
)
from data_platform.ingestion.domains.source_validation import validate_domain_integrity


def build_parser() -> argparse.ArgumentParser:
    """Build the stable CLI used by Airflow and historical runbooks."""

    parser = argparse.ArgumentParser(
        description="Independent-watermark domain ingestion and reconciliation."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    start.add_argument("--run-id", required=True)
    start.add_argument("--phase", required=True)
    start.add_argument("--fault-domain", default="")
    extract = subparsers.add_parser("extract")
    extract.add_argument("--run-id", required=True)
    extract.add_argument("--phase", required=True)
    extract.add_argument("--domain", choices=DOMAINS, required=True)
    load = subparsers.add_parser("load-raw")
    load.add_argument("--run-id", required=True)
    load.add_argument("--domain", choices=DOMAINS, required=True)
    load.add_argument("--fault-domain", default="")
    reconcile = subparsers.add_parser("reconcile")
    reconcile.add_argument("--run-id", required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--run-id", required=True)
    complete = subparsers.add_parser("complete")
    complete.add_argument("--run-id", required=True)
    fail = subparsers.add_parser("audit-fail")
    fail.add_argument("--run-id", required=True)
    fail.add_argument("--step", required=True)
    fail.add_argument("--error", default="")
    retry = subparsers.add_parser("audit-retry")
    retry.add_argument("--run-id", required=True)
    retry.add_argument("--step", required=True)
    retry.add_argument("--error", default="")
    state = subparsers.add_parser("state")
    state.add_argument("--run-id", required=True)
    subparsers.add_parser("validate")
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Dispatch one parsed command without mixing CLI parsing into services."""

    if args.command == "start":
        return start_run(
            args.run_id,
            args.phase,
            fault_domain=args.fault_domain or None,
        )
    if args.command == "extract":
        return extract_domain(args.run_id, args.phase, args.domain)
    if args.command == "load-raw":
        return load_raw_domain(
            args.run_id,
            args.domain,
            fault_domain=args.fault_domain or None,
        )
    if args.command == "reconcile":
        return reconcile_run(args.run_id)
    if args.command == "finalize":
        return finalize_watermarks(args.run_id)
    if args.command == "complete":
        return complete_run(args.run_id)
    if args.command == "audit-fail":
        return fail_run(args.run_id, args.step, args.error)
    if args.command == "audit-retry":
        return retry_run(args.run_id, args.step, args.error)
    if args.command == "state":
        return pipeline_state(args.run_id)
    return validate_domain_integrity()


def main(argv: Sequence[str] | None = None) -> None:
    """Run the stable JSON-emitting domain-pipeline CLI."""

    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(run_command(args), sort_keys=True, default=str))
