"""Privacy-safe request diagnostics for the bounded Copilot pipeline."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
import json
import logging
from typing import Any
from uuid import uuid4

logger = logging.getLogger("maintenance.copilot.diagnostics")
_ACTIVE_DIAGNOSTICS: ContextVar[CopilotDiagnostics | None] = ContextVar(
    "copilot_diagnostics",
    default=None,
)


@dataclass
class CopilotDiagnostics:
    """Operational facts only; never store questions, prompts, answers, or document text."""

    request_id: str
    route_status: str | None = None
    intent: str | None = None
    filters_present: dict[str, bool] = field(default_factory=dict)
    relaxation_steps: list[str] = field(default_factory=list)
    candidate_count: int = 0
    relevant_count: int = 0
    document_count: int = 0
    latency_ms: dict[str, float] = field(
        default_factory=lambda: {
            "routing": 0.0,
            "retrieval": 0.0,
            "reranking": 0.0,
            "generation": 0.0,
            "total": 0.0,
        }
    )
    response_mode: str | None = None
    fallback_reason: str | None = None
    provider: str | None = None
    model: str | None = None
    citation_status: str = "not_applicable"
    provider_failure_category: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "route_status": self.route_status,
            "intent": self.intent,
            "filters_present": dict(self.filters_present),
            "relaxation_steps": list(self.relaxation_steps),
            "candidate_count": self.candidate_count,
            "relevant_count": self.relevant_count,
            "document_count": self.document_count,
            "latency_ms": {key: round(value, 3) for key, value in self.latency_ms.items()},
            "response_mode": self.response_mode,
            "fallback_reason": self.fallback_reason,
            "provider": self.provider,
            "model": self.model,
            "citation_status": self.citation_status,
            "provider_failure_category": self.provider_failure_category,
        }


def start_diagnostics(
    request_id: str | None,
) -> tuple[CopilotDiagnostics, Token[CopilotDiagnostics | None]]:
    """Start one context-local diagnostics record with a bounded correlation ID."""

    safe_request_id = " ".join((request_id or str(uuid4())).split())[:100]
    diagnostics = CopilotDiagnostics(request_id=safe_request_id)
    return diagnostics, _ACTIVE_DIAGNOSTICS.set(diagnostics)


def reset_diagnostics(token: Token[CopilotDiagnostics | None]) -> None:
    _ACTIVE_DIAGNOSTICS.reset(token)


def current_diagnostics() -> CopilotDiagnostics | None:
    return _ACTIVE_DIAGNOSTICS.get()


def add_stage_latency(stage: str, duration_ms: float) -> None:
    diagnostics = current_diagnostics()
    if diagnostics is not None and stage in diagnostics.latency_ms:
        diagnostics.latency_ms[stage] += max(0.0, float(duration_ms))


def emit_diagnostics(diagnostics: CopilotDiagnostics) -> None:
    """Emit one structured record containing no user or retrieved content."""

    logger.info(
        "copilot_request_diagnostics %s",
        json.dumps(diagnostics.to_dict(), ensure_ascii=True, separators=(",", ":")),
    )
