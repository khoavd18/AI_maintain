"""Deterministic Vietnamese Maintenance Copilot service."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from src.api.services import ProcessedDataService, get_processed_data_service
from src.config.settings import get_settings
from src.config.value_mappings import (
    ASSET_TYPE_CODE_TO_VI,
    DOCUMENT_TYPE_CODE_TO_VI,
    FAILURE_TYPE_CODE_TO_VI,
)
from src.rag.embeddings import EmbeddingDependencyError, create_embedding_provider
from src.rag.retriever import (
    QdrantRetriever,
    RetrievalResult,
    RetrievalUnavailableError,
    Retriever,
    SEMANTIC_RELEVANCE_THRESHOLD,
    UnavailableRetriever,
)
from src.rag.vector_store import QdrantVectorStore, VectorStoreError

MAX_QUESTION_LENGTH = 1000
FOCUSED_ASSET_TYPES = {
    ASSET_TYPE_CODE_TO_VI["hvac"],
    ASSET_TYPE_CODE_TO_VI["pump"],
    ASSET_TYPE_CODE_TO_VI["generator"],
}
SAFE_FALLBACK = (
    "Không tìm thấy SOP hoặc checklist đủ liên quan trong kho tài liệu hiện có. "
    "Vui lòng kiểm tra tài liệu của nhà sản xuất hoặc liên hệ kỹ thuật trưởng."
)
SAFETY_NOTICE = (
    "Đây là công cụ hỗ trợ quyết định. Kỹ thuật viên phải xác minh thiết bị tại hiện trường, "
    "tuân thủ PPE và quy trình cô lập năng lượng của tòa nhà. Hướng dẫn của nhà sản xuất và "
    "quy định an toàn của tòa nhà luôn được ưu tiên."
)
RECOMMENDATION_LIMIT = (
    "Anomaly và Risk Score chỉ là tín hiệu ưu tiên, không chứng minh thiết bị đã hỏng và không "
    "phải chẩn đoán tự động hay dự đoán chính xác thời điểm hỏng. Mọi hành động cuối cùng thuộc "
    "trách nhiệm của manager và technician có thẩm quyền."
)


@dataclass(frozen=True)
class CopilotAnswer:
    """Structured, backward-compatible Copilot response."""

    answer: str
    asset_context: dict[str, Any] | None
    sources: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    retrieval_status: str = "relevant"
    relevance_status: str = "relevant"
    safety_notice: str = SAFETY_NOTICE
    filters_applied: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return an API-safe response dictionary with additive status fields."""

        return {
            "answer": self.answer,
            "asset_context": self.asset_context,
            "sources": self.sources,
            "retrieved_chunks": self.retrieved_chunks,
            "retrieval_status": self.retrieval_status,
            "relevance_status": self.relevance_status,
            "safety_notice": self.safety_notice,
            "filters_applied": self.filters_applied,
        }


