"""Release-record tests grouped by validation capability."""

from __future__ import annotations

from ._release_record_scenarios import (
    CRITICAL_GATES,
    _finding,
    _findings,
    _only,
    _ready_documents,
    deepcopy,
)


def test_missing_critical_gates_are_sorted() -> None:
    *_, record = _ready_documents()
    record["gates"] = []

    assert _only(_findings(record=record)[1], {"critical_gate_missing"}) == [
        _finding(
            "critical_gate_missing",
            f"release_record.gates.{gate_id}",
            f"Thiếu critical gate: {gate_id}.",
        )
        for gate_id in sorted(CRITICAL_GATES)
    ]


def test_duplicate_gate_and_per_gate_findings_keep_order() -> None:
    *_, record = _ready_documents()
    gate = deepcopy(record["gates"][0])
    record["gates"].append(gate)
    gate["critical"] = False
    gate["status"] = "unknown"
    gate["evidence_links"] = []
    gate_id = gate["id"]

    findings = _only(
        _findings(record=record)[1],
        {"duplicate_gate", "critical_gate_weakened", "gate_status_invalid", "critical_gate_open"},
    )
    assert [finding.code for finding in findings] == [
        "duplicate_gate",
        "critical_gate_weakened",
        "gate_status_invalid",
        "critical_gate_open",
    ]
    assert all(gate_id in finding.scope for finding in findings)


def test_passed_gate_requires_evidence_but_unknown_noncritical_gate_is_allowed() -> None:
    *_, record = _ready_documents()
    record["gates"].append(
        {"id": "optional_gate", "critical": False, "status": "passed", "evidence_links": []}
    )

    assert _only(_findings(record=record)[1], {"gate_evidence_missing"}) == [
        _finding(
            "gate_evidence_missing",
            "release_record.gates.optional_gate",
            "Gate passed phải có evidence link.",
        )
    ]
