"""Regression tests for bounded grounded-generation correction."""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.llm.base import LLMGenerationRequest, LLMGenerationResult
from src.llm.prompt_builder import build_grounded_prompt
from src.rag.copilot import CopilotGenerationConfig, MaintenanceCopilot
from src.rag.retriever import RetrievalResult


class _AssetContext:
    def get_asset_context(self, asset_id: str) -> dict[str, Any]:
        return {
            "asset_id": asset_id,
            "asset_profile": {
                "asset_id": asset_id,
                "asset_type": "Máy lạnh",
                "manufacturer": "Daikin",
                "model": "RZAG71-140N",
            },
            "latest_risk": {
                "asset_id": asset_id,
                "asset_type": "Máy lạnh",
            },
            "recent_anomalies": [],
        }

    def list_tickets(self, asset_id: str | None = None, limit: int = 3) -> list[dict[str, str]]:
        return []


class _Retriever:
    minimum_relevance_score = 0.5

    def search(self, *_args: Any, **_kwargs: Any) -> list[RetrievalResult]:
        return [_evidence()]


class _SequenceProvider:
    provider_name = "sequence"
    model_name = "sequence-model"

    def __init__(self, *results: str) -> None:
        self.results = list(results)
        self.requests: list[LLMGenerationRequest] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        self.requests.append(request)
        result = self.results[len(self.requests) - 1]
        return LLMGenerationResult(
            content=result,
            provider=self.provider_name,
            model=self.model_name,
        )


def test_prompt_directs_answer_when_current_evidence_is_adequate() -> None:
    prompt = build_grounded_prompt(
        question="Máy lạnh này cần kiểm tra gì?",
        asset_context=None,
        retrievals=[_evidence()],
        max_context_chars=12_000,
    )

    system_prompt = prompt.system_prompt.casefold()
    assert "trả lời trực tiếp" in system_prompt
    assert "không được từ chối chỉ vì" in system_prompt
    assert "insufficient_evidence=true chỉ khi" in system_prompt
    assert "bắt buộc đặt insufficient_evidence=false" in system_prompt
    assert "escalation_required là cờ chuyển cấp độc lập" in system_prompt


def test_absent_required_evidence_still_remains_fail_closed() -> None:
    provider = _SequenceProvider(_insufficient_answer())

    response = _copilot(provider).ask(
        "HVAC này cần kiểm tra thông số không có trong nguồn?",
        asset_id="HVAC-001",
    )

    assert provider.calls == 1
    assert response.response_mode == "deterministic_fallback"
    assert response.fallback_reason == "llm_insufficient_evidence"


def test_unsupported_safety_prose_is_rejected_after_one_bounded_repair() -> None:
    unsupported = _unsupported_safety_answer()
    provider = _SequenceProvider(unsupported, unsupported)

    response = _copilot(provider).ask(
        "HVAC này cần kiểm tra gì?",
        asset_id="HVAC-001",
    )

    assert provider.calls == 2
    assert response.response_mode == "deterministic_fallback"
    assert response.fallback_reason == "invalid_citations"
    assert response.citation_validation is not None
    assert response.citation_validation["unsupported_claims"] == ["safety_warnings[0]"]


def test_one_bounded_repair_can_return_a_supported_cited_answer() -> None:
    provider = _SequenceProvider(_unsupported_safety_answer(), _supported_answer())

    response = _copilot(provider).ask(
        "HVAC này cần kiểm tra gì?",
        asset_id="HVAC-001",
    )

    assert provider.calls == 2
    assert response.response_mode == "llm_grounded"
    assert response.fallback_reason is None
    assert response.citation_validation is not None
    assert response.citation_validation["valid"] is True
    assert "generation_validation_repair_succeeded" in response.context_warnings