class MaintenanceCopilot:
    """Answer focused technician questions using asset facts and retrieved guidance."""

    def __init__(
        self,
        processed_data_service: ProcessedDataService,
        retriever: Retriever,
    ) -> None:
        self.processed_data_service = processed_data_service
        self.retriever = retriever

    def ask(
        self,
        question: str,
        asset_id: str | None = None,
        top_k: int = 5,
        document_type: str | None = None,
        failure_category: str | None = None,
    ) -> CopilotAnswer:
        """Answer a maintenance question with explicit relevance and fallback policy."""

        normalized_question = " ".join(question.split())
        _validate_question(normalized_question)
        asset_context = self._load_asset_context(asset_id)
        selected_asset_type = _asset_type_from_context(asset_context)
        question_asset_type = _infer_asset_type(normalized_question)

        scope_status = _question_scope_status(
            normalized_question,
            selected_asset_type=selected_asset_type,
            question_asset_type=question_asset_type,
        )
        asset_type_filter = question_asset_type or selected_asset_type
        filters = _clean_filters(
            asset_type=asset_type_filter,
            document_type=_normalize_document_type(document_type)
            or _infer_document_type(normalized_question),
            failure_category=_normalize_failure_category(failure_category)
            or _infer_failure_category(normalized_question),
        )
        if scope_status != "supported":
            return _fallback_response(
                question=normalized_question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrieval_status=scope_status,
                filters=filters,
            )

        retrieval_query = _build_retrieval_query(
            normalized_question,
            self._recent_ticket_context(asset_id),
        )
        try:
            optional_filters = {
                key: filters[key]
                for key in ["document_type", "failure_category"]
                if key in filters
            }
            retrievals = self.retriever.search(
                retrieval_query,
                limit=top_k,
                asset_type=filters.get("asset_type"),
                **optional_filters,
            )
        except (RetrievalUnavailableError, VectorStoreError, EmbeddingDependencyError):
            return _fallback_response(
                question=normalized_question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrieval_status="unavailable",
                filters=filters,
            )

        if not retrievals:
            return _fallback_response(
                question=normalized_question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrieval_status="empty",
                filters=filters,
            )

        threshold = float(
            getattr(self.retriever, "minimum_relevance_score", SEMANTIC_RELEVANCE_THRESHOLD)
        )
        relevant = [result for result in retrievals if result.score >= threshold]
        if not relevant:
            return _fallback_response(
                question=normalized_question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrieval_status="low_relevance",
                filters=filters,
            )

        sources = _deduplicate_sources(relevant)
        return CopilotAnswer(
            answer=compose_answer(
                question=normalized_question,
                asset_id=asset_id,
                asset_context=asset_context,
                retrievals=relevant,
            ),
            asset_context=asset_context,
            sources=sources,
            retrieved_chunks=[result.to_dict() for result in relevant],
            retrieval_status="success",
            relevance_status="relevant",
            filters_applied=filters,
        )

    def _load_asset_context(self, asset_id: str | None) -> dict[str, Any] | None:
        if not asset_id:
            return None
        return self.processed_data_service.get_asset_context(asset_id)

    def _recent_ticket_context(self, asset_id: str | None) -> list[str]:
        if not asset_id or not hasattr(self.processed_data_service, "list_tickets"):
            return []
        tickets = self.processed_data_service.list_tickets(asset_id=asset_id, limit=3)
        context: list[str] = []
        for ticket in tickets:
            category = str(ticket.get("failure_category") or "").strip()
            description = str(ticket.get("issue_description") or "").strip()
            value = " - ".join(part for part in [category, description] if part)
            if value:
                context.append(value)
        return context


def compose_answer(
    question: str,
    asset_id: str | None,
    asset_context: dict[str, Any] | None,
    retrievals: list[RetrievalResult],
) -> str:
    """Compose a deterministic Vietnamese answer without an external LLM."""

    lines = ["### Tóm tắt tình trạng thiết bị", f"Câu hỏi: {question}"]
    if asset_context:
        latest_risk = asset_context.get("latest_risk") or {}
        lines.extend(_format_structured_context(asset_id or asset_context.get("asset_id"), latest_risk))
        lines.extend(_format_recent_anomalies(asset_context.get("recent_anomalies") or []))
        recommendation = asset_context.get("latest_recommendation")
        if recommendation:
            lines.append(f"Khuyến nghị từ analytics: {recommendation}")
    else:
        lines.append("Không có asset_id; phần tóm tắt chỉ sử dụng phạm vi nêu trong câu hỏi.")

    lines.append("### Checklist hoặc bước kiểm tra được tìm thấy")
    lines.extend(f"- {action}" for action in _extract_actions(retrievals))
    lines.append("### Nguồn tài liệu")
    for source in _deduplicate_sources(retrievals):
        lines.append(
            f"- {source['title']} ({source['document_type']}, phiên bản "
            f"{source['version']}, hiệu lực {source['effective_date']})"
        )
    lines.extend(
        [
            "### Lưu ý an toàn",
            SAFETY_NOTICE,
            "### Giới hạn của khuyến nghị",
            RECOMMENDATION_LIMIT,
        ]
    )
    return "\n".join(lines)


@lru_cache(maxsize=1)
def get_copilot_service() -> MaintenanceCopilot:
    """Create the default Copilot while isolating optional RAG initialization."""

    settings = get_settings()
    try:
        embedding_provider = create_embedding_provider(settings.embedding_model_name)
    except EmbeddingDependencyError:
        retriever: Retriever = UnavailableRetriever()
    else:
        vector_store = QdrantVectorStore(
            url=settings.qdrant_url,
            collection_name=settings.qdrant_collection,
        )
        retriever = QdrantRetriever(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )
    return MaintenanceCopilot(
        processed_data_service=get_processed_data_service(),
        retriever=retriever,
    )


