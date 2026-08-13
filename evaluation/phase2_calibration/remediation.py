"""Authoritative, bounded decisions for formerly unresolved calibration evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceRemediation:
    """One captured-PDF decision, distinct from SME review or source currentness."""

    evidence_id: str
    source_anchor: str
    rationale: str
    old_section: str
    verified_section: str


REMEDIATIONS = {
    "EV2-HVAC-026": EvidenceRemediation(
        evidence_id="EV2-HVAC-026",
        source_anchor="Piping size mm Tightening torque N m Flare dimensions A",
        rationale="Rendered PDF page 42 explicitly gives Ø9.5 as 33~39 N•m; the original title named the adjacent connection-guidelines heading.",
        old_section="7.4.5 Flare connection guidelines",
        verified_section="7.4.5 To flare the pipe end",
    ),
    "EV2-HVAC-043": EvidenceRemediation(
        evidence_id="EV2-HVAC-043",
        source_anchor="Open the liquid stop valve and gas stop valve",
        rationale="Rendered PDF pages 66-68 show checklist completion, stop-valve opening, six-hour power-on, test operation, and stopping through the service interface.",
        old_section="8.4 To perform a test run",
        verified_section="8.4 To perform a test run",
    ),
    "EV2-GEN-027": EvidenceRemediation(
        evidence_id="EV2-GEN-027",
        source_anchor="A Air filter B Radiator C Coolant overflow jug",
        rationale="Rendered PDF page 16 labels the named interior components in Figure 2-3.",
        old_section="Component Locations Interior",
        verified_section="Component Locations Interior",
    ),
    "EV2-GEN-035": EvidenceRemediation(
        evidence_id="EV2-GEN-035",
        source_anchor="Do not continuously crank engine for more than ten seconds",
        rationale="Rendered PDF page 19 explicitly limits continuous cranking to ten seconds and warns of starter seizure.",
        old_section="Starting the Unit",
        verified_section="Starting the Unit",
    ),
    "EV2-GEN-036": EvidenceRemediation(
        evidence_id="EV2-GEN-036",
        source_anchor="If oil pressure is not obtained within 15 seconds after",
        rationale="Rendered PDF page 20 explicitly states the 15-second RUN threshold and automatic fuel shutoff.",
        old_section="Starting the Unit",
        verified_section="Starting the Unit",
    ),
}
