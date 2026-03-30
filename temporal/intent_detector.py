"""
Lightweight rule-based classifier that decides whether a user query
carries *temporal / version-comparison* intent.

Design choice: regex + keyword matching — fast, deterministic, no ML
dependency.  Easy to extend by adding patterns to ``_TEMPORAL_PATTERNS``.
"""

from __future__ import annotations

import re
from typing import List

# ---------------------------------------------------------------------------
# Patterns (case-insensitive).  Each entry is compiled once at import time.
# ---------------------------------------------------------------------------
_TEMPORAL_KEYWORDS: List[str] = [
    # explicit comparison / change language
    r"\bhow\s+has\b.*\bchanged\b",
    r"\bwhat\s+(has\s+)?changed\b",
    r"\bwhat\s+are\s+the\s+changes\b",
    r"\bcompare\b",
    r"\bcomparison\b",
    r"\bdifference(s)?\s+between\b",
    r"\bdiff\b",

    # version / amendment language
    r"\bprevious\s+version\b",
    r"\bearlier\s+(version|rule|regulation|clause|guideline)\b",
    r"\bold(er)?\s+(version|rule|regulation|clause|guideline)\b",
    r"\bnew(er)?\s+(version|rule|regulation|clause|guideline)\b",
    r"\bamendment(s)?\b",
    r"\bamended\b",
    r"\bsuperseded\b",
    r"\brevised\b",
    r"\brevision(s)?\b",
    r"\bupdate(d|s)?\b",

    # temporal cues
    r"\bchange\s+history\b",
    r"\bhistory\s+of\s+changes\b",
    r"\bover\s+time\b",
    r"\bversion\s+\d+",
    r"\beffective\s+from\b",
    r"\beffective\s+date\b",
    r"\bwhen\s+was\s+(it|this)\s+(changed|updated|amended|revised)\b",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _TEMPORAL_KEYWORDS]


def detect_temporal_intent(query: str) -> bool:
    """Return ``True`` if *query* expresses temporal / version-comparison intent.

    >>> detect_temporal_intent("how has the lending guideline changed?")
    True
    >>> detect_temporal_intent("what is the LTV ratio?")
    False
    """
    if not query or not query.strip():
        return False
    return any(pat.search(query) for pat in _COMPILED_PATTERNS)
