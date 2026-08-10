"""Validate release gate identity, criticality, status, and evidence."""

from __future__ import annotations

from typing import Any

from ..constants import CRITICAL_GATES
from ..document_shapes import _check_unique_names, _list_of_mappings
from ..evidence_values import _valid_evidence_links
from ..findings import _add
from ..schemas import Finding


def _validate_release_record_gates(
    record: dict[str, Any],
    findings: list[Finding],
) -> None:
    gates = _list_of_mappings(
        record.get("gates"),
        findings=findings,
        scope="release_record.gates",
    )
    gate_ids = _check_unique_names(gates, "id", "gate", findings)
    for gate_id in sorted(CRITICAL_GATES - gate_ids):
        _add(
            findings,
            "critical_gate_missing",
            f"release_record.gates.{gate_id}",
            f"Thiếu critical gate: {gate_id}.",
        )
    for gate in gates:
        gate_id = str(gate.get("id", "unknown"))
        if gate_id in CRITICAL_GATES and gate.get("critical") is not True:
            _add(
                findings,
                "critical_gate_weakened",
                f"release_record.gates.{gate_id}",
                "Critical gate không được hạ cấp.",
            )
        if gate.get("status") not in {"passed", "failed", "unverified"}:
            _add(
                findings,
                "gate_status_invalid",
                f"release_record.gates.{gate_id}",
                "Gate status phải là passed, failed hoặc unverified.",
            )
        if gate.get("status") == "passed" and not _valid_evidence_links(gate.get("evidence_links")):
            _add(
                findings,
                "gate_evidence_missing",
                f"release_record.gates.{gate_id}",
                "Gate passed phải có evidence link.",
            )
        if gate_id in CRITICAL_GATES and gate.get("status") != "passed":
            _add(
                findings,
                "critical_gate_open",
                f"release_record.gates.{gate_id}",
                f"Critical gate chưa passed: {gate_id}.",
            )
