"""Concrete outbound LLM providers."""

from src.llm.providers.ollama import OllamaProvider
from src.llm.providers.openai_compatible import OpenAICompatibleProvider

__all__ = ["OllamaProvider", "OpenAICompatibleProvider"]
