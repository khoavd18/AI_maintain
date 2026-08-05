"""Ollama chat provider with native JSON-Schema output enforcement."""

from __future__ import annotations

import httpx

from src.llm.base import (
    LLMGenerationRequest,
    LLMGenerationResult,
    LLMProviderError,
)
from src.llm.providers._http import post_json


class OllamaProvider:
    """Call an operator-configured Ollama server without model defaults."""

    provider_name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        timeout_seconds: int,
        max_retries: int,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.client = client

    def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        payload = {
            "model": self.model_name,
            "stream": False,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "format": request.json_schema,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        response = post_json(
            url=f"{self.base_url}/api/chat",
            payload=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
            client=self.client,
        )
        message = response.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("Ollama không trả về nội dung có thể xử lý.")
        return LLMGenerationResult(
            content=content,
            provider=self.provider_name,
            model=self.model_name,
        )
