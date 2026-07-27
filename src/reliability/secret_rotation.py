"""Synthetic, secret-free signing-key rotation rehearsal for PM9."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
from typing import Any
from uuid import uuid4

from src.reliability.load_harness import (
    _validated_report_directory,
    _write_report,
)
from src.security.tokens import (
    InvalidAccessTokenError,
    create_access_token,
    create_csrf_token,
    create_refresh_token,
    decode_access_token,
    hash_token,
    refresh_session_id,
    token_hash_matches,
)

_OPT_IN_FLAG = "PM9_ALLOW_SYNTHETIC_SECRET_ROTATION"


def run_synthetic_signing_key_rotation(
    *,
    output_dir: Path | None = None,
    access_token_lifetime_minutes: int = 15,
) -> tuple[dict[str, Any], Path]:
    """Exercise current/previous-key transitions with ephemeral synthetic values."""

    if os.getenv(_OPT_IN_FLAG) != "true":
        raise RuntimeError(f"Synthetic key rotation requires {_OPT_IN_FLAG}=true.")
    if not 1 <= access_token_lifetime_minutes <= 60:
        raise ValueError("Synthetic access-token lifetime must be between 1 and 60 minutes.")
    report_dir = _validated_report_directory(output_dir)
    previous_secret = _generate_signing_secret()
    current_secret = _generate_signing_secret()
    if len(previous_secret) < 32 or len(current_secret) < 32 or previous_secret == current_secret:
        raise RuntimeError("Synthetic key generation did not produce two distinct strong keys.")

    user_id = uuid4()
    session_id = uuid4()
    previous_token, _ = create_access_token(
        user_id=user_id,
        session_id=session_id,
        role="administrator",
        user_version=1,
        signing_secret=previous_secret,
        lifetime_minutes=access_token_lifetime_minutes,
    )
    current_token, _ = create_access_token(
        user_id=user_id,
        session_id=session_id,
        role="administrator",
        user_version=1,
        signing_secret=current_secret,
        lifetime_minutes=access_token_lifetime_minutes,
    )

    pre_rotation = {
        "previous_token_valid_with_previous_as_current": _valid_for(
            previous_token, previous_secret
        ),
        "current_token_not_valid_before_current_key_is_installed": not _valid_for(
            current_token, previous_secret
        ),
    }
    overlap = {
        "previous_token_valid_through_previous_verification_key": _valid_for(
            previous_token,
            current_secret,
            previous_secret,
        ),
        "current_token_valid_with_current_key": _valid_for(
            current_token,
            current_secret,
            previous_secret,
        ),
        "current_token_not_signed_by_previous_key": not _valid_for(
            current_token,
            previous_secret,
        ),
    }
    previous_removed = {
        "previous_token_rejected": not _valid_for(previous_token, current_secret),
        "current_token_remains_valid": _valid_for(current_token, current_secret),
    }
    rollback_within_window = {
        "previous_token_valid_after_previous_key_restored_as_current": _valid_for(
            previous_token,
            previous_secret,
            current_secret,
        ),
        "current_token_valid_through_rollback_previous_key": _valid_for(
            current_token,
            previous_secret,
            current_secret,
        ),
    }
    forward_restored = {
        "previous_token_valid_during_restored_overlap": _valid_for(
            previous_token,
            current_secret,
            previous_secret,
        ),
        "current_token_valid_after_forward_restore": _valid_for(
            current_token,
            current_secret,
            previous_secret,
        ),
    }
    simulated_post_window_removal = {
        "previous_token_rejected_after_previous_key_removed": not _valid_for(
            previous_token,
            current_secret,
        ),
        "current_token_valid_after_previous_key_removed": _valid_for(
            current_token,
            current_secret,
        ),
    }

    refresh_token = create_refresh_token(session_id)
    csrf_token = create_csrf_token()
    session_mechanics = {
        "opaque_refresh_session_identifier_preserved": (
            refresh_session_id(refresh_token) == session_id
        ),
        "csrf_hash_verification_preserved": token_hash_matches(
            csrf_token,
            hash_token(csrf_token),
        ),
        "database_backed_refresh_rotation_executed": False,
    }
    phases = {
        "pre_rotation": pre_rotation,
        "overlap": overlap,
        "previous_key_removal": previous_removed,
        "rollback_within_window": rollback_within_window,
        "forward_restore": forward_restored,
        "simulated_post_window_removal": simulated_post_window_removal,
        "session_mechanics": session_mechanics,
    }
    assertions = [
        value
        for phase in phases.values()
        for key, value in phase.items()
        if not key.endswith("_executed")
    ]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "synthetic-signing-key-rotation",
        "synthetic_only": True,
        "real_pilot_secrets_used": False,
        "real_pilot_rotation_executed": False,
        "real_pilot_rotation_gate_passed": False,
        "configured_overlap_window_minutes": access_token_lifetime_minutes,
        "real_time_overlap_window_elapsed": False,
        "secret_material_persisted": False,
        "token_material_persisted": False,
        "phases": phases,
        "synthetic_assertions_passed": all(assertions),
        "production_readiness_claim": False,
        "result_interpretation": (
            "This synthetic rehearsal validates the application token APIs and "
            "configuration transitions only. It does not verify pilot secrets, process "
            "restart coordination, database credentials, or a real elapsed overlap window."
        ),
    }
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = report_dir / f"pm9-synthetic-secret-rotation-{timestamp}.json"
    _write_report(report_path, report)
    return report, report_path


def _valid_for(
    token: str,
    current_secret: str,
    previous_secret: str = "",
) -> bool:
    try:
        decode_access_token(
            token,
            current_secret,
            previous_signing_secret=previous_secret,
        )
    except InvalidAccessTokenError:
        return False
    return True


def _generate_signing_secret() -> str:
    return secrets.token_urlsafe(48)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--access-token-lifetime-minutes",
        type=int,
        default=15,
    )
    args = parser.parse_args()
    report, report_path = run_synthetic_signing_key_rotation(
        output_dir=args.output_dir,
        access_token_lifetime_minutes=args.access_token_lifetime_minutes,
    )
    print(
        "PM9 synthetic signing-key rotation: "
        f"assertions_passed={report['synthetic_assertions_passed']} "
        f"report={report_path}; real pilot-secret rotation remains unverified."
    )


if __name__ == "__main__":
    main()
