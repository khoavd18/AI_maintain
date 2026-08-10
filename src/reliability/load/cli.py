"""Small authenticated HTTP reliability harness for a dedicated pilot test stack."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .execution_limits import STEP_LOAD_FLAG as _STEP_LOAD_FLAG
from .profile_workflow import run_profile
from .profiles import PM9_STEP_LOAD_PROFILES, PROFILES
from .request_contracts import _load_mutations
from .step_workflow import run_step_load


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password-env", default="PM8_TEST_PASSWORD")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="baseline")
    parser.add_argument(
        "--step-load-profile",
        choices=sorted(PM9_STEP_LOAD_PROFILES),
        help=(
            "Explicit PM9 capacity rehearsal; also requires "
            f"{_STEP_LOAD_FLAG}=true on an approved host."
        ),
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--mutation-fixture", type=Path)
    args = parser.parse_args()
    password = os.getenv(args.password_env)
    if not password:
        raise RuntimeError(f"{args.password_env} must provide the test password.")
    mutations = _load_mutations(args.mutation_fixture)
    if args.step_load_profile:
        report, path = run_step_load(
            base_url=args.base_url,
            username=args.username,
            password=password,
            profile=PM9_STEP_LOAD_PROFILES[args.step_load_profile],
            output_dir=args.output_dir,
            mutation_specs=mutations,
        )
        point = report["first_observed_degradation_point"]
        observed = point["target_requests_per_second"] if point is not None else "not-observed"
        print(
            "PM9 observed-boundary-only step load: "
            f"first_degradation_rps={observed} report={path}; "
            "not an SLA or production claim."
        )
        return
    report, path = run_profile(
        base_url=args.base_url,
        username=args.username,
        password=password,
        profile=PROFILES[args.profile],
        output_dir=args.output_dir,
        mutation_specs=mutations,
    )
    print(
        f"PM8 {args.profile}: requests={report['total_requests']} "
        f"failures={report['unexpected_failures']} report={path}"
    )


if __name__ == "__main__":
    main()
