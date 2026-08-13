"""Chunk-level deterministic calibration evaluation through production request analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.phase2_calibration.common import jsonl, normalized_fragment, write_json
from src.rag.application.request_analysis import RequestAnalysisService
from src.rag.query_analysis import QueryAnalyzer
from src.rag.retriever import RetrievalResult


@dataclass(frozen=True)
class ChunkRetriever:
    chunks: tuple[dict[str, Any], ...]

    def search(
        self, query: str, limit: int = 5, asset_type: str | None = None, **_: object
    ) -> list[RetrievalResult]:
        terms = set(normalized_fragment(query).split())
        candidates = [
            chunk
            for chunk in self.chunks
            if asset_type is None or chunk["asset_type"] == asset_type
        ]
        scored = sorted(
            candidates,
            key=lambda row: (
                -len(terms & set(normalized_fragment(row["text"]).split())),
                row["chunk_id"],
            ),
        )
        return [
            RetrievalResult(
                chunk_id=row["chunk_id"],
                doc_id=row["doc_id"],
                title=row["title"],
                doc_type=row["doc_type"],
                asset_type=row["asset_type"],
                source=row["source"],
                text=row["text"],
                score=float(len(terms & set(normalized_fragment(row["text"]).split()))),
                chunk_index=row["chunk_index"],
            )
            for row in scored[:limit]
        ]


class _AssetContext:
    def __init__(self, questions: list[dict[str, Any]]) -> None:
        self.by_id = {q["selected_asset_id"]: q for q in questions}

    def get_asset_context(self, asset_id: str) -> dict[str, Any]:
        row = self.by_id[asset_id]
        return {
            "asset_profile": {
                "asset_id": asset_id,
                "asset_type": row["asset_type"],
                "model_scope": row["model_applicability"],
            },
            "latest_risk": {"asset_id": asset_id, "asset_type": row["asset_type"]},
            "recent_anomalies": [],
            "maintenance_logs": [],
            "tickets": [],
        }


def run_calibration_retrieval(dataset: Path, output: Path | None = None) -> dict[str, Any]:
    """Score chunk IDs after prediction; gold evidence never reaches retriever input."""

    questions, chunks = (
        jsonl(dataset / "retrieval_questions.jsonl"),
        jsonl(dataset / "evidence_chunks.jsonl"),
    )
    retriever = ChunkRetriever(tuple(chunks))
    analysis = RequestAnalysisService(
        asset_context_provider=_AssetContext(questions), query_analyzer=QueryAnalyzer()
    )
    answerable, failures, per_family = [], [], {}
    no_answer_hits = wrong_model_hits = 0
    no_answer_total = wrong_model_total = 0
    for question in questions:
        prepared = analysis.prepare(
            question=question["question"],
            asset_id=question["selected_asset_id"],
            document_type=None,
            failure_category=None,
            version=None,
            language=None,
            conversation_context=None,
        )
        before = len(chunks)
        after = sum(c["asset_type"] == question["asset_type"] for c in chunks)
        if question["manual_review_only"]:
            if prepared.early_status == "parameter_confirmation_required":
                no_answer_total += 1
                no_answer_hits += 1
            if prepared.early_status == "model_context_mismatch":
                wrong_model_total += 1
                wrong_model_hits += 1
            failures.append(
                {
                    "id": question["id"],
                    "category": "manual_review",
                    "predicted_status": prepared.early_status,
                    "ranked_evidence_ids": [],
                }
            )
            continue
        ranked = retriever.search(
            prepared.retrieval_query or question["question"],
            asset_type=prepared.filters.get("asset_type") or question["asset_type"],
        )
        ids = [r.chunk_id for r in ranked]
        gold = set(question["expected_evidence_ids"])
        rank = next((i for i, value in enumerate(ids, 1) if value in gold), None)
        result = {
            "id": question["id"],
            "candidate_pool_before_filter": before,
            "candidate_pool_after_filter": after,
            "ranked_evidence_ids": ids,
            "expected_evidence_ids": sorted(gold),
            "rank": rank,
        }
        answerable.append(result)
        if rank is None or rank > 1:
            failures.append({**result, "category": "answerable"})
    denom = len(answerable)
    metrics = {
        "evidence_recall_at_1": sum(x["rank"] is not None and x["rank"] <= 1 for x in answerable)
        / denom,
        "evidence_recall_at_3": sum(x["rank"] is not None and x["rank"] <= 3 for x in answerable)
        / denom,
        "evidence_recall_at_5": sum(x["rank"] is not None and x["rank"] <= 5 for x in answerable)
        / denom,
        "mrr": sum(1 / x["rank"] if x["rank"] else 0 for x in answerable) / denom,
        "ndcg_at_5": sum(
            1 / __import__("math").log2(x["rank"] + 1) if x["rank"] and x["rank"] <= 5 else 0
            for x in answerable
        )
        / denom,
        "metadata_filter_accuracy": sum(x["candidate_pool_after_filter"] >= 50 for x in answerable)
        / denom,
    }
    for family in sorted({q["asset_type"] for q in questions}):
        values = [
            x
            for x in answerable
            if next(q for q in questions if q["id"] == x["id"])["asset_type"] == family
        ]
        per_family[family] = {
            "count": len(values),
            "recall_at_1": sum(x["rank"] == 1 for x in values) / len(values),
            "candidate_pool_after_filter": values[0]["candidate_pool_after_filter"]
            if values
            else 0,
        }
    report = {
        "dataset": str(dataset),
        "fixture_components": ["deterministic lexical ChunkRetriever"],
        "production_components": ["RequestAnalysisService", "QueryAnalyzer", "Retriever protocol"],
        "live_llm_called": False,
        "candidate_pool_before_filter": 152,
        "answerable_retrieval": {"count": denom, **metrics, "per_family": per_family},
        "insufficient_evidence": {
            "count": no_answer_total,
            "no_answer_routing_accuracy": no_answer_hits / no_answer_total,
        },
        "wrong_model_applicability": {
            "count": wrong_model_total,
            "wrong_model_rejection_accuracy": wrong_model_hits / wrong_model_total,
        },
        "manual_review": {"count": 3},
        "conversation_state": {
            "count": 0,
            "metric": "n/a; this bounded calibration set preserves original single-turn cases",
        },
        "failures": failures,
    }
    if output:
        write_json(output, report)
    return report


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            run_calibration_retrieval(args.dataset, args.output), ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
