"""LLM provider protocol and public-safe error categories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(RuntimeError):
    """Base class for errors at the external generation boundary."""


class LLMUnavailableError(LLMError):
    """Raised when a configured provider cannot be reached."""


class LLMTimeoutError(LLMError):
    """Raised when a provider exceeds its bounded timeout."""


class LLMProviderError(LLMError):
    """Raised when a provider rejects or cannot complete a request."""


class LLMOutputError(LLMError):
    """Raised when generated content violates the local output contract."""


@dataclass(frozen=True)
class LLMGenerationRequest:
    """Provider-neutral, single-turn grounded generation request."""

    system_prompt: str
    user_prompt: str
    json_schema: dict[str, Any]
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class LLMGenerationResult:
    """Raw provider result; parsing remains an application responsibility."""

    content: str
    provider: str
    model: str


class LLMProvider(Protocol):
    """Generate text without exposing provider details to RAG business logic."""

    provider_name: str
    model_name: str

    def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        """Return one non-streaming generation result."""
        ...