def _fallback_response(
    *,
    question: str,
    asset_id: str | None,
    asset_context: dict[str, Any] | None,
    retrieval_status: str,
    filters: dict[str, str],
) -> CopilotAnswer:
    lines = ["### Tóm tắt tình trạng thiết bị", f"Câu hỏi: {question}"]
    if asset_context:
        lines.extend(
            _format_structured_context(
                asset_id or asset_context.get("asset_id"),
                asset_context.get("latest_risk") or {},
            )
        )
    elif asset_id:
        lines.append(f"Không có ngữ cảnh sử dụng được cho thiết bị {asset_id}.")
    else:
        lines.append("Chưa có thiết bị thuộc phạm vi HVAC, pump hoặc generator để đối chiếu.")

    reason = {
        "unrelated": "Câu hỏi không thuộc phạm vi tra cứu bảo trì của Copilot.",
        "unsupported_asset_type": "Câu hỏi nằm ngoài ba loại thiết bị của MVP.",
        "missing_asset_context": "Cần chọn thiết bị hoặc nêu rõ HVAC, pump hay generator.",
        "unavailable": "Dịch vụ truy xuất tài liệu hiện chưa sẵn sàng.",
        "empty": "Không có chunk phù hợp với bộ lọc hiện tại.",
        "low_relevance": "Các chunk tìm được không đạt ngưỡng relevance đã cấu hình.",
    }.get(retrieval_status, "Không có hướng dẫn đủ căn cứ để trả lời.")
    lines.extend(
        [
            "### Checklist hoặc bước kiểm tra được tìm thấy",
            reason,
            SAFE_FALLBACK,
            "### Nguồn tài liệu",
            "Không có nguồn tài liệu đủ liên quan để trích dẫn.",
            "### Lưu ý an toàn",
            SAFETY_NOTICE,
            "### Giới hạn của khuyến nghị",
            RECOMMENDATION_LIMIT,
        ]
    )
    return CopilotAnswer(
        answer="\n".join(lines),
        asset_context=asset_context,
        sources=[],
        retrieved_chunks=[],
        retrieval_status=retrieval_status,
        relevance_status="not_relevant",
        filters_applied=filters,
    )


def _format_structured_context(asset_id: object, latest_risk: dict[str, Any]) -> list[str]:
    if not latest_risk:
        return ["Không có dòng rủi ro mới nhất cho thiết bị này."]

    lines = [
        (
            f"Thiết bị {asset_id}: {latest_risk.get('asset_name')}, loại "
            f"{latest_risk.get('asset_type')}, vị trí {latest_risk.get('location')}. "
            f"Điểm rủi ro hiện tại {latest_risk.get('final_risk_score')}, mức "
            f"{latest_risk.get('risk_level')}."
        )
    ]
    reasons = latest_risk.get("main_reasons")
    if reasons:
        lines.append(f"Lý do rủi ro chính: {reasons}")
    return lines


def _format_recent_anomalies(anomalies: list[dict[str, Any]]) -> list[str]:
    anomalous = [record for record in anomalies if record.get("is_anomaly")]
    if not anomalous:
        return ["Không có bất thường gần đây được đánh dấu trong ngữ cảnh thiết bị."]

    lines = ["Bất thường gần đây:"]
    for record in anomalous[:3]:
        lines.append(
            "- "
            f"{record.get('date')}: {record.get('anomaly_type')} "
            f"(điểm {record.get('anomaly_score')}) - {record.get('anomaly_reasons')}"
        )
    return lines


def _extract_actions(retrievals: list[RetrievalResult], limit: int = 6) -> list[str]:
    keywords = [
        "kiểm tra",
        "quan sát",
        "ghi nhận",
        "xác nhận",
        "đối chiếu",
        "liên hệ",
        "dừng",
        "chuyển cấp",
    ]
    actions: list[str] = []
    for retrieval in retrievals:
        for sentence in _split_sentences(retrieval.text):
            if sentence.endswith(":"):
                continue
            if any(keyword in sentence.casefold() for keyword in keywords):
                action = sentence.strip()
                if action and action not in actions:
                    actions.append(action)
            if len(actions) >= limit:
                return actions
    return actions or [retrieval.text for retrieval in retrievals[:limit]]


def _split_sentences(text: str) -> list[str]:
    fragments: list[str] = []
    for line in text.splitlines():
        for fragment in line.replace(";", ".").split("."):
            cleaned = fragment.strip(" -\n\t")
            if cleaned and not cleaned.isdigit():
                fragments.append(cleaned)
    return fragments


