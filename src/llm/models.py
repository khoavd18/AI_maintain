"""Strict structured-output models for grounded maintenance guidance."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

CitationId = Annotated[str, StringConstraints(pattern=r"^S[1-9][0-9]{0,2}$")]


class CitedStatement(BaseModel):
    """One maintenance statement supported by prompt-local source IDs."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=1200)
    source_ids: list[CitationId] = Field(min_length=1, max_length=5)

    @field_validator("source_ids")
    @classmethod
    def deduplicate_source_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class ConversationalLLMAnswer(BaseModel):
    """Validated output for bounded greetings and Copilot identity questions."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = Field(min_length=1, max_length=600)


class GroundedLLMAnswer(BaseModel):
    """Validated, Vietnamese, claim-level grounded model output."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=1800)
    summary_source_ids: list[CitationId] = Field(min_length=1, max_length=5)
    possible_causes: list[CitedStatement] = Field(max_length=5)
    recommended_checks: list[CitedStatement] = Field(max_length=8)
    safety_warnings: list[CitedStatement] = Field(max_length=6)
    escalation_required: bool
    source_ids: list[CitationId] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Exact deduplicated union of summary_source_ids and every claim-level source_ids; "
            "do not include unused sources."
        ),
    )
    confidence: Literal["low", "medium", "high"]
    insufficient_evidence: bool

    @field_validator("summary_source_ids")
    @classmethod
    def deduplicate_citations(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_guidance_shape(self) -> GroundedLLMAnswer:
        if self.insufficient_evidence:
            if not self.escalation_required:
                raise ValueError("insufficient_evidence requires escalation_required=true")
            if self.confidence == "high":
                raise ValueError("insufficient_evidence cannot have high confidence")
        elif not self.recommended_checks:
            raise ValueError("A grounded answer requires at least one recommended check")
        return self
