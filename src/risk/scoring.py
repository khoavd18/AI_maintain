"""Explainable risk scoring heuristics for the MVP."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskBreakdown:
    """Risk score and component-level explanation."""

    score: float
    anomaly_component: float
    criticality_component: float
    ticket_component: float


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def calculate_risk_score(
    anomaly_score: float,
    criticality: float,
    open_ticket_count: int = 0,
) -> RiskBreakdown:
    """Calculate an explainable 0-100 risk score from normalized inputs."""

    anomaly_component = 0.55 * _clamp(anomaly_score)
    criticality_component = 0.30 * _clamp(criticality)
    ticket_component = 0.15 * _clamp(open_ticket_count / 5)
    score = round((anomaly_component + criticality_component + ticket_component) * 100, 2)

    return RiskBreakdown(
        score=score,
        anomaly_component=round(anomaly_component * 100, 2),
        criticality_component=round(criticality_component * 100, 2),
        ticket_component=round(ticket_component * 100, 2),
    )
