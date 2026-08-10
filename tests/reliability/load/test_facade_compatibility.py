"""Historical load-harness import-surface compatibility."""

from __future__ import annotations

from src.reliability import load_harness
from src.reliability.load import cli, profiles
from src.reliability.load_harness import (
    PM9_STEP_LOAD_PROFILES,
    PROFILES,
    ReliabilityProfile,
    StepLoadProfile,
)


def test_historical_profile_imports_are_identity_preserving_exports() -> None:
    expected = {
        "PM9_STEP_LOAD_PROFILES": (PM9_STEP_LOAD_PROFILES, profiles.PM9_STEP_LOAD_PROFILES),
        "PROFILES": (PROFILES, profiles.PROFILES),
        "ReliabilityProfile": (ReliabilityProfile, profiles.ReliabilityProfile),
        "StepLoadProfile": (StepLoadProfile, profiles.StepLoadProfile),
    }

    for name, (historical, canonical) in expected.items():
        assert historical is canonical
        assert globals()[name] is canonical
        assert getattr(load_harness, name) is canonical
        assert name in load_harness.__all__


def test_historical_profile_wildcard_and_cli_bindings_are_preserved() -> None:
    namespace: dict[str, object] = {}
    exec("from src.reliability.load_harness import *", namespace)

    for name in (
        "PM9_STEP_LOAD_PROFILES",
        "PROFILES",
        "ReliabilityProfile",
        "StepLoadProfile",
    ):
        assert namespace[name] is getattr(profiles, name)
    assert load_harness.main is cli.main
