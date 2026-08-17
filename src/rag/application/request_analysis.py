"""Input validation, conversation resolution, and deterministic query routing."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from src.rag.adapters.asset_context import AssetContextProvider
from src.rag.applicability import (
    ApplicabilityConstraint,
    build_applicability_constraint,
)
from src.rag.conversation import ConversationContext, parse_conversation_context
from src.rag.evidence_boundary import missing_exact_parameter_context
from src.rag.query_analysis import (
    QueryAnalysis,
    QueryAnalyzer,
    normalize_document_type,
    normalize_failure_category,
)

MAX_QUESTION_LENGTH = 1000


@dataclass(frozen=True)
class PreparedCopilotRequest:
    """All routing facts needed by the retrieval and generation stages."""

    normalized_question: str
    asset_id: str | None
    conversation: ConversationContext | None
    pre_analysis: QueryAnalysis | None
    analysis: QueryAnalysis | None
    asset_context: dict[str, Any] | None
    filters: dict[str, str]
    relaxable_filters: frozenset[str]
    applicability: ApplicabilityConstraint | None
    retrieval_query: str | None
    early_status: str | None = None


class RequestAnalysisService:
    """Own the ordered, non-LLM input and query-analysis stages."""

    def __init__(
        self,
        *,
        asset_context_provider: AssetContextProvider,
        query_analyzer: QueryAnalyzer,
    ) -> None:
        self.asset_context_provider = asset_context_provider
        self.query_analyzer = query_analyzer

    def prepare(
        self,
        *,
        question: str,
        asset_id: str | None,
        document_type: str | None,
        failure_category: str | None,
        version: str | None,
        language: str | None,
        conversation_context: dict[str, Any] | None,
    ) -> PreparedCopilotRequest:
        normalized_question = " ".join(question.split())
        self._validate_question(normalized_question)
        conversation = parse_conversation_context(conversation_context)
        if conversation and conversation.unsafe:
            return self._early(normalized_question, asset_id, conversation, "unsafe_conversation")

        pre_analysis = self.query_analyzer.analyze(normalized_question)
        if pre_analysis.status in {"prompt_injection", "unsafe_operation"}:
            return self._early(
                normalized_question,
                asset_id,
                conversation,
                pre_analysis.status,
                pre_analysis=pre_analysis,
            )
        if pre_analysis.status == "conversation":
            return self._early(
                normalized_question,
                asset_id,
                conversation,
                "conversation",
                pre_analysis=pre_analysis,
            )

        contextual_asset_id = (
            conversation.resolved_asset_id
            if (
                conversation
                and pre_analysis.follow_up_reference
                and not asset_id
                and not pre_analysis.asset_type
            )
            else None
        )
        effective_asset_id = asset_id or contextual_asset_id
        asset_context = self._load_asset_context(effective_asset_id)
        selected_asset_type = self._asset_type_from_context(asset_context)
        contextual_asset_type = (
            conversation.resolved_asset_type
            if (
                conversation
                and pre_analysis.follow_up_reference
                and not selected_asset_type
                and not pre_analysis.asset_type
            )
            else None
        )
        analysis = self.query_analyzer.analyze(
            normalized_question,
            selected_asset_type=selected_asset_type or contextual_asset_type,
            recent_intent=(conversation.recent_intent if conversation else None),
            has_follow_up_context=conversation is not None,
        )
        effective_conversation = (
            conversation if conversation and analysis.follow_up_reference else None
        )
        current_asset_changed = bool(
            effective_conversation
            and pre_analysis.asset_type
            and pre_analysis.asset_type != effective_conversation.resolved_asset_type
        )
        current_topic_changed = bool(effective_conversation and analysis.symptom_present)
        if effective_conversation and (current_asset_changed or current_topic_changed):
            effective_conversation = replace(
                effective_conversation,
                resolved_asset_id=None,
                resolved_asset_type=(
                    pre_analysis.asset_type or effective_conversation.resolved_asset_type
                ),
                resolved_failure_category=analysis.failure_category,
                previous_source_ids=(),
                previous_answer_summary="",
            )
        asset_type_filter = analysis.asset_type or selected_asset_type or contextual_asset_type
        contextual_failure = (
            effective_conversation.resolved_failure_category if effective_conversation else None
        )
        normalized_document_type = normalize_document_type(document_type)
        normalized_failure_category = normalize_failure_category(failure_category)
        filters = self._clean_filters(
            asset_type=asset_type_filter,
            document_type=normalized_document_type or analysis.document_type,
            failure_category=normalized_failure_category
            or analysis.failure_category
            or contextual_failure,
            version=version,
            language=language,
        )
        relaxable_filters = frozenset(
            key
            for key, relaxable in {
                "failure_category": "failure_category" in filters,
                "document_type": bool(analysis.document_type and not normalized_document_type),
            }.items()
            if relaxable
        )
        applicability = build_applicability_constraint(normalized_question, asset_context)
        guard_status = None
        if applicability.question_conflicts_with_selected_model:
            guard_status = "model_context_mismatch"
        elif (
            effective_conversation and asset_context is None and applicability.requested_identifiers
        ):
            guard_status = "missing_asset_context"
        elif missing_exact_parameter_context(normalized_question):
            guard_status = "parameter_confirmation_required"
        if guard_status:
            return PreparedCopilotRequest(
                normalized_question=normalized_question,
                asset_id=effective_asset_id,
                conversation=effective_conversation,
                pre_analysis=pre_analysis,
                analysis=analysis,
                asset_context=asset_context,
                filters=filters,
                relaxable_filters=relaxable_filters,
                applicability=applicability,
                retrieval_query=None,
                early_status=guard_status,
            )
        if analysis.status != "supported":
            return PreparedCopilotRequest(
                normalized_question=normalized_question,
                asset_id=effective_asset_id,
                conversation=effective_conversation,
                pre_analysis=pre_analysis,
                analysis=analysis,
                asset_context=asset_context,
                filters=filters,
                relaxable_filters=relaxable_filters,
                applicability=applicability,
                retrieval_query=None,
                early_status=analysis.status,
            )

        retrieval_query = self._build_retrieval_query(
            normalized_question,
            self._recent_ticket_context(asset_id),
            previous_answer_summary=(
                effective_conversation.previous_answer_summary if effective_conversation else ""
            ),
            conversation=effective_conversation,
        )
        return PreparedCopilotRequest(
            normalized_question=normalized_question,
            asset_id=effective_asset_id,
            conversation=effective_conversation,
            pre_analysis=pre_analysis,
            analysis=analysis,
            asset_context=asset_context,
            filters=filters,
            relaxable_filters=relaxable_filters,
            applicability=applicability,
            retrieval_query=retrieval_query,
        )

    def _early(
        self,
        normalized_question: str,
        asset_id: str | None,
        conversation: ConversationContext | None,
        status: str,
        *,
        pre_analysis: QueryAnalysis | None = None,
    ) -> PreparedCopilotRequest:
        return PreparedCopilotRequest(
            normalized_question=normalized_question,
            asset_id=asset_id,
            conversation=conversation,
            pre_analysis=pre_analysis,
            analysis=None,
            asset_context=None,
            filters={},
            relaxable_filters=frozenset(),
            applicability=None,
            retrieval_query=None,
            early_status=status,
        )

    @staticmethod
    def _validate_question(question: str) -> None:
        if not question:
            raise ValueError("Câu hỏi không được để trống.")
        if len(question) > MAX_QUESTION_LENGTH:
            raise ValueError(f"Câu hỏi không được dài quá {MAX_QUESTION_LENGTH} ký tự.")

    def _load_asset_context(self, asset_id: str | None) -> dict[str, Any] | None:
        if not asset_id:
            return None
        return self.asset_context_provider.get_asset_context(asset_id)

    def _recent_ticket_context(self, asset_id: str | None) -> list[str]:
        if not asset_id:
            return []
        list_tickets = getattr(self.asset_context_provider, "list_tickets", None)
        if list_tickets is None:
            return []
        tickets = list_tickets(asset_id=asset_id, limit=3)
        context: list[str] = []
        for ticket in tickets:
            category = str(ticket.get("failure_category") or "").strip()
            description = str(ticket.get("issue_description") or "").strip()
            value = " - ".join(part for part in [category, description] if part)
            if value:
                context.append(value)
        return context

    @staticmethod
    def _asset_type_from_context(asset_context: dict[str, Any] | None) -> str | None:
        if not asset_context:
            return None
        latest_risk = asset_context.get("latest_risk") or {}
        asset_type = latest_risk.get("asset_type")
        return str(asset_type) if asset_type else None

    @staticmethod
    def _clean_filters(
        *,
        asset_type: str | None,
        document_type: str | None,
        failure_category: str | None,
        version: str | None = None,
        language: str | None = None,
    ) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "asset_type": asset_type,
                "document_type": document_type,
                "failure_category": failure_category,
                "version": version,
                "language": language,
            }.items()
            if value
        }

    @staticmethod
    def _build_retrieval_query(
        question: str,
        ticket_context: list[str],
        *,
        previous_answer_summary: str = "",
        conversation: ConversationContext | None = None,
    ) -> str:
        supporting: list[str] = [question]
        if conversation:
            if conversation.resolved_asset_type:
                supporting.append(f"Loại thiết bị lượt trước: {conversation.resolved_asset_type}")
            if conversation.resolved_failure_category:
                supporting.append(
                    f"Nhóm sự cố lượt trước: {conversation.resolved_failure_category}"
                )
            if conversation.recent_intent:
                supporting.append(f"Ý định lượt trước: {conversation.recent_intent}")
        if previous_answer_summary:
            supporting.append(f"Tóm tắt lượt trước: {previous_answer_summary[:600]}")
        if ticket_context:
            supporting.append(f"Ngữ cảnh ticket tham khảo: {' | '.join(ticket_context)[:600]}")
        return "\n".join(supporting)
