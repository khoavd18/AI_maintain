"""Shared immutable configuration for the Phase 2 v2 dataset builder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from evaluation.phase2_v2.catalog import EvidenceSeed
from evaluation.phase2_v2.catalog_generator import GENERATOR_EVIDENCE
from evaluation.phase2_v2.catalog_hvac import HVAC_EVIDENCE
from evaluation.phase2_v2.catalog_pump import PUMP_EVIDENCE

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "evaluation" / "datasets" / "phase2_document_derived_v1"
DEFAULT_OUTPUT = ROOT / "evaluation" / "datasets" / "phase2_document_derived_v2"
DATASET_VERSION = "2.0.0"

CATEGORY_QUOTA = (
    ("troubleshooting", 30),
    ("operation_repair_procedure", 15),
    ("preventive_maintenance_inspection", 12),
    ("safety_escalation", 10),
    ("insufficient_evidence_no_answer", 10),
    ("model_version_applicability_isolation", 10),
    ("multi_turn_follow_up", 8),
    ("language_typo_abbreviation_robustness", 5),
)
RISK_TARGET = {"critical": 15, "high": 25, "medium": 35, "low": 25}
LANGUAGE_TARGET = {
    "vi_diacritics": 60,
    "vi_no_diacritics": 15,
    "en": 15,
    "mixed_vi_en": 10,
}


@dataclass(frozen=True)
class Family:
    code: str
    source_id: str
    profile_id: str
    asset_type: str
    manufacturer: str
    model_scope: str
    document_number: str
    document_revision: str
    official_url: str
    source_sha256: str
    currentness: str
    currentness_risk: str
    currentness_gate: str
    reviewer_role: str
    evidence: tuple[EvidenceSeed, ...]


FAMILIES = (
    Family(
        code="PUMP",
        source_id="SRC-GF-CR5-0407",
        profile_id="ASSET-PUMP-GF-CR5-A",
        asset_type="Máy bơm nước",
        manufacturer="Grundfos",
        model_scope="CR 1, CR 3 and CR 5; Model A; 50/60 Hz; 1/3 phase",
        document_number="96546866",
        document_revision="captured 03.2022; registered 0407 GB unresolved",
        official_url="https://api.grundfos.com/literature/Grundfosliterature-79597.pdf",
        source_sha256="53c0b3599bf6ebb307dd96d3046971c0907792aac0f15a8372a7f29f8de7a33a",
        currentness="VERSION_AMBIGUOUS",
        currentness_risk="HIGH",
        currentness_gate="blocked",
        reviewer_role="pump_maintenance_engineer",
        evidence=PUMP_EVIDENCE,
    ),
    Family(
        code="HVAC",
        source_id="SRC-DAIKIN-RZAG-4P695307-1B",
        profile_id="ASSET-HVAC-DAIKIN-RZAG-N",
        asset_type="Máy lạnh",
        manufacturer="Daikin",
        model_scope="RZAG71-140N Sky Air Alpha-series; V1B/Y1B variants on cover",
        document_number="4P695307-1B",
        document_revision="2025.03",
        official_url=(
            "https://www.daikin.eu/content/dam/document-library/Installer-reference-guide/"
            "ac/sky-air/rzag-nv1_ny1/RZAG-NV1.RZAG-NY2_Installer%20reference%20guide_"
            "4PEN695307-1B_English.pdf"
        ),
        source_sha256="e02cff997f4fd499c880ceb1b3a175011cfc12476d5925ae79acb722a54c8936",
        currentness="VERIFIED_CURRENT",
        currentness_risk="MEDIUM",
        currentness_gate="passed",
        reviewer_role="hvac_service_engineer",
        evidence=HVAC_EVIDENCE,
    ),
    Family(
        code="GEN",
        source_id="SRC-GENERAC-MLG15-A0000381158",
        profile_id="ASSET-GEN-GENERAC-MLG15",
        asset_type="Máy phát điện dự phòng",
        manufacturer="Generac Mobile",
        model_scope="MLG15 diesel generator, serial number 3004595385 and above",
        document_number="A0000381158",
        document_revision="Rev. A, 09/10/2019",
        official_url=(
            "https://www.generac.com/globalassets/products/business/mobile-power--light-"
            "solutions/mobile-generators/owners-manual/mlg15_diesel-generator_owners-manual.pdf"
        ),
        source_sha256="ea0ac1dd6dea236aad4f939d47b9dd9e2f1c94dd8854b78fd0ebebe173ca29c8",
        currentness="VERSION_AMBIGUOUS",
        currentness_risk="HIGH",
        currentness_gate="blocked",
        reviewer_role="generator_maintenance_engineer",
        evidence=GENERATOR_EVIDENCE,
    ),
)

_MODEL_SWITCH = {"PUMP": "CR 10", "HVAC": "RZAG50N", "GEN": "MLG20"}
_ORIGINAL_CATEGORIES = {
    "PUMP": (
        "safety_escalation",
        "preventive_maintenance_inspection",
        "operation_repair_procedure",
        "operation_repair_procedure",
        "operation_repair_procedure",
        "troubleshooting",
        "preventive_maintenance_inspection",
        "operation_repair_procedure",
        "insufficient_evidence_no_answer",
        "model_version_applicability_isolation",
    ),
    "HVAC": (
        "preventive_maintenance_inspection",
        "safety_escalation",
        "safety_escalation",
        "troubleshooting",
        "preventive_maintenance_inspection",
        "troubleshooting",
        "troubleshooting",
        "troubleshooting",
        "safety_escalation",
        "safety_escalation",
    ),
    "GEN": (
        "preventive_maintenance_inspection",
        "safety_escalation",
        "safety_escalation",
        "safety_escalation",
        "troubleshooting",
        "operation_repair_procedure",
        "preventive_maintenance_inspection",
        "troubleshooting",
        "troubleshooting",
        "insufficient_evidence_no_answer",
    ),
}
_ORIGINAL_EVIDENCE_KEYS = {
    "PUMP": (
        "before-dismantle",
        "replace-seals",
        "coupling-gap",
        "seal-prepare",
        "main-dismantle",
        "impeller-wear",
        "neck-rings",
        "torque-coupling",
        "torque-coupling",
        "scope",
    ),
    "HVAC": (
        "maintenance-frequency",
        "capacitor",
        "x106a",
        "x106a",
        "heat-exchanger",
        "error-codes",
        "error-codes",
        "troubleshooting",
        "troubleshooting",
        "leak-pumpdown",
    ),
    "GEN": (
        "prestart-maintenance",
        "crank-limit",
        "shutdown-reset",
        "voltage-regulator",
        "wet-stacking",
        "shutdown-order",
        "oil-dipstick",
        "low-oil",
        "high-coolant",
        "engine-manual",
    ),
}
_ORIGINAL_UNACCENTED = {"P2-PUMP-007", "P2-HVAC-008", "P2-GEN-002"}
