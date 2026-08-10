"""Historical post-start import-surface compatibility."""

from __future__ import annotations

from src.reliability import post_start_validation
from src.reliability.environment_loader import EnvironmentFileError as CanonicalEnvironmentFileError
from src.reliability.post_start import cli, contracts
from src.reliability.post_start_validation import (
    CheckStatus,
    EnvironmentFileError,
    OverallStatus,
)


def test_historical_contract_imports_are_identity_preserving_exports() -> None:
    expected = {
        "CheckStatus": (CheckStatus, contracts.CheckStatus),
        "OverallStatus": (OverallStatus, contracts.OverallStatus),
        "EnvironmentFileError": (EnvironmentFileError, CanonicalEnvironmentFileError),
    }

    for name, (historical, canonical) in expected.items():
        assert historical is canonical
        assert globals()[name] is canonical
        assert getattr(post_start_validation, name) is canonical
        assert name in post_start_validation.__all__


def test_historical_contract_wildcard_and_cli_bindings_are_preserved() -> None:
    namespace: dict[str, object] = {}
    exec("from src.reliability.post_start_validation import *", namespace)

    assert namespace["CheckStatus"] is contracts.CheckStatus
    assert namespace["OverallStatus"] is contracts.OverallStatus
    assert namespace["EnvironmentFileError"] is CanonicalEnvironmentFileError
    assert post_start_validation.main is cli.main
