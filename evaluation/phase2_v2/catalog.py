"""Shared types for concise, source-traceable OEM evidence catalogs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceSeed:
    """One short paraphrase tied to a stable place in a captured OEM document."""

    key: str
    pdf_page: int
    printed_page: str
    section: str
    title_vi: str
    title_en: str
    paraphrase_vi: str
    facts: tuple[str, ...]
    safety_tags: tuple[str, ...] = ()


def seed(
    key: str,
    pdf_page: int,
    printed_page: str,
    section: str,
    title_vi: str,
    title_en: str,
    paraphrase_vi: str,
    *facts: str,
    safety: tuple[str, ...] = (),
) -> EvidenceSeed:
    """Keep family catalogs compact without hiding any traceability field."""

    return EvidenceSeed(
        key=key,
        pdf_page=pdf_page,
        printed_page=printed_page,
        section=section,
        title_vi=title_vi,
        title_en=title_en,
        paraphrase_vi=paraphrase_vi,
        facts=facts,
        safety_tags=safety,
    )
