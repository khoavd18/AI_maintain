"""Conservative deterministic evidence-quality gates."""

from __future__ import annotations

from src.rag.retriever import RetrievalResult

_CONTRADICTION_PAIRS = (
    ("được phép vận hành", "không được phép vận hành"),
    ("tiếp tục vận hành", "dừng thiết bị"),
    ("có thể khởi động", "không được khởi động"),
    ("có thể tháo", "không được tháo"),
    ("safe to operate", "do not operate"),
)


def has_significant_conflict(retrievals: list[RetrievalResult]) -> bool:
    """Flag only explicit opposed directives found in different retrieved documents."""

    by_document: dict[str, str] = {}
    for result in retrievals:
        document_key = result.doc_id or result.source or result.title
        by_document[document_key] = f"{by_document.get(document_key, '')} {result.text}".casefold()
    if len(by_document) < 2:
        return False
    documents = list(by_document.items())
    for index, (_, first_text) in enumerate(documents):
        for _, second_text in documents[index + 1 :]:
            for positive, negative in _CONTRADICTION_PAIRS:
                if (positive in first_text and negative in second_text) or (
                    negative in first_text and positive in second_text
                ):
                    return True
    return False