def _deduplicate_sources(retrievals: list[RetrievalResult]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in retrievals:
        key = result.doc_id or result.source or result.title
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "doc_id": result.doc_id,
                "document_id": result.doc_id,
                "title": result.title,
                "doc_type": result.doc_type,
                "document_type": result.doc_type,
                "asset_type": result.asset_type,
                "failure_category": result.failure_category,
                "version": result.version,
                "effective_date": result.effective_date,
                "source": result.source,
                "score": result.score,
            }
        )
    return sources


def _asset_type_from_context(asset_context: dict[str, Any] | None) -> str | None:
    if not asset_context:
        return None
    latest_risk = asset_context.get("latest_risk") or {}
    asset_type = latest_risk.get("asset_type")
    return str(asset_type) if asset_type else None


def _validate_question(question: str) -> None:
    if not question:
        raise ValueError("Câu hỏi không được để trống.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise ValueError(f"Câu hỏi không được dài quá {MAX_QUESTION_LENGTH} ký tự.")


def _question_scope_status(
    question: str,
    *,
    selected_asset_type: str | None,
    question_asset_type: str | None,
) -> str:
    normalized = question.casefold()
    unsupported_terms = [
        "thang máy",
        "elevator",
        "tủ điện",
        "báo cháy",
        "bồn nước",
        "chiếu sáng",
        "xe máy",
        "ô tô",
    ]
    if any(term in normalized for term in unsupported_terms) and not question_asset_type:
        return "unsupported_asset_type"
    if selected_asset_type and selected_asset_type not in FOCUSED_ASSET_TYPES:
        return "unsupported_asset_type"

    maintenance_terms = [
        "bảo trì",
        "kiểm tra",
        "sop",
        "checklist",
        "rủi ro",
        "bất thường",
        "rung",
        "ồn",
        "khởi động",
        "làm mát",
        "sự cố",
        "hỏng",
    ]
    if not any(term in normalized for term in maintenance_terms):
        return "unrelated"
    if not selected_asset_type and not question_asset_type:
        return "missing_asset_context"
    return "supported"


def _infer_asset_type(question: str) -> str | None:
    normalized = question.casefold()
    aliases = {
        ASSET_TYPE_CODE_TO_VI["hvac"]: ["hvac", "máy lạnh", "điều hòa", "điều hoà"],
        ASSET_TYPE_CODE_TO_VI["pump"]: ["pump", "máy bơm", "bơm nước"],
        ASSET_TYPE_CODE_TO_VI["generator"]: [
            "generator",
            "máy phát điện",
            "máy phát",
        ],
    }
    for asset_type, terms in aliases.items():
        if any(term in normalized for term in terms):
            return asset_type
    return None


def _infer_failure_category(question: str) -> str | None:
    normalized = question.casefold()
    if any(term in normalized for term in ["không làm mát", "làm lạnh", "không lạnh"]):
        return FAILURE_TYPE_CODE_TO_VI["cooling_issue"]
    if any(term in normalized for term in ["rung", "tiếng ồn", "ồn bất thường"]):
        return FAILURE_TYPE_CODE_TO_VI["vibration_issue"]
    if "không khởi động" in normalized:
        return FAILURE_TYPE_CODE_TO_VI["electrical_issue"]
    return None


def _infer_document_type(question: str) -> str | None:
    normalized = question.casefold()
    if "bảo trì định kỳ" in normalized or "kiểm tra định kỳ" in normalized:
        return DOCUMENT_TYPE_CODE_TO_VI["checklist"]
    return None


def _normalize_document_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized in DOCUMENT_TYPE_CODE_TO_VI:
        return DOCUMENT_TYPE_CODE_TO_VI[normalized]
    if normalized in DOCUMENT_TYPE_CODE_TO_VI.values():
        return normalized
    raise ValueError(f"document_type không được hỗ trợ: {value}")


def _normalize_failure_category(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized in FAILURE_TYPE_CODE_TO_VI:
        return FAILURE_TYPE_CODE_TO_VI[normalized]
    if normalized in FAILURE_TYPE_CODE_TO_VI.values():
        return normalized
    raise ValueError(f"failure_category không được hỗ trợ: {value}")


def _clean_filters(
    *,
    asset_type: str | None,
    document_type: str | None,
    failure_category: str | None,
) -> dict[str, str]:
    return {
        key: value
        for key, value in {
            "asset_type": asset_type,
            "document_type": document_type,
            "failure_category": failure_category,
        }.items()
        if value
    }


def _build_retrieval_query(question: str, ticket_context: list[str]) -> str:
    if not ticket_context:
        return question
    supporting = " | ".join(ticket_context)
    return f"{question}\nNgữ cảnh ticket tham khảo: {supporting[:600]}"
