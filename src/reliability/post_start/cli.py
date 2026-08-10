"""Bounded authenticated post-start validation for an internal-pilot stack.

The validator exercises existing FastAPI boundaries only. It creates and
revokes normal authentication sessions, performs no business mutation, accepts
no arbitrary request targets, and writes only aggregate, credential-free
evidence outside the repository.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path

from .environment import _environment_value, load_environment_file
from .preflight import _DEFAULT_MANIFEST
from .runner import run_post_start_validation


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment-file", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument(
        "--operator-username-env",
        default="PM9_SMOKE_OPERATOR_USERNAME",
    )
    parser.add_argument(
        "--operator-password-env",
        default="PM9_SMOKE_OPERATOR_PASSWORD",
    )
    parser.add_argument(
        "--restricted-username-env",
        default="PM9_SMOKE_RESTRICTED_USERNAME",
    )
    parser.add_argument(
        "--restricted-password-env",
        default="PM9_SMOKE_RESTRICTED_PASSWORD",
    )
    parser.add_argument("--intended-host", action="store_true")
    parser.add_argument("--allow-loopback-http", action="store_true")
    args = parser.parse_args(argv)
    configured = load_environment_file(args.environment_file)
    report, report_path = run_post_start_validation(
        base_url=configured.get("NEXT_PUBLIC_API_BASE_URL", ""),
        operator_username=_environment_value(args.operator_username_env),
        operator_password=_environment_value(args.operator_password_env),
        restricted_username=_environment_value(args.restricted_username_env),
        restricted_password=_environment_value(args.restricted_password_env),
        expected_release_identifier=configured.get("RELEASE_IDENTIFIER", ""),
        expected_release_commit=configured.get("RELEASE_GIT_COMMIT", ""),
        expected_release_tag=configured.get("RELEASE_GIT_TAG", ""),
        expected_alembic_revision=configured.get(
            "RELEASE_ALEMBIC_REVISION",
            "",
        ),
        manifest_path=args.manifest,
        refresh_cookie_name=configured.get(
            "REFRESH_COOKIE_NAME",
            "maintenance_refresh",
        ),
        csrf_cookie_name=configured.get("CSRF_COOKIE_NAME", "maintenance_csrf"),
        evidence_dir=args.evidence_dir,
        host_approved=configured.get("PILOT_HOST_APPROVED", "").lower() == "true",
        intended_host=args.intended_host,
        allow_loopback_http=args.allow_loopback_http,
    )
    print(
        json.dumps(
            {
                "executed": report.executed,
                "status": report.overall_status,
                "evidence_written": report_path is not None,
                "intended_host_claim": report.intended_host_claim,
                "production_readiness_claim": False,
            },
            sort_keys=True,
        )
    )
    return 0 if report.overall_status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
