"""Compatibility facade for historical reliability profile imports."""

from src.reliability.load.profiles import (
    MAX_RELIABILITY_DURATION_SECONDS,
    MAX_STEP_LOAD_DURATION_SECONDS,
    MAX_STEP_LOAD_STEPS,
    PM9_STEP_LOAD_PROFILES,
    PROFILES,
    ReliabilityProfile,
    StepLoadProfile,
    StepLoadStage,
)

__all__ = [
    "MAX_RELIABILITY_DURATION_SECONDS",
    "MAX_STEP_LOAD_DURATION_SECONDS",
    "MAX_STEP_LOAD_STEPS",
    "PM9_STEP_LOAD_PROFILES",
    "PROFILES",
    "ReliabilityProfile",
    "StepLoadProfile",
    "StepLoadStage",
]
