"""
Lightweight rule-based query triage for regulatory assistant routing.

Design choice: regex + keyword matching — fast, deterministic, no ML
dependency. Easy to extend by adding patterns to each intent bucket.

Returned classes:
- ``fact_retrieval``
- ``timeline_analysis``
- ``drafting_request``
"""

from __future__ import annotations

import re
from typing import List, Literal

IntentClass = Literal["fact_retrieval", "timeline_analysis", "drafting_request"]

# ---------------------------------------------------------------------------
# Patterns (case-insensitive).  Each entry is compiled once at import time.
# ---------------------------------------------------------------------------
_TIMELINE_PATTERNS: List[str] = [
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

_DRAFTING_PATTERNS: List[str] = [
    # direct drafting language
    r"\bdraft\b.*\b(policy|procedure|sop|guideline|framework|document|template)\b",
    r"\b(create|prepare|generate|write|compose)\b.*\b(policy|procedure|sop|guideline|framework|document|template)\b",
    r"\b(policy\s+draft|draft\s+policy)\b",

    # compliance policy generation cues
    r"\bkyc\b.*\bpolicy\b",
    r"\bprivacy\b.*\bpolicy\b",
    r"\bdata\s+retention\b.*\bpolicy\b",
    r"\bboard\s+approval\b.*\b(policy|document)\b",
]

_COMPILED_TIMELINE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _TIMELINE_PATTERNS]
_COMPILED_DRAFTING_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _DRAFTING_PATTERNS]


def _score_matches(query: str, patterns: List[re.Pattern[str]]) -> int:
    return sum(1 for pat in patterns if pat.search(query))


def triage_query_intent(query: str) -> IntentClass:
    """Classify query intent into fact/timeline/drafting buckets.

    >>> triage_query_intent("what are the latest KYC rules?")
    'fact_retrieval'
    >>> triage_query_intent("how has digital lending changed since 2022?")
    'timeline_analysis'
    >>> triage_query_intent("draft a KYC policy for an NBFC")
    'drafting_request'
    """
    if not query or not query.strip():
        return "fact_retrieval"

    timeline_score = _score_matches(query, _COMPILED_TIMELINE_PATTERNS)
    drafting_score = _score_matches(query, _COMPILED_DRAFTING_PATTERNS)

    # Drafting takes precedence on ties because policy generation requests
    # can include temporal language as context (e.g., "draft policy for latest updates").
    if drafting_score > 0 and drafting_score >= timeline_score:
        return "drafting_request"
    if timeline_score > 0:
        return "timeline_analysis"
    return "fact_retrieval"


def detect_temporal_intent(query: str) -> bool:
    """Backward-compatible helper retained for legacy callers.

    >>> detect_temporal_intent("how has the lending guideline changed?")
    True
    >>> detect_temporal_intent("what is the LTV ratio?")
    False
    """
    return triage_query_intent(query) == "timeline_analysis"
