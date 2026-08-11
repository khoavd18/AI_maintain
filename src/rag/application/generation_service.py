"""Grounded generation, citation validation, and deterministic fallback."""

from __future__ import annotations

import logging
from typing import Any

from src.llm.base import (
    LLMGenerationRequest,
    LLMOutputError,
    LLMProvider,
    LLMProviderError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from src.llm.citation_validator import validate_citations
from src.llm.models import GroundedLLMAnswer
from src.llm.output_parser import parse_grounded_answer
from src.llm.prompt_builder import (
    build_grounded_prompt,
    retrieval_alias_key,
    safe_asset_context_contains_prompt_injection,
)
from src.rag.copilot_response import (
    CopilotAnswer,
    compose_llm_answer,
    deduplicate_sources,
    deterministic_retrieval_response,
    fallback_response,
    insufficient_generation_response,
    retrieved_chunk_payloads,
)
from src.rag.retriever import RetrievalResult
from src.rag.conversation import ConversationContext

logger = logging.getLogger("maintenance.copilot")


class GenerationService:
    """Own prompt budgeting, provider calls, output parsing, and citation gates."""

    def __init__(self, *, llm_provider: LLMProvider | None, generation_config: Any) -> None:
        self.llm_provider = llm_provider
        self.generation_config = generation_config

    def generate(
        self,
        *,
        question: str,
        conversation: ConversationContext | None,
        asset_id: str | None,
        asset_context: dict[str, Any] | None,
        retrievals: list[RetrievalResult],
        filters: dict[str, str],
        context_warnings: list[str],
    ) -> CopilotAnswer:
        if not self.generation_config.enabled or self.llm_provider is None:
            return deterministic_retrieval_response(
                question=question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrievals=retrievals,
                filters=filters,
                fallback_reason="llm_disabled",
                context_warnings=context_warnings,
            )

        if safe_asset_context_contains_prompt_injection(asset_context):
            return deterministic_retrieval_response(
                question=question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrievals=retrievals,
                filters=filters,
                fallback_reason="unsafe_asset_context",
                context_warnings=[*context_warnings, "unsafe_asset_context_blocked"],
            )

        prompt = build_grounded_prompt(
            question=question,
            conversation_context=(conversation.to_prompt_data() if conversation else None),
            asset_context=asset_context,
            retrievals=retrievals,
            max_context_chars=self.generation_config.max_context_chars,
        )
        prompt_document_count = len(
            {
                source.retrieval.doc_id or source.retrieval.source or source.retrieval.title
                for source in prompt.sources
            }
        )
        if prompt_document_count < self.generation_config.min_relevant_documents:
            return fallback_response(
                question=question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrieval_status="insufficient_evidence",
                filters=filters,
                fallback_reason="context_budget_exceeded",
                context_warnings=context_warnings,
            )

        prompt_retrievals = [source.retrieval for source in prompt.sources]
        try:
            generation = self.llm_provider.generate(
                LLMGenerationRequest(
                    system_prompt=prompt.system_prompt,
                    user_prompt=prompt.user_prompt,
                    json_schema=GroundedLLMAnswer.model_json_schema(),
                    temperature=self.generation_config.temperature,
                    max_tokens=self.generation_config.max_tokens,
                )
            )
            grounded_answer = parse_grounded_answer(generation.content)
        except LLMTimeoutError:
            return self._generation_fallback(
                reason="llm_timeout",
                question=question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrievals=prompt_retrievals,
                filters=filters,
                context_warnings=context_warnings,
            )
        except LLMUnavailableError:
            return self._generation_fallback(
                reason="llm_unavailable",
                question=question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrievals=prompt_retrievals,
                filters=filters,
                context_warnings=context_warnings,
            )
        except LLMProviderError:
            return self._generation_fallback(
                reason="llm_provider_error",
                question=question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrievals=prompt_retrievals,
                filters=filters,
                context_warnings=context_warnings,
            )
        except LLMOutputError:
            return self._generation_fallback(
                reason="invalid_llm_output",
                question=question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrievals=prompt_retrievals,
                filters=filters,
                context_warnings=context_warnings,
            )

        citation_result = validate_citations(
            grounded_answer,
            prompt.allowed_source_ids,
            source_text_by_id={
                source.citation_id: (
                    f"{source.retrieval.title}\n{source.retrieval.failure_category}\n"
                    f"{source.retrieval.text}"
                )
                for source in prompt.sources
            },
        )
        if not citation_result.valid:
            return self._generation_fallback(
                reason="invalid_citations",
                question=question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrievals=prompt_retrievals,
                filters=filters,
                context_warnings=context_warnings,
                citation_validation=citation_result.to_dict(),
            )
        if grounded_answer.insufficient_evidence:
            return insufficient_generation_response(
                question=question,
                asset_context=asset_context,
                prompt_sources=list(prompt.sources),
                filters=filters,
                provider=generation.provider,
                model=generation.model,
                citation_validation=citation_result.to_dict(),
                context_warnings=context_warnings,
            )

        grounded_answer = grounded_answer.model_copy(
            update={"source_ids": list(citation_result.cited_source_ids)}
        )
        citation_map = {
            retrieval_alias_key(source.retrieval): source.citation_id for source in prompt.sources
        }
        return CopilotAnswer(
            answer=compose_llm_answer(grounded_answer),
            asset_context=asset_context,
            sources=deduplicate_sources(prompt_retrievals, citation_map),
            retrieved_chunks=retrieved_chunk_payloads(prompt_retrievals, citation_map),
            retrieval_status="success",
            relevance_status="relevant",
            filters_applied=filters,
            response_mode="llm_grounded",
            structured_answer=grounded_answer.model_dump(mode="json"),
            llm_provider=generation.provider,
            llm_model=generation.model,
            evidence_status=("limited" if grounded_answer.confidence == "low" else "sufficient"),
            citation_validation=citation_result.to_dict(),
            context_warnings=context_warnings,
            confidence=grounded_answer.confidence,
        )

    def _generation_fallback(
        self,
        *,
        reason: str,
        question: str,
        asset_id: str | None,
        asset_context: dict[str, Any] | None,
        retrievals: list[RetrievalResult],
        filters: dict[str, str],
        context_warnings: list[str],
        citation_validation: dict[str, Any] | None = None,
    ) -> CopilotAnswer:
        logger.warning("Copilot used deterministic fallback after generation failure: %s", reason)
        return deterministic_retrieval_response(
            question=question,
            asset_id=asset_id,
            asset_context=asset_context,
            retrievals=retrievals,
            filters=filters,
            fallback_reason=reason,
            context_warnings=context_warnings,
            citation_validation=citation_validation,
        )
