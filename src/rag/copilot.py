"""Deterministic Vietnamese Maintenance Copilot service."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from src.api.services import ProcessedDataService, get_processed_data_service
from src.config.settings import get_settings
from src.rag.embeddings import create_embedding_provider
from src.rag.retriever import QdrantRetriever, RetrievalResult, Retriever
from src.rag.vector_store import QdrantVectorStore


@dataclass(frozen=True)
class CopilotAnswer:
    """Structured copilot response."""

    answer: str
    asset_context: dict[str, Any] | None
    sources: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Return an API-safe response dictionary."""

        return {
            "answer": self.answer,
            "asset_context": self.asset_context,
            "sources": self.sources,
            "retrieved_chunks": self.retrieved_chunks,
        }


class MaintenanceCopilot:
    """Answer technician questions using structured context and retrieved documents."""

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
    ) -> CopilotAnswer:
        """Answer a maintenance question with grounded, deterministic context."""

        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty.")

        asset_context = self._load_asset_context(asset_id)
        asset_type = _asset_type_from_context(asset_context)
        retrievals = self.retriever.search(
            normalized_question,
            limit=top_k,
            asset_type=asset_type,
        )

        answer = compose_answer(
            question=normalized_question,
            asset_id=asset_id,
            asset_context=asset_context,
            retrievals=retrievals,
        )
        sources = _deduplicate_sources(retrievals)
        return CopilotAnswer(
            answer=answer,
            asset_context=asset_context,
            sources=sources,
            retrieved_chunks=[result.to_dict() for result in retrievals],
        )

    def _load_asset_context(self, asset_id: str | None) -> dict[str, Any] | None:
        if not asset_id:
            return None
        return self.processed_data_service.get_asset_context(asset_id)


def compose_answer(
    question: str,
    asset_id: str | None,
    asset_context: dict[str, Any] | None,
    retrievals: list[RetrievalResult],
) -> str:
    """Compose a deterministic Vietnamese answer without an external LLM."""

    lines = [
        "Tôi trả lời dựa trên dữ liệu rủi ro, bất thường gần đây và tài liệu bảo trì đã truy xuất.",
        f"Câu hỏi: {question}",
    ]

    if asset_context:
        latest_risk = asset_context.get("latest_risk") or {}
        lines.extend(_format_structured_context(asset_id or asset_context.get("asset_id"), latest_risk))
        lines.extend(_format_recent_anomalies(asset_context.get("recent_anomalies") or []))
        recommendation = asset_context.get("latest_recommendation")
        if recommendation:
            lines.append(f"Khuyến nghị hiện tại từ hệ thống: {recommendation}")
    elif asset_id:
        lines.append(
            f"Không tìm thấy ngữ cảnh có cấu trúc cho thiết bị {asset_id}; "
            "không nên kết luận nguyên nhân rủi ro nếu thiếu dữ liệu thiết bị."
        )
    else:
        lines.append(
            "Chưa có asset_id nên phần trả lời chỉ dựa trên tài liệu SOP/checklist được truy xuất."
        )

    if retrievals:
        lines.append("Hành động nên xem xét từ SOP/checklist:")
        for action in _extract_actions(retrievals):
            lines.append(f"- {action}")
        lines.append("Nguồn sử dụng:")
        for source in _deduplicate_sources(retrievals):
            lines.append(
                f"- {source['title']} ({source['doc_type']}, {source['asset_type']})"
            )
    else:
        lines.append(
            "Chưa truy xuất được SOP/checklist phù hợp từ Qdrant. "
            "Cần chạy indexing tài liệu hoặc mở rộng kho tri thức trước khi đưa ra checklist chi tiết."
        )

    return "\n".join(lines)


@lru_cache(maxsize=1)
def get_copilot_service() -> MaintenanceCopilot:
    """Create the default copilot service for FastAPI and CLI use."""

    settings = get_settings()
    embedding_provider = create_embedding_provider(settings.embedding_model_name)
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
    )
    retriever = QdrantRetriever(embedding_provider=embedding_provider, vector_store=vector_store)
    return MaintenanceCopilot(
        processed_data_service=get_processed_data_service(),
        retriever=retriever,
    )


def _format_structured_context(asset_id: object, latest_risk: dict[str, Any]) -> list[str]:
    if not latest_risk:
        return ["Không có dòng rủi ro mới nhất cho thiết bị này."]

    score = latest_risk.get("final_risk_score")
    risk_level = latest_risk.get("risk_level")
    asset_name = latest_risk.get("asset_name")
    asset_type = latest_risk.get("asset_type")
    location = latest_risk.get("location")
    reasons = latest_risk.get("main_reasons")

    lines = [
        (
            f"Thiết bị {asset_id}: {asset_name}, loại {asset_type}, vị trí {location}. "
            f"Điểm rủi ro hiện tại {score}, mức {risk_level}."
        )
    ]
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
        "vệ sinh",
        "thay",
        "ghi",
        "xác nhận",
        "hiệu chuẩn",
        "so sánh",
        "liên hệ",
        "escalate",
        "chuyển cấp",
    ]
    actions: list[str] = []
    for retrieval in retrievals:
        for sentence in _split_sentences(retrieval.text):
            sentence_lower = sentence.lower()
            if any(keyword in sentence_lower for keyword in keywords):
                action = sentence.strip()
                if action and action not in actions:
                    actions.append(action)
            if len(actions) >= limit:
                return actions

    if not actions:
        actions = [retrieval.text for retrieval in retrievals[:limit]]
    return actions[:limit]


def _split_sentences(text: str) -> list[str]:
    fragments = []
    for fragment in text.replace(";", ".").split("."):
        fragment = fragment.strip(" -\n\t")
        if fragment:
            fragments.append(fragment)
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
                "title": result.title,
                "doc_type": result.doc_type,
                "asset_type": result.asset_type,
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
