"""Pilot environment validation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .runtime_environment.identity import _validate_identity_environment
from .runtime_environment.network import _validate_network_environment
from .runtime_environment.security import _validate_security_environment
from .runtime_environment.settings import _validate_runtime_environment_settings
from .runtime_environment.storage import _validate_storage_environment
from .schemas import Finding


def _validate_environment(
    manifest: dict[str, Any],
    environment: Mapping[str, str],
    repository_root: Path,
    findings: list[Finding],
) -> None:
    _validate_security_environment(manifest, environment, findings)
    _validate_network_environment(manifest, environment, findings)
    _validate_identity_environment(manifest, environment, findings)
    _validate_runtime_environment_settings(manifest, environment, findings)
    _validate_storage_environment(manifest, environment, repository_root, findings)
