"""Unicode-safe Vietnamese matching without altering source queries or identifiers."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class NormalizedText:
    """Exact and accent-folded views used only for deterministic comparisons."""

    exact: str
    folded: str

    def contains(self, *phrases: str) -> bool:
        """Match a phrase against either view while respecting word boundaries."""

        return any(_contains_phrase(self, phrase) for phrase in phrases)


def normalize_for_matching(text: str) -> NormalizedText:
    """Return NFC/case-folded text plus an accent-insensitive comparison view."""

    exact = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text).casefold()).strip()
    return NormalizedText(exact=exact, folded=fold_accents(exact))


def fold_accents(text: str) -> str:
    """Fold Vietnamese accents for matching while leaving caller data untouched."""

    decomposed = unicodedata.normalize("NFD", text.casefold()).replace("đ", "d")
    folded = "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    )
    return unicodedata.normalize("NFC", folded)


def _contains_phrase(text: NormalizedText, phrase: str) -> bool:
    normalized_phrase = normalize_for_matching(phrase)
    return _bounded_contains(text.exact, normalized_phrase.exact) or _bounded_contains(
        text.folded,
        normalized_phrase.folded,
    )


def _bounded_contains(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, flags=re.UNICODE) is not None
