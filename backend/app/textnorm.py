"""Text normalization + quote verification.

Grounding rule: a fact is only stored if its evidence quote can be found in the
actual page text (after whitespace normalization). This module owns that rule.
"""
import re
from dataclasses import dataclass

_WS = re.compile(r"\s+")

# PDF extraction often swaps typographic punctuation for ASCII lookalikes.
_PUNCT_MAP = str.maketrans({
    "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u00a0": " ",
})


def normalize(text: str) -> str:
    text = text.translate(_PUNCT_MAP)
    """Lowercase and collapse all whitespace runs to single spaces.

    PDF text extraction jumbles line breaks and spacing, so quotes are compared
    in this normalized space rather than byte-for-byte.
    """
    return _WS.sub(" ", text).strip().lower()


def similarity(a: str, b: str) -> float:
    """Cheap char-trigram Jaccard similarity for fuzzy quote matching."""
    ta, tb = normalize(a), normalize(b)
    if not ta or not tb:
        return 0.0

    def trigrams(s: str) -> set:
        return {s[i : i + 3] for i in range(len(s) - 2)}

    ga, gb = trigrams(ta), trigrams(tb)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


@dataclass
class QuoteCheck:
    verified: bool
    page: int | None
    score: float  # 1.0 exact normalized match, <1 fuzzy


def verify_quote(quote: str, pages: dict[int, str]) -> QuoteCheck:
    """Locate a quote in {page_number: page_text}. Exact match first, then fuzzy."""
    nq = normalize(quote)
    if not nq:
        return QuoteCheck(False, None, 0.0)

    for page in sorted(pages):
        if nq in normalize(pages[page]):
            return QuoteCheck(True, page, 1.0)

    # Fuzzy: find the best page by sliding a window of the quote's length.
    best_page, best_score = None, 0.0
    qlen = len(nq)
    for page in sorted(pages):
        ntext = normalize(pages[page])
        if len(ntext) < 10:
            continue
        step = max(50, qlen // 4)
        for i in range(0, max(1, len(ntext) - qlen + 1), step):
            window = ntext[i : i + qlen + 40]
            score = similarity(nq, window)
            if score > best_score:
                best_page, best_score = page, score
    if best_score >= 0.75:
        return QuoteCheck(True, best_page, best_score)
    return QuoteCheck(False, best_page, best_score)
