"""Baseline preservation and source registry construction for Phase 2 v2."""

from __future__ import annotations

from typing import Any

from evaluation.phase2_v2.dataset_spec import FAMILIES, V1
from evaluation.phase2_v2.integrity import _load_jsonl


def _build_sources() -> list[dict[str, Any]]:
    return [
        {
            "source_id": family.source_id,
            "manufacturer": family.manufacturer,
            "asset_profile_id": family.profile_id,
            "asset_type": family.asset_type,
            "model_scope": family.model_scope,
            "title": f"Captured official OEM document — {family.document_number}",
            "document_number": family.document_number,
            "document_revision": family.document_revision,
            "language": "en",
            "official_url": family.official_url,
            "provenance_type": "document_derived",
            "scenario_origin": "document_derived",
            "authority": "manufacturer_hosted_or_distributed",
            "source_file_included": False,
            "redistribution_mode": "link_only",
            "sha256": family.source_sha256,
            "checksum_status": "captured_external_vault",
            "source_currentness_status": family.currentness,
            "source_currentness_risk": family.currentness_risk,
            "source_currentness_gate": family.currentness_gate,
            "source_review_required": family.currentness_gate == "blocked",
            "review_status": "pending_sme",
            "promotion_eligible": False,
            "notes": (
                "Source-currentness status is an audit gate, not SME approval. Full PDF bytes remain "
                "outside Git in the authorized local evidence vault."
            ),
        }
        for family in FAMILIES
    ]


def load_v1_cases() -> list[dict[str, Any]]:
    """Load the immutable v1 cases as the preserved baseline."""

    return _load_jsonl(V1 / "cases.jsonl")
