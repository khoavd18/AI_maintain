from __future__ import annotations

import json

from src.analytics.question_router import QuestionRoute, route_question
from src.rag.evidence_export import (
    EvidenceCandidate,
    collect_eligible_evidence,
    export_evidence_jsonl,
)


def test_evidence_filter_excludes_sensitive_ineligible_and_duplicate_text() -> None:
    candidates = [
        EvidenceCandidate("sop", "sop-1", "Inspect and isolate power.", None, {"path": "a"}),
        EvidenceCandidate("sop", "sop-2", " Inspect  and isolate power. ", None, {"path": "b"}),
        EvidenceCandidate(
            "technician_note",
            "ticket-1",
            "Contact user@example.com before work.",
            None,
            {"ticket": "ticket-1"},
        ),
        EvidenceCandidate(
            "resolution_summary",
            "ticket-2",
            "Safe synthetic resolution evidence.",
            None,
            {"ticket": "ticket-2"},
            contains_sensitive_data=True,
        ),
        EvidenceCandidate("unknown", "x", "Not eligible.", None, {}),
    ]

    result = collect_eligible_evidence(candidates, max_candidates=10)

    assert len(result) == 1
    assert result[0].source_id == "sop-1"
    assert result[0].provenance == {"path": "a"}


def test_local_export_is_bounded_and_reports_zero_external_calls(tmp_path) -> None:
    candidates = (
        EvidenceCandidate("manual", str(index), f"Manual evidence {index}", None, {})
        for index in range(10)
    )
    destination = tmp_path / "evidence.jsonl"

    result = export_evidence_jsonl(candidates, destination, max_candidates=3)

    lines = destination.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert all(json.loads(line)["evidence_type"] == "manual" for line in lines)
    assert result["embedding_calls"] == 0
    assert result["external_api_calls"] == 0


def test_question_routing_keeps_analytics_and_semantic_evidence_separate() -> None:
    assert route_question("What is the monthly SLA breach rate by site?") == (
        QuestionRoute.STRUCTURED_ANALYTICS
    )
    assert route_question("Show the SOP for isolating this pump") == (
        QuestionRoute.SEMANTIC_EVIDENCE
    )
