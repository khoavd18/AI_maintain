"""Deterministic boundary between structured analytics and semantic evidence."""

from __future__ import annotations

from enum import StrEnum
import re


class QuestionRoute(StrEnum):
    STRUCTURED_ANALYTICS = "structured_analytics"
    SEMANTIC_EVIDENCE = "semantic_evidence"


_STRUCTURED_TERMS = frozenset(
    {
        "count",
        "how many",
        "average",
        "total",
        "trend",
        "rate",
        "sla",
        "breach",
        "escalated",
        "inventory",
        "consumption",
        "stock",
        "cost",
        "variance",
        "workload",
        "reliability",
        "bao nhiêu",
        "tổng",
        "trung bình",
        "chi phí",
        "tồn kho",
    }
)
_SEMANTIC_TERMS = frozenset(
    {
        "manual",
        "procedure",
        "sop",
        "instruction",
        "troubleshoot",
        "explain",
        "hướng dẫn",
        "quy trình",
        "tài liệu",
    }
)


def route_question(question: str) -> QuestionRoute:
    """Route aggregate questions to SQL and document questions to governed evidence."""

    normalized = " ".join(question.casefold().split())
    if not normalized:
        raise ValueError("Question must not be empty.")
    structured_score = sum(term in normalized for term in _STRUCTURED_TERMS)
    semantic_score = sum(term in normalized for term in _SEMANTIC_TERMS)
    if structured_score:
        return QuestionRoute.STRUCTURED_ANALYTICS
    if semantic_score or re.search(r"\b(why|how|what)\b", normalized):
        return QuestionRoute.SEMANTIC_EVIDENCE
    return QuestionRoute.SEMANTIC_EVIDENCE


__all__ = ["QuestionRoute", "route_question"]
