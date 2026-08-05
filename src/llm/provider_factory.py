"""Create the configured LLM provider outside routes and business logic."""

from __future__ import annotations

from src.config.settings import Settings
from src.llm.base import LLMProvider
from src.llm.providers import OllamaProvider, OpenAICompatibleProvider


def create_llm_provider(settings: Settings) -> LLMProvider | None:
    """Return no provider when generation is explicitly disabled."""

    if not settings.llm_enabled:
        return None
    common = {
        "base_url": settings.llm_base_url,
        "model_name": settings.llm_model,
        "timeout_seconds": settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
    }
    if settings.llm_provider == "ollama":
        return OllamaProvider(**common)
    return OpenAICompatibleProvider(
        **common,
        api_key=settings.llm_api_key.get_secret_value(),
    )
