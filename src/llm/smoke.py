"""Credential-safe smoke check for the configured outbound LLM provider."""

from __future__ import annotations

import json
import sys

from src.config.settings import get_settings
from src.llm.base import LLMError, LLMGenerationRequest
from src.llm.provider_factory import create_llm_provider

_SMOKE_SCHEMA = {
    "type": "object",
    "properties": {"status": {"type": "string", "enum": ["ok"]}},
    "required": ["status"],
    "additionalProperties": False,
}


def main() -> None:
    settings = get_settings()
    provider = create_llm_provider(settings)
    if provider is None:
        print("LLM smoke skipped: set LLM_ENABLED=true with an explicit model and base URL.")
        raise SystemExit(2)
    try:
        result = provider.generate(
            LLMGenerationRequest(
                system_prompt="Return only JSON matching the supplied schema.",
                user_prompt='Return {"status":"ok"}.',
                json_schema=_SMOKE_SCHEMA,
                temperature=0.0,
                max_tokens=128,
            )
        )
        payload = json.loads(result.content)
    except (LLMError, ValueError, json.JSONDecodeError):
        print("LLM smoke failed at the configured provider boundary.", file=sys.stderr)
        raise SystemExit(1) from None
    if payload != {"status": "ok"}:
        print("LLM smoke failed structured-output validation.", file=sys.stderr)
        raise SystemExit(1)
    print(f"LLM smoke passed: provider={result.provider}, model={result.model}")


if __name__ == "__main__":
    main()
