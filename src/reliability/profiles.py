"""Safe local reliability workload profiles.

Values are test assumptions, not measured customer demand or service targets.
"""

from dataclasses import dataclass
import math
import re


MAX_RELIABILITY_DURATION_SECONDS = 900
MAX_STEP_LOAD_DURATION_SECONDS = 900
MAX_STEP_LOAD_STEPS = 10

_PROFILE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class ReliabilityProfile:
    name: str
    concurrent_users: int
    requests_per_second: float
    duration_seconds: int
    mutation_share: float
    analytics_trigger_frequency_seconds: int | None
    extended: bool = False

    def __post_init__(self) -> None:
        _validate_profile_name(self.name)
        if not 1 <= self.concurrent_users <= 100:
            raise ValueError("Concurrent users must be between 1 and 100.")
        if (
            not math.isfinite(self.requests_per_second)
            or self.requests_per_second <= 0
            or self.requests_per_second > 100
        ):
            raise ValueError("Requests per second must be greater than 0 and at most 100.")
        if not 1 <= self.duration_seconds <= MAX_RELIABILITY_DURATION_SECONDS:
            raise ValueError(
                "Reliability profile duration must be between 1 and "
                f"{MAX_RELIABILITY_DURATION_SECONDS} seconds."
            )
        if (
            not math.isfinite(self.mutation_share)
            or self.mutation_share < 0
            or self.mutation_share > 1
        ):
            raise ValueError("Mutation share must be between 0 and 1.")
        if (
            self.analytics_trigger_frequency_seconds is not None
            and self.analytics_trigger_frequency_seconds <= 0
        ):
            raise ValueError("Analytics trigger frequency must be positive when supplied.")


@dataclass(frozen=True)
class StepLoadStage:
    requests_per_second: float
    concurrent_users: int

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.requests_per_second)
            or self.requests_per_second <= 0
            or self.requests_per_second > 100
        ):
            raise ValueError("Step requests per second must be greater than 0 and at most 100.")
        if not 1 <= self.concurrent_users <= 100:
            raise ValueError("Step concurrent users must be between 1 and 100.")


@dataclass(frozen=True)
class StepLoadProfile:
    """Bounded, explicitly selected capacity-rehearsal assumptions."""

    name: str
    stages: tuple[StepLoadStage, ...]
    stage_duration_seconds: int
    mutation_share: float = 0.0

    def __post_init__(self) -> None:
        _validate_profile_name(self.name)
        if not self.stages or len(self.stages) > MAX_STEP_LOAD_STEPS:
            raise ValueError(
                f"Step-load profiles require between 1 and {MAX_STEP_LOAD_STEPS} stages."
            )
        if any(
            current.requests_per_second <= previous.requests_per_second
            for previous, current in zip(self.stages, self.stages[1:], strict=False)
        ):
            raise ValueError("Step-load requests per second must increase at every stage.")
        if self.stage_duration_seconds <= 0:
            raise ValueError("Step-load stage duration must be positive.")
        if self.total_duration_seconds > MAX_STEP_LOAD_DURATION_SECONDS:
            raise ValueError(
                "Total step-load duration must not exceed "
                f"{MAX_STEP_LOAD_DURATION_SECONDS} seconds."
            )
        if (
            not math.isfinite(self.mutation_share)
            or self.mutation_share < 0
            or self.mutation_share > 1
        ):
            raise ValueError("Mutation share must be between 0 and 1.")

    @property
    def total_duration_seconds(self) -> int:
        return len(self.stages) * self.stage_duration_seconds

    def stage_profile(self, stage: StepLoadStage) -> ReliabilityProfile:
        rate_label = f"{stage.requests_per_second:g}".replace(".", "_")
        suffix = f"-{rate_label}rps"
        return ReliabilityProfile(
            name=f"{self.name[: 64 - len(suffix)]}{suffix}",
            concurrent_users=stage.concurrent_users,
            requests_per_second=stage.requests_per_second,
            duration_seconds=self.stage_duration_seconds,
            mutation_share=self.mutation_share,
            analytics_trigger_frequency_seconds=None,
            extended=False,
        )


def _validate_profile_name(value: str) -> None:
    if not _PROFILE_NAME_PATTERN.fullmatch(value):
        raise ValueError(
            "Profile names must use 1-64 lowercase letters, numbers, underscores, or hyphens."
        )


PROFILES = {
    "baseline": ReliabilityProfile(
        name="baseline",
        concurrent_users=4,
        requests_per_second=4.0,
        duration_seconds=30,
        mutation_share=0.10,
        analytics_trigger_frequency_seconds=None,
    ),
    "stress": ReliabilityProfile(
        name="stress",
        concurrent_users=8,
        requests_per_second=12.0,
        duration_seconds=45,
        mutation_share=0.15,
        analytics_trigger_frequency_seconds=None,
    ),
    "recovery": ReliabilityProfile(
        name="recovery",
        concurrent_users=2,
        requests_per_second=2.0,
        duration_seconds=30,
        mutation_share=0.05,
        analytics_trigger_frequency_seconds=None,
    ),
    "soak": ReliabilityProfile(
        name="soak",
        concurrent_users=4,
        requests_per_second=3.0,
        duration_seconds=900,
        mutation_share=0.05,
        analytics_trigger_frequency_seconds=None,
        extended=True,
    ),
}


PM9_STEP_LOAD_PROFILES = {
    "capacity": StepLoadProfile(
        name="capacity",
        stages=(
            StepLoadStage(requests_per_second=4.0, concurrent_users=4),
            StepLoadStage(requests_per_second=8.0, concurrent_users=4),
            StepLoadStage(requests_per_second=12.0, concurrent_users=8),
            StepLoadStage(requests_per_second=16.0, concurrent_users=8),
            StepLoadStage(requests_per_second=20.0, concurrent_users=10),
        ),
        stage_duration_seconds=30,
    )
}
