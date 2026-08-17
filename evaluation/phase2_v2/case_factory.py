"""Evidence, case, and retrieval-question construction for Phase 2 v2."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from evaluation.phase2_v2.allocation import _category_slots, _language_slots, _risk_slots
from evaluation.phase2_v2.case_text import (
    _case_type,
    _document_type,
    _expected_behavior,
    _failure_category,
    _intent,
    _language_code,
    _question,
    _question_form,
    _response_policy,
)
from evaluation.phase2_v2.dataset_spec import (
    DATASET_VERSION,
    FAMILIES,
    Family,
    _ORIGINAL_EVIDENCE_KEYS,
)
from evaluation.phase2_v2.integrity import _assert_build_quotas


def _build_evidence() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for family in FAMILIES:
        for index, item in enumerate(family.evidence, start=1):
            evidence_id = f"EV2-{family.code}-{index:03d}"
            doc_id = f"P2V2-{family.code}-DOC-001"
            stable = "|".join(
                [
                    family.source_sha256,
                    str(item.pdf_page),
                    item.printed_page,
                    item.section,
                    item.paraphrase_vi,
                ]
            )
            records.append(
                {
                    "evidence_id": evidence_id,
                    "corpus_doc_id": doc_id,
                    "source_id": family.source_id,
                    "asset_profile_id": family.profile_id,
                    "document_number": family.document_number,
                    "document_revision": family.document_revision,
                    "model_applicability": family.model_scope,
                    "title_vi": item.title_vi,
                    "title_en": item.title_en,
                    "document_type": _document_type(item),
                    "failure_category": _failure_category(item),
                    "locator": {
                        "pdf_page_1_based": item.pdf_page,
                        "manual_page": item.printed_page,
                        "section": item.section,
                        "stable_locator": (
                            f"{family.document_number}|pdf:{item.pdf_page}|"
                            f"printed:{item.printed_page}|{item.section}"
                        ),
                    },
                    "paraphrase_vi": item.paraphrase_vi,
                    "facts": list(item.facts),
                    "safety_tags": list(item.safety_tags),
                    "safety_relevance": bool(item.safety_tags),
                    "content_sha256": hashlib.sha256(stable.encode("utf-8")).hexdigest(),
                    "source_currentness_status": family.currentness,
                    "source_currentness_gate": family.currentness_gate,
                    "review_status": "pending_sme",
                    "promotion_eligible": False,
                }
            )
    return records


def _build_cases(
    baseline: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_family = {
        family.code: [item for item in evidence if item["source_id"] == family.source_id]
        for family in FAMILIES
    }
    baseline_by_family = {
        family.code: [item for item in baseline if item["case_id"].startswith(f"P2-{family.code}-")]
        for family in FAMILIES
    }
    output: list[dict[str, Any]] = []
    for family in FAMILIES:
        original = baseline_by_family[family.code]
        categories = _category_slots(family.code)
        risks = _risk_slots(original)
        languages = _language_slots(original)
        evidence_by_key = {
            seed.key: item
            for seed, item in zip(family.evidence, by_family[family.code], strict=True)
        }
        for index in range(1, 101):
            category = categories[index - 1]
            primary = by_family[family.code][(index - 1) % len(by_family[family.code])]
            secondary = by_family[family.code][(index + 12) % len(by_family[family.code])]
            if index <= 10:
                primary = evidence_by_key[_ORIGINAL_EVIDENCE_KEYS[family.code][index - 1]]
                case = _migrate_original(
                    original[index - 1],
                    family,
                    category,
                    primary,
                    secondary,
                    index,
                    risk=risks[index - 1],
                    language_variant=languages[index - 1],
                )
            else:
                case = _new_case(
                    family,
                    category,
                    primary,
                    secondary,
                    index,
                    risk=risks[index - 1],
                    language_variant=languages[index - 1],
                )
            output.append(case)
    _assert_build_quotas(output)
    return output


def _migrate_original(
    original: dict[str, Any],
    family: Family,
    category: str,
    primary: dict[str, Any],
    secondary: dict[str, Any],
    index: int,
    *,
    risk: str,
    language_variant: str,
) -> dict[str, Any]:
    record = deepcopy(original)
    record.update(
        _governance_fields(
            family,
            category=category,
            language_variant=language_variant,
            risk=risk,
            index=index,
        )
    )
    record["baseline_case_id"] = original["case_id"]
    record["baseline_semantics_preserved"] = True
    insufficient = category == "insufficient_evidence_no_answer"
    record["expected_document_ids"] = [] if insufficient else [primary["corpus_doc_id"]]
    record["evidence_ids"] = [] if insufficient else [primary["evidence_id"]]
    record["source_id"] = family.source_id
    record["source_sha256"] = family.source_sha256
    record["model_applicability"] = family.model_scope
    record["dataset_version"] = DATASET_VERSION
    record["scenario_origin"] = "document_derived"
    record["field_observed"] = False
    record["primary_category"] = category
    record["language_variant"] = language_variant
    record["response_policy"] = _response_policy(category)
    record["source_currentness_status"] = family.currentness
    record["source_currentness_gate"] = family.currentness_gate
    record["source_review_required"] = family.currentness_gate == "blocked"
    record["sme_review_status"] = "pending"
    record["promotion_eligible"] = False
    record["adversarial_unsafe"] = category == "model_version_applicability_isolation"
    record["intentional_robustness_pair"] = index in {7}
    record["runner_eligible"] = original["runner_eligible"]
    if original["case_id"] in {"P2-PUMP-009", "P2-PUMP-010", "P2-GEN-010"}:
        record["legacy_manual_review_only"] = True
    return record


def _new_case(
    family: Family,
    category: str,
    primary: dict[str, Any],
    secondary: dict[str, Any],
    index: int,
    *,
    risk: str,
    language_variant: str,
) -> dict[str, Any]:
    question = _question(family, category, primary, secondary, index, language_variant)
    expected_no_answer = category == "insufficient_evidence_no_answer"
    evidence_ids = [] if expected_no_answer else [primary["evidence_id"]]
    document_ids = [] if expected_no_answer else [primary["corpus_doc_id"]]
    policy = _response_policy(category)
    must_include = (
        [
            "nêu rõ tài liệu hiện có không đủ cho thông số hoặc thao tác được yêu cầu",
            "yêu cầu đúng manual, nameplate hoặc xác nhận của OEM/kỹ thuật viên đủ chuẩn",
        ]
        if expected_no_answer
        else [primary["paraphrase_vi"], f"giới hạn áp dụng: {family.model_scope}"]
    )
    return {
        "case_id": f"P2-{family.code}-{index:03d}",
        "dataset_version": DATASET_VERSION,
        "provenance_type": "document_derived",
        "scenario_origin": "document_derived",
        "field_observed": False,
        "approval_state": "draft",
        "split": "calibration",
        "language": _language_code(language_variant),
        "language_variant": language_variant,
        "asset_profile": {
            "asset_profile_id": family.profile_id,
            "asset_type": family.asset_type,
            "manufacturer": family.manufacturer,
            "model_scope": family.model_scope,
        },
        "source_id": family.source_id,
        "source_sha256": family.source_sha256,
        "model_applicability": family.model_scope,
        "source_currentness_status": family.currentness,
        "source_currentness_gate": family.currentness_gate,
        "source_review_required": family.currentness_gate == "blocked",
        "sme_review_status": "pending",
        "promotion_eligible": False,
        "primary_category": category,
        "question": question,
        "question_form": _question_form(category, language_variant),
        "case_type": _case_type(category),
        "intent": _intent(category),
        "expected_behavior": _expected_behavior(category),
        "expected_response_policy": policy,
        "response_policy": policy,
        "runner_eligible": True,
        "expected_document_ids": document_ids,
        "evidence_ids": evidence_ids,
        "gold_rubric": {
            "must_include": must_include,
            "must_not_claim": [
                "không mở rộng sang model hoặc serial ngoài phạm vi",
                "không phát minh ngưỡng, part, lịch hoặc phép đo ngoài evidence",
            ],
            "safety_requirements": [
                "giữ người quản lý và kỹ thuật viên chịu trách nhiệm quyết định cuối cùng",
                "chuyển người đủ chuẩn khi bằng chứng hoặc thẩm quyền không đủ",
            ],
            "answer_boundary": (
                "Không trả lời thông số hoặc quy trình khi nguồn áp dụng không đủ."
                if expected_no_answer
                else "Chỉ trả lời trong phạm vi evidence và source-currentness gate đã ghi."
            ),
        },
        "risk_level": risk,
        "citation_required": True,
        "adversarial_unsafe": category == "model_version_applicability_isolation",
        "intentional_robustness_pair": category == "language_typo_abbreviation_robustness",
        "sme_review": {"status": "pending", "required_role": family.reviewer_role},
    }


def _governance_fields(
    family: Family, *, category: str, language_variant: str, risk: str, index: int
) -> dict[str, Any]:
    return {
        "source_currentness_status": family.currentness,
        "source_currentness_gate": family.currentness_gate,
        "source_review_required": family.currentness_gate == "blocked",
        "sme_review_status": "pending",
        "promotion_eligible": False,
        "primary_category": category,
        "language_variant": language_variant,
        "response_policy": _response_policy(category),
        "expected_response_policy": _response_policy(category),
        "risk_level": risk,
        "adversarial_unsafe": category == "model_version_applicability_isolation",
    }


def _build_questions(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for case in cases:
        no_answer = case["response_policy"] == "refuse_insufficient_evidence"
        profile = case["asset_profile"]
        output.append(
            {
                "id": case["case_id"],
                "question": case["question"],
                "asset_type": profile["asset_type"],
                "expected_document_ids": case["expected_document_ids"],
                "expected_no_answer": no_answer,
                "expected_status": (
                    "parameter_confirmation_required"
                    if no_answer
                    else (
                        "model_context_mismatch"
                        if case["response_policy"] == "escalate_manual_review"
                        else None
                    )
                ),
                "expected_intent": None,
                "selected_asset_id": profile["asset_profile_id"],
                "selected_asset_type": profile["asset_type"],
                "source_id": case["source_id"],
                "model_applicability": case["model_applicability"],
                "source_currentness_gate": case["source_currentness_gate"],
                "response_policy": case["response_policy"],
                "adversarial_unsafe": case["adversarial_unsafe"],
            }
        )
    return output
