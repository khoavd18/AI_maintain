"""Cross-encoder reranking boundary for hybrid maintenance retrieval."""

from __future__ import annotations

from collections.abc import Sequence
import logging
import math
from threading import Lock
from typing import Protocol

import numpy as np

from src.rag.retriever import RetrievalResult

logger = logging.getLogger("maintenance.rag.reranking")


class RerankerUnavailableError(RuntimeError):
    """Raised when the optional cross-encoder cannot be loaded or executed."""


class Reranker(Protocol):
    def score(self, query: str, candidates: Sequence[RetrievalResult]) -> list[float]:
        """Return one normalized relevance score per candidate."""
        ...


class CrossEncoderReranker:
    """Lazy, process-cached multilingual cross-encoder with CPU fallback."""

    def __init__(
        self,
        model_name: str,
        *,
        device: str = "auto",
        batch_size: int = 16,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self._model: object | None = None
        self._lock = Lock()

    def score(self, query: str, candidates: Sequence[RetrievalResult]) -> list[float]:
        if not candidates:
            return []
        model = self._get_model()
        pairs = [
            (
                query,
                "\n".join(
                    value
                    for value in (
                        candidate.title,
                        candidate.doc_type,
                        candidate.asset_type,
                        candidate.failure_category,
                        candidate.text,
                    )
                    if value
                ),
            )
            for candidate in candidates
        ]
        try:
            raw_scores = model.predict(  # type: ignore[attr-defined]
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise RerankerUnavailableError("Cross-encoder reranking failed.") from exc
        scores = np.asarray(raw_scores, dtype=float).reshape(-1)
        if len(scores) != len(candidates) or not np.all(np.isfinite(scores)):
            raise RerankerUnavailableError("Cross-encoder returned invalid scores.")
        if np.any(scores < 0.0) or np.any(scores > 1.0):
            scores = np.asarray([_sigmoid(float(value)) for value in scores], dtype=float)
        return np.clip(scores, 0.0, 1.0).tolist()

    def _get_model(self) -> object:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._load_model()
        return self._model

    def _load_model(self) -> object:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RerankerUnavailableError(
                "sentence-transformers is required for cross-encoder reranking."
            ) from exc
        requested_device = None if self.device == "auto" else self.device
        try:
            model = CrossEncoder(self.model_name, device=requested_device)
        except Exception as exc:
            if self.device in {"auto", "cpu"}:
                raise RerankerUnavailableError(
                    "Could not load the configured cross-encoder."
                ) from exc
            logger.warning(
                "Reranker device %s was unavailable; retrying on CPU.",
                self.device,
            )
            try:
                model = CrossEncoder(self.model_name, device="cpu")
                self.device = "cpu"
            except Exception as fallback_exc:
                raise RerankerUnavailableError(
                    "Could not load the configured cross-encoder on CPU fallback."
                ) from fallback_exc
        logger.info(
            "Cross-encoder initialized: model=%s device=%s batch_size=%s",
            self.model_name,
            self.device,
            self.batch_size,
        )
        return model


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-min(value, 60.0)))
    exponent = math.exp(max(value, -60.0))
    return exponent / (1.0 + exponent)
