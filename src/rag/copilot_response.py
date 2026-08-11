"""Compatible Copilot response models, rendering, and source serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.config.settings import get_settings
from src.llm.models import CitedStatement, GroundedLLMAnswer
from src.llm.prompt_builder import PromptSource, retrieval_alias_key
from src.rag.retriever import RetrievalResult

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
    response_mode: str = "deterministic_fallback"
    fallback_reason: str | None = None
    structured_answer: dict[str, Any] | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    evidence_status: str = "insufficient"
    citation_validation: dict[str, Any] | None = None
    context_warnings: list[str] = field(default_factory=list)
    confidence: str = "insufficient_evidence"
    conversation_state: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

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
            "response_mode": self.response_mode,
            "fallback_reason": self.fallback_reason,
            "structured_answer": self.structured_answer,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "evidence_status": self.evidence_status,
            "citation_validation": self.citation_validation,
            "context_warnings": self.context_warnings,
            "confidence": self.confidence,
            "conversation_state": self.conversation_state,
            "diagnostics": self.diagnostics,
        }


def compose_answer(
    question: str,
    asset_id: str | None,
    asset_context: dict[str, Any] | None,
    retrievals: list[RetrievalResult],
    citation_ids: dict[str, str] | None = None,
) -> str:
    """Compose a deterministic Vietnamese answer without an external LLM."""

    lines = ["### Tóm tắt tình trạng thiết bị", f"Câu hỏi: {question}"]
    if asset_context:
        latest_risk = asset_context.get("latest_risk") or {}
        lines.extend(
            _format_structured_context(asset_id or asset_context.get("asset_id"), latest_risk)
        )
        lines.extend(_format_recent_anomalies(asset_context.get("recent_anomalies") or []))
        lines.append(
            "Ngữ cảnh analytics chỉ là tín hiệu hỗ trợ ưu tiên và không phải chẩn đoán "
            "hoặc nguồn cho bước kỹ thuật."
        )
    else:
        lines.append("Không có asset_id; phần tóm tắt chỉ sử dụng phạm vi nêu trong câu hỏi.")

    lines.append("### Checklist hoặc bước kiểm tra được tìm thấy")
    local_citations = citation_ids or citation_map(retrievals)
    lines.extend(
        f"- {action} {_citation_suffix([local_citations[key]])}"
        for action, key in _extract_actions(retrievals)
        if key in local_citations
    )
    lines.append("### Nguồn tài liệu")
    for source in deduplicate_sources(retrievals, local_citations):
        source_suffix = _citation_suffix(source.get("citation_ids", []))
        lines.append(
            f"- {source['title']} ({source['document_type']}, phiên bản "
            f"{source['version']}, hiệu lực {source['effective_date']}) {source_suffix}"
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


def compose_llm_answer(answer: GroundedLLMAnswer) -> str:
    """Render validated structured output into the compatible Markdown answer field."""

    lines = [
        "### Tóm tắt tình trạng thiết bị",
        f"{answer.summary} {_citation_suffix(answer.summary_source_ids)}",
    ]
    if answer.possible_causes:
        lines.append("### Nguyên nhân có thể")
        lines.extend(_render_cited_items(answer.possible_causes))
    lines.append("### Checklist hoặc bước kiểm tra được đề xuất")
    lines.extend(_render_cited_items(answer.recommended_checks, ordered=True))
    if answer.safety_warnings:
        lines.append("### Cảnh báo an toàn từ nguồn")
        lines.extend(_render_cited_items(answer.safety_warnings))
    lines.extend(
        [
            "### Chuyển cấp",
            (
                "Cần chuyển cấp cho kỹ thuật trưởng hoặc người có thẩm quyền."
                if answer.escalation_required
                else "Chưa có căn cứ bắt buộc chuyển cấp; người có thẩm quyền vẫn phải xác minh."
            ),
            "### Giới hạn của khuyến nghị",
            RECOMMENDATION_LIMIT,
        ]
    )
    return "\n".join(lines)


def deterministic_retrieval_response(
    *,
    question: str,
    asset_id: str | None,
    asset_context: dict[str, Any] | None,
    retrievals: list[RetrievalResult],
    filters: dict[str, str],
    fallback_reason: str,
    context_warnings: list[str],
    citation_validation: dict[str, Any] | None = None,
) -> CopilotAnswer:
    citation_ids = citation_map(retrievals)
    return CopilotAnswer(
        answer=compose_answer(
            question,
            asset_id,
            asset_context,
            retrievals,
            citation_ids,
        ),
        asset_context=asset_context,
        sources=deduplicate_sources(retrievals, citation_ids),
        retrieved_chunks=retrieved_chunk_payloads(retrievals, citation_ids),
        retrieval_status="success",
        relevance_status="relevant",
        filters_applied=filters,
        response_mode="deterministic_fallback",
        fallback_reason=fallback_reason,
        evidence_status="limited",
        citation_validation=citation_validation,
        context_warnings=context_warnings,
        confidence="low",
    )


def insufficient_generation_response(
    *,
    question: str,
    asset_context: dict[str, Any] | None,
    prompt_sources: list[PromptSource],
    filters: dict[str, str],
    provider: str,
    model: str,
    citation_validation: dict[str, Any],
    context_warnings: list[str],
) -> CopilotAnswer:
    retrievals = [source.retrieval for source in prompt_sources]
    citation_ids = {
        retrieval_alias_key(source.retrieval): source.citation_id for source in prompt_sources
    }
    lines = [
        "### Tóm tắt tình trạng thiết bị",
        f"Câu hỏi: {question}",
        "Bằng chứng truy xuất hiện có chưa đủ để tạo hướng dẫn kỹ thuật có căn cứ.",
        "### Checklist hoặc bước kiểm tra được đề xuất",
        SAFE_FALLBACK,
        "### Chuyển cấp",
        "Cần chuyển cấp cho kỹ thuật trưởng hoặc người có thẩm quyền để xác minh tại hiện trường.",
        "### Giới hạn của khuyến nghị",
        RECOMMENDATION_LIMIT,
    ]
    return CopilotAnswer(
        answer="\n".join(lines),
        asset_context=asset_context,
        sources=deduplicate_sources(retrievals, citation_ids),
        retrieved_chunks=retrieved_chunk_payloads(retrievals, citation_ids),
        retrieval_status="success",
        relevance_status="not_relevant",
        filters_applied=filters,
        response_mode="deterministic_fallback",
        fallback_reason="llm_insufficient_evidence",
        llm_provider=provider,
        llm_model=model,
        evidence_status="insufficient",
        citation_validation=citation_validation,
        context_warnings=context_warnings,
        confidence="insufficient_evidence",
    )


def fallback_response(
    *,
    question: str,
    asset_id: str | None,
    asset_context: dict[str, Any] | None,
    retrieval_status: str,
    filters: dict[str, str],
    fallback_reason: str | None = None,
    context_warnings: list[str] | None = None,
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
        "asset_context_mismatch": (
            "Loại thiết bị trong câu hỏi không khớp thiết bị đã chọn. "
            "Hãy xác nhận lại thiết bị hoặc loại thiết bị cần tra cứu."
        ),
        "model_context_mismatch": (
            "Mã model trong câu hỏi hoặc tài liệu không khớp model của thiết bị đã chọn. "
            "Copilot không sử dụng bằng chứng khác model; hãy xác nhận nhãn máy và tài liệu áp dụng."
        ),
        "parameter_confirmation_required": (
            "Yêu cầu thông số kỹ thuật chính xác còn thiếu điều kiện áp dụng cần thiết. "
            "Copilot không suy đoán mô-men, cấp dầu hoặc thông số an toàn; hãy xác nhận "
            "nhãn máy, kích thước và đúng manual với người có thẩm quyền."
        ),
        "prompt_injection": (
            "Câu hỏi chứa chỉ thị cố gắng thay đổi quy tắc hoặc truy xuất cấu hình nội bộ."
        ),
        "unsafe_operation": (
            "Copilot chỉ hỗ trợ tra cứu đọc. Yêu cầu thực thi lệnh, thay đổi bản ghi hoặc "
            "điều khiển thiết bị đã bị từ chối."
        ),
        "unsafe_conversation": (
            "Ngữ cảnh lượt trước chứa chỉ thị không an toàn và không được sử dụng."
        ),
        "unsafe_context": "Tài liệu truy xuất chứa chỉ thị không an toàn và đã bị loại bỏ.",
        "insufficient_evidence": "Số tài liệu liên quan chưa đạt ngưỡng bằng chứng tối thiểu.",
        "unavailable": "Dịch vụ truy xuất tài liệu hiện chưa sẵn sàng.",
        "empty": "Không có chunk phù hợp với bộ lọc hiện tại.",
        "low_relevance": "Các chunk tìm được không đạt ngưỡng relevance đã cấu hình.",
        "conflicting_evidence": (
            "Các tài liệu truy xuất chứa chỉ dẫn đối nghịch đáng kể; Copilot không chọn "
            "một hướng dẫn thay cho người có thẩm quyền."
        ),
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
        response_mode="deterministic_fallback",
        fallback_reason=fallback_reason or retrieval_status,
        evidence_status="insufficient",
        context_warnings=context_warnings or [],
        confidence="insufficient_evidence",
    )


def conversation_fallback(
    *,
    question: str,
    intent: str,
    reason: str,
) -> CopilotAnswer:
    """Return a concise local response when the social LLM path is unavailable."""

    answers = {
        "greeting": (
            "Xin chào! Tôi là Trợ lý bảo trì AI. "
            "Bạn có thể hỏi tôi về HVAC, máy bơm hoặc máy phát điện."
        ),
        "identity": (
            "Tôi là Trợ lý bảo trì AI, hỗ trợ tra cứu SOP, checklist và thông tin ưu tiên "
            "cho HVAC, máy bơm và máy phát điện. Tôi không tự điều khiển thiết bị hoặc thay đổi hồ sơ."
        ),
        "capabilities": (
            "Tôi có thể giúp tra cứu tài liệu bảo trì, gợi ý bước kiểm tra có nguồn và đối chiếu "
            "ngữ cảnh thiết bị. Hãy chọn thiết bị hoặc nêu rõ loại HVAC, máy bơm hay máy phát điện."
        ),
        "courtesy": "Rất vui được hỗ trợ. Khi cần, bạn hãy gửi câu hỏi bảo trì cụ thể.",
    }
    return CopilotAnswer(
        answer=answers.get(intent, answers["identity"]),
        asset_context=None,
        sources=[],
        retrieved_chunks=[],
        retrieval_status="conversation",
        relevance_status="not_applicable",
        safety_notice="",
        response_mode="deterministic_fallback",
        fallback_reason=reason,
        evidence_status="not_applicable",
        confidence="not_applicable",
    )


def deduplicate_sources(
    retrievals: list[RetrievalResult],
    citation_ids: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    source_indexes: dict[str, int] = {}
    for result in retrievals:
        key = result.doc_id or result.source or result.title
        citation_id = (citation_ids or {}).get(retrieval_alias_key(result))
        if key in source_indexes:
            if citation_id:
                existing = sources[source_indexes[key]]["citation_ids"]
                if citation_id not in existing:
                    existing.append(citation_id)
            continue
        source_indexes[key] = len(sources)
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
                "citation_ids": [citation_id] if citation_id else [],
            }
        )
    return sources


def retrieved_chunk_payloads(
    retrievals: list[RetrievalResult],
    citation_ids: dict[str, str],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for result in retrievals:
        payload = result.to_dict(include_diagnostics=get_settings().rag_debug_enabled)
        payload["citation_id"] = citation_ids.get(retrieval_alias_key(result))
        payloads.append(payload)
    return payloads


def citation_map(retrievals: list[RetrievalResult]) -> dict[str, str]:
    return {
        retrieval_alias_key(result): f"S{index}" for index, result in enumerate(retrievals, start=1)
    }


def _render_cited_items(
    items: list[CitedStatement],
    *,
    ordered: bool = False,
) -> list[str]:
    rendered: list[str] = []
    for index, item in enumerate(items, start=1):
        prefix = f"{index}." if ordered else "-"
        rendered.append(f"{prefix} {item.text} {_citation_suffix(item.source_ids)}")
    return rendered


def _citation_suffix(source_ids: list[str]) -> str:
    return " ".join(f"[{source_id}]" for source_id in source_ids)


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


def _extract_actions(
    retrievals: list[RetrievalResult],
    limit: int = 6,
) -> list[tuple[str, str]]:
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
    actions: list[tuple[str, str]] = []
    seen_actions: set[str] = set()
    for retrieval in retrievals:
        key = retrieval_alias_key(retrieval)
        for sentence in _split_sentences(retrieval.text):
            if sentence.endswith(":"):
                continue
            if any(keyword in sentence.casefold() for keyword in keywords):
                action = sentence.strip()
                if action and action not in seen_actions:
                    actions.append((action, key))
                    seen_actions.add(action)
            if len(actions) >= limit:
                return actions
    return actions or [
        (retrieval.text, retrieval_alias_key(retrieval)) for retrieval in retrievals[:limit]
    ]


def _split_sentences(text: str) -> list[str]:
    fragments: list[str] = []
    for line in text.splitlines():
        for fragment in line.replace(";", ".").split("."):
            cleaned = fragment.strip(" -\n\t")
            if cleaned and not cleaned.isdigit():
                fragments.append(cleaned)
    return fragments
