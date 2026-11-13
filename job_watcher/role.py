"""The single title-only rule for Finance & Banking Analyst.

Normalize Unicode, case and punctuation. Match an approved family immediately
before or after 'analyst', allowing up to two seniority/level tokens between.
FP&A is expanded before punctuation normalization. Bare risk is not a family.
"""

import re
import unicodedata

TARGET_ROLE = "Finance & Banking Analyst"
FAMILIES = (
    "financial", "finance", "fpanda", "financial planning and analysis",
    "treasury", "credit", "commercial banking", "corporate banking",
    "capital markets", "investment banking", "banking",
    "financial risk", "banking risk", "credit risk", "market risk",
    "liquidity risk", "treasury risk", "capital risk", "investment risk",
    "counterparty risk",
)
_FAMILY = "(?:" + "|".join(re.escape(x) for x in FAMILIES) + ")"
_LEVEL = r"(?:senior|sr|lead|principal|junior|jr|i|ii|iii|iv|1|2|3|4)"
_GAP = rf" (?:{_LEVEL} ){{0,2}}"
_RULE = re.compile(rf"\b(?:{_FAMILY}{_GAP}analyst|analyst{_GAP}{_FAMILY})\b")


def in_role(title: str) -> bool:
    """Classify only the title; never inspect employer, description or category."""
    title = unicodedata.normalize("NFKC", title).casefold()
    title = re.sub(r"\bfp\s*&\s*a\b", "fpanda", title)
    title = title.replace("&", " and ")
    title = " ".join(re.sub(r"[\W_]+", " ", title).split())
    return bool(_RULE.search(title))
