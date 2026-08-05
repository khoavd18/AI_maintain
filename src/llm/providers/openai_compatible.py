"""OpenAI-compatible Chat Completions provider."""

from __future__ import annotations

import httpx

from src.llm.base import (
    LLMGenerationRequest,
    LLMGenerationResult,
    LLMProviderError,
)
from src.llm.providers._http import post_json


class OpenAICompatibleProvider:
    """Call a configured Chat Completions API with strict structured output."""

    provider_name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        api_key: str,
        timeout_seconds: int,
        max_retries: int,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.client = client

    def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "maintenance_copilot_answer",
                    "strict": True,
                    "schema": request.json_schema,
                },
            },
        }
        response = post_json(
            url=f"{self.base_url}/chat/completions",
            payload=payload,
            headers=headers,
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
            client=self.client,
        )
        choices = response.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else None
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("Nhà cung cấp LLM không trả về nội dung có thể xử lý.")
        return LLMGenerationResult(
            content=content,
            provider=self.provider_name,
            model=self.model_name,
        )
