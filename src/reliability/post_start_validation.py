"""Historical import and CLI facade for authenticated post-start validation."""

from src.reliability.post_start.cli import main
from src.reliability.environment_loader import EnvironmentFileError
from src.reliability.post_start.contracts import (
    CheckStatus,
    OverallStatus,
    PostStartCheck,
    PostStartReport,
)
from src.reliability.post_start.environment import load_environment_file
from src.reliability.post_start.preflight import (  # noqa: F401 - compatibility aliases
    PostStartValidationError,
    _DEFAULT_MANIFEST,
    _EXPECTED_JOB_TYPES,
    _PostStartPreflight,
    _REPOSITORY_ROOT,
    _load_manifest_expectations,
    _prepare_post_start_validation,
    _required_text,
    _validate_credentials,
    _validated_origin,
    validate_post_start_preconditions,
)
from src.reliability.post_start.runner import run_post_start_validation

__all__ = [
    "CheckStatus",
    "EnvironmentFileError",
    "OverallStatus",
    "PostStartCheck",
    "PostStartReport",
    "PostStartValidationError",
    "load_environment_file",
    "main",
    "run_post_start_validation",
    "validate_post_start_preconditions",
]


if __name__ == "__main__":
    raise SystemExit(main())
