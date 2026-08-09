"""Safety-contract tests for the live graduation workflow runner."""

import hashlib

import pytest

from src.reliability.graduation_demo_smoke import (
    _validate_grounded_copilot,
    _validate_loopback_url,
    _validate_test_database_url,
)


def test_graduation_smoke_accepts_only_attestable_test_database() -> None:
    url = "postgresql+psycopg://user:secret@localhost:5432/runtime_demo_test"

    assert (
        _validate_test_database_url(url)
        == hashlib.sha256(b"pm9-test-database:runtime_demo_test").hexdigest()
    )

    with pytest.raises(ValueError, match="must end with _test"):
        _validate_test_database_url("postgresql+psycopg://user:secret@localhost:5432/runtime_demo")


def test_graduation_smoke_restricts_targets_to_loopback() -> None:
    _validate_loopback_url("http://127.0.0.1:8000", "API")
    _validate_loopback_url("http://localhost:3000", "frontend")

    with pytest.raises(ValueError, match="loopback"):
        _validate_loopback_url("https://example.com", "API")


def test_grounded_copilot_requires_response_local_alias_mapping() -> None:
    payload = {
        "response_mode": "llm_grounded",
        "fallback_reason": None,
        "citation_validation": {"valid": True, "invalid_source_ids": []},
        "retrieved_chunks": [{"citation_id": "S1"}],
        "sources": [{"citation_ids": ["S1"]}],
        "structured_answer": {"source_ids": ["S1"]},
        "safety_notice": "Safety",
    }
    _validate_grounded_copilot(payload)

    payload["structured_answer"] = {"source_ids": ["S2"]}
    with pytest.raises(RuntimeError, match="source aliases"):
        _validate_grounded_copilot(payload)
