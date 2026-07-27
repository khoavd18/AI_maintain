"""Synthetic PM9 signing-key rotation rehearsal tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.settings import Settings
from src.release import CANONICAL_SCHEMA_REVISION
from src.reliability.secret_rotation import run_synthetic_signing_key_rotation


def test_synthetic_rotation_requires_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PM9_ALLOW_SYNTHETIC_SECRET_ROTATION", raising=False)
    with pytest.raises(RuntimeError, match="PM9_ALLOW_SYNTHETIC_SECRET_ROTATION"):
        run_synthetic_signing_key_rotation(output_dir=tmp_path)


def test_rotation_covers_overlap_removal_and_rollback_without_persisting_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_SYNTHETIC_SECRET_ROTATION", "true")
    generated_secrets = iter(
        (
            "synthetic-previous-signing-secret-" + ("p" * 40),
            "synthetic-current-signing-secret-" + ("c" * 40),
        )
    )
    monkeypatch.setattr(
        "src.reliability.secret_rotation._generate_signing_secret",
        lambda: next(generated_secrets),
    )

    report, report_path = run_synthetic_signing_key_rotation(
        output_dir=tmp_path,
        access_token_lifetime_minutes=15,
    )

    assert report["synthetic_assertions_passed"] is True
    assert all(report["phases"]["pre_rotation"].values())
    assert all(report["phases"]["overlap"].values())
    assert all(report["phases"]["previous_key_removal"].values())
    assert all(report["phases"]["rollback_within_window"].values())
    assert all(report["phases"]["forward_restore"].values())
    assert all(report["phases"]["simulated_post_window_removal"].values())
    assert (
        report["phases"]["session_mechanics"]["opaque_refresh_session_identifier_preserved"] is True
    )
    assert report["real_time_overlap_window_elapsed"] is False
    assert report["real_pilot_rotation_gate_passed"] is False
    assert report["production_readiness_claim"] is False

    serialized = report_path.read_text(encoding="utf-8")
    assert "synthetic-previous-signing-secret" not in serialized
    assert "synthetic-current-signing-secret" not in serialized
    assert "eyJ" not in serialized
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert "csrf_token" not in serialized


def test_pilot_settings_reject_weak_or_duplicate_rotation_keys() -> None:
    base = {
        "_env_file": None,
        "app_environment": "pilot",
        "storage_backend": "postgresql",
        "database_url": (
            "postgresql+psycopg://pilot_user:synthetic-strong-password@"
            "db.example.test/pilot_database"
        ),
        "auth_cookie_secure": True,
        "release_identifier": "product-milestone-9-rehearsal",
        "release_git_commit": "a" * 40,
        "release_git_tag": "product-milestone-9-candidate",
        "release_alembic_revision": CANONICAL_SCHEMA_REVISION,
    }
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(**base, token_signing_secret="weak")

    current = "synthetic-current-key-" + ("x" * 40)
    with pytest.raises(ValidationError, match="must differ"):
        Settings(
            **base,
            token_signing_secret=current,
            token_signing_previous_secret=current,
        )
