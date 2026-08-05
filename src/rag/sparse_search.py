"""Bounded in-memory BM25 retrieval for the controlled maintenance corpus."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import re
from threading import Lock
import unicodedata

from src.rag.retriever import RetrievalResult
from src.rag.vector_store import QdrantVectorStore, VectorSearchResult

_TOKEN_PATTERN = re.compile(r"[\w]+(?:[-_.][\w]+)*", flags=re.UNICODE)


@dataclass(frozen=True)
class _IndexedDocument:
    result: RetrievalResult
    term_frequencies: Counter[str]
    length: int


class BM25Index:
    """Pre-tokenized BM25 index suitable for a bounded, small SOP corpus."""

    def __init__(
        self,
        documents: list[RetrievalResult],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("BM25 requires k1 > 0 and 0 <= b <= 1.")
        self.k1 = k1
        self.b = b
        self._documents = [self._index_document(document) for document in documents]
        self._average_length = (
            sum(document.length for document in self._documents) / len(self._documents)
            if self._documents
            else 1.0
        )
        document_frequency: Counter[str] = Counter()
        for document in self._documents:
            document_frequency.update(document.term_frequencies.keys())
        corpus_size = len(self._documents)
        self._inverse_document_frequency = {
            term: math.log(1.0 + (corpus_size - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def search(
        self,
        query: str,
        *,
        limit: int,
        asset_type: str | None = None,
        document_type: str | None = None,
        failure_category: str | None = None,
        version: str | None = None,
        language: str | None = None,
    ) -> list[RetrievalResult]:
        """Return positive BM25 matches under conjunctive metadata filters."""

        if limit <= 0:
            raise ValueError("limit must be positive.")
        query_terms = list(dict.fromkeys(tokenize(query)))
        if not query_terms:
            return []
        scored: list[tuple[float, RetrievalResult]] = []
        for document in self._documents:
            if not _matches_filters(
                document.result,
                asset_type=asset_type,
                document_type=document_type,
                failure_category=failure_category,
                version=version,
                language=language,
            ):
                continue
            score = self._score(document, query_terms)
            if score > 0:
                scored.append((score, document.result))
        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return [_copy_with_score(result, score) for score, result in scored[:limit]]

    def _score(self, document: _IndexedDocument, query_terms: list[str]) -> float:
        score = 0.0
        length_ratio = document.length / self._average_length
        for term in query_terms:
            frequency = document.term_frequencies.get(term, 0)
            if not frequency:
                continue
            denominator = frequency + self.k1 * (1.0 - self.b + self.b * length_ratio)
            score += self._inverse_document_frequency.get(term, 0.0) * (
                frequency * (self.k1 + 1.0) / denominator
            )
        return score

    @staticmethod
    def _index_document(document: RetrievalResult) -> _IndexedDocument:
        tokens = tokenize(
            " ".join(
                (
                    document.doc_id,
                    document.title,
                    document.asset_type,
                    document.failure_category,
                    document.text,
                )
            )
        )
        return _IndexedDocument(
            result=document,
            term_frequencies=Counter(tokens),
            length=max(1, len(tokens)),
        )


class QdrantBM25Retriever:
    """Lazily materialize one bounded BM25 index from Qdrant payloads per process."""

    def __init__(self, vector_store: QdrantVectorStore, *, max_chunks: int = 10000) -> None:
        self.vector_store = vector_store
        self.max_chunks = max_chunks
        self._index: BM25Index | None = None
        self._lock = Lock()

    def search(self, query: str, *, limit: int, **filters: str | None) -> list[RetrievalResult]:
        return self._get_index().search(query, limit=limit, **filters)

    def refresh(self) -> None:
        """Invalidate cached sparse state after an explicit indexing operation."""

        with self._lock:
            self._index = None

    def _get_index(self) -> BM25Index:
        if self._index is None:
            with self._lock:
                if self._index is None:
                    payloads = self.vector_store.list_chunks(max_chunks=self.max_chunks)
                    self._index = BM25Index([_from_vector_result(item) for item in payloads])
        return self._index


def tokenize(text: str) -> list[str]:
    """Tokenize Vietnamese text and preserve exact equipment identifiers."""

    normalized = unicodedata.normalize("NFC", text).casefold()
    return [match.group(0) for match in _TOKEN_PATTERN.finditer(normalized)]


def _matches_filters(
    result: RetrievalResult,
    *,
    asset_type: str | None,
    document_type: str | None,
    failure_category: str | None,
    version: str | None,
    language: str | None,
) -> bool:
    expected = {
        "asset_type": asset_type,
        "doc_type": document_type,
        "failure_category": failure_category,
        "version": version,
        "language": language,
    }
    return all(
        value is None or getattr(result, field) == value for field, value in expected.items()
    )


def _from_vector_result(result: VectorSearchResult) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=result.chunk_id,
        doc_id=result.doc_id,
        title=result.title,
        doc_type=result.doc_type,
        asset_type=result.asset_type,
        source=result.source,
        text=result.text,
        score=0.0,
        failure_category=result.failure_category,
        version=result.version,
        effective_date=result.effective_date,
        language=result.language,
        chunk_index=result.chunk_index,
    )


def _copy_with_score(result: RetrievalResult, score: float) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=result.chunk_id,
        doc_id=result.doc_id,
        title=result.title,
        doc_type=result.doc_type,
        asset_type=result.asset_type,
        source=result.source,
        text=result.text,
        score=score,
        failure_category=result.failure_category,
        version=result.version,
        effective_date=result.effective_date,
        language=result.language,
        chunk_index=result.chunk_index,
        sparse_score=score,
    )