def test_repair_uses_no_prior_prose_stale_ids_or_unvalidated_evidence() -> None:
    stale_marker = "STALE-UNSUPPORTED-ASSISTANT-PROSE"
    first_payload = json.loads(_unsupported_safety_answer())
    first_payload["summary"] = stale_marker
    first_payload["summary_source_ids"] = ["S9"]
    first_payload["source_ids"] = ["S1", "S9"]
    provider = _SequenceProvider(
        json.dumps(first_payload, ensure_ascii=False),
        _supported_answer(),
    )

    response = _copilot(provider).ask(
        "Với bước vừa nêu, kiểm tra tiếp HVAC thế nào?",
        asset_id="HVAC-001",
        conversation_context={
            "recent_intent": "troubleshooting",
            "resolved_asset_id": "HVAC-001",
            "resolved_asset_type": "Máy lạnh",
            "previous_source_ids": ["S9"],
            "previous_answer_summary": "STALE-PRIOR-TURN-SUMMARY",
        },
    )

    assert response.response_mode == "llm_grounded"
    assert provider.calls == 2
    repair_request = provider.requests[1]
    assert stale_marker not in repair_request.user_prompt
    assert "STALE-PRIOR-TURN-SUMMARY" not in repair_request.user_prompt
    assert '"source_id":"S1"' in repair_request.user_prompt
    assert '"source_id":"S9"' not in repair_request.user_prompt
    assert '"unsupported_claims"' in repair_request.user_prompt


@pytest.mark.parametrize(
    "question",
    [
        "Máy lạnh này cần kiểm tra gì?",
        "May lanh nay can kiem tra gi?",
        "What should I check on this HVAC unit?",
        "Với bước vừa nêu, kiểm tra tiếp phần liên quan thế nào?",
    ],
)
def test_grounding_contract_is_language_and_follow_up_invariant(question: str) -> None:
    prompt = build_grounded_prompt(
        question=question,
        conversation_context={
            "recent_intent": "troubleshooting",
            "resolved_asset_type": "Máy lạnh",
        },
        asset_context=None,
        retrievals=[_evidence()],
        max_context_chars=12_000,
    )

    system_prompt = prompt.system_prompt.casefold()
    assert "không tự thêm cảnh báo an toàn" in system_prompt
    assert "bằng chứng kỹ thuật duy nhất" in system_prompt
    assert '"source_id":"S1"' in prompt.user_prompt


def _copilot(provider: _SequenceProvider) -> MaintenanceCopilot:
    return MaintenanceCopilot(
        asset_context_provider=_AssetContext(),
        retriever=_Retriever(),
        llm_provider=provider,
        generation_config=CopilotGenerationConfig(enabled=True),
    )


def _evidence() -> RetrievalResult:
    return RetrievalResult(
        chunk_id="CURRENT-HVAC-chunk",
        doc_id="CURRENT-HVAC",
        title="Kiểm tra lưới lọc HVAC",
        doc_type="Danh sách kiểm tra",
        asset_type="Máy lạnh",
        source="Nguồn đã kiểm soát",
        text="Kiểm tra lưới lọc và cô lập nguồn điện trước khi mở tủ điện.",
        score=0.95,
        version="1.0",
        language="vi",
        equipment_model_identifiers=("RZAG71-140N",),
    )


def _supported_answer() -> str:
    return json.dumps(
        {
            "summary": "Kiểm tra lưới lọc và cô lập nguồn điện trước khi mở tủ điện.",
            "summary_source_ids": ["S1"],
            "possible_causes": [],
            "recommended_checks": [
                {
                    "text": "Kiểm tra lưới lọc trước khi mở tủ điện.",
                    "source_ids": ["S1"],
                }
            ],
            "safety_warnings": [
                {
                    "text": "Cô lập nguồn điện trước khi mở tủ điện.",
                    "source_ids": ["S1"],
                }
            ],
            "escalation_required": False,
            "source_ids": ["S1"],
            "confidence": "medium",
            "insufficient_evidence": False,
        },
        ensure_ascii=False,
    )


def _unsupported_safety_answer() -> str:
    payload = json.loads(_supported_answer())
    payload["safety_warnings"] = [
        {
            "text": "Đội mũ bảo hộ và mang dây chống rơi trên mái.",
            "source_ids": ["S1"],
        }
    ]
    return json.dumps(payload, ensure_ascii=False)


def _insufficient_answer() -> str:
    payload = json.loads(_supported_answer())
    payload.update(
        {
            "possible_causes": [],
            "recommended_checks": [],
            "safety_warnings": [],
            "escalation_required": True,
            "confidence": "low",
            "insufficient_evidence": True,
        }
    )
    return json.dumps(payload, ensure_ascii=False)
