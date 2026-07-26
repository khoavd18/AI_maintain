"""Safe local reliability workload profiles.

Values are test assumptions, not measured customer demand or service targets.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReliabilityProfile:
    name: str
    concurrent_users: int
    requests_per_second: float
    duration_seconds: int
    mutation_share: float
    analytics_trigger_frequency_seconds: int | None
    extended: bool = False


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
