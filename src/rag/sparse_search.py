"""Bounded in-memory BM25 retrieval for the controlled maintenance corpus."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
import math
import re
from threading import Lock
import time
import unicodedata

from src.rag.retriever import RetrievalResult
from src.rag.vector_store import QdrantVectorStore, VectorSearchResult
from src.rag.text_normalization import fold_accents

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
    """Lazily materialize a bounded BM25 index with interval-based freshness."""

    def __init__(
        self,
        vector_store: QdrantVectorStore,
        *,
        max_chunks: int = 10000,
        refresh_interval_seconds: float = 60.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if refresh_interval_seconds <= 0:
            raise ValueError("refresh_interval_seconds must be positive.")
        self.vector_store = vector_store
        self.max_chunks = max_chunks
        self.refresh_interval_seconds = refresh_interval_seconds
        self._monotonic = monotonic
        self._index: BM25Index | None = None
        self._refreshed_at: float | None = None
        self._lock = Lock()

    def search(self, query: str, *, limit: int, **filters: str | None) -> list[RetrievalResult]:
        return self._get_index().search(query, limit=limit, **filters)

    def refresh(self) -> None:
        """Invalidate cached sparse state after an explicit indexing operation."""

        with self._lock:
            self._index = None
            self._refreshed_at = None

    def _get_index(self) -> BM25Index:
        now = self._now()
        if self._is_stale(now):
            with self._lock:
                now = self._now()
                if self._is_stale(now):
                    payloads = self.vector_store.list_chunks(max_chunks=self.max_chunks)
                    self._index = BM25Index([_from_vector_result(item) for item in payloads])
                    self._refreshed_at = now
        if self._index is None:  # pragma: no cover - guarded by the refresh branch
            raise RuntimeError("BM25 index initialization failed.")
        return self._index

    def _is_stale(self, now: float) -> bool:
        return (
            self._index is None
            or self._refreshed_at is None
            or (now - self._refreshed_at >= self.refresh_interval_seconds)
        )

    def _now(self) -> float:
        value = self._monotonic()
        return float(value)


def tokenize(text: str) -> list[str]:
    """Keep exact tokens and add distinct accent-folded Vietnamese variants."""

    normalized = unicodedata.normalize("NFC", text).casefold()
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(normalized):
        token = match.group(0)
        tokens.append(token)
        folded = fold_accents(token)
        if folded != token:
            tokens.append(folded)
    return tokens


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
