"""
Predefined / canned responses for SAARTHI.

Handles greetings, identity questions, out-of-scope queries, and other
common interactions that do NOT require the RAG pipeline.

The public entry-point is ``get_predefined_response(query)`` which returns
a response string if the query matches a known pattern, or ``None`` if
the query should be forwarded to the RAG pipeline.
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Pattern → response registry
# ---------------------------------------------------------------------------
# Each entry is a tuple of (compiled_regex, response_string).
# The first match wins, so more specific patterns should come first.

_RESPONSE_RULES: list[tuple[re.Pattern, str]] = []


def _rule(pattern: str, response: str) -> None:
    """Register a pattern→response rule (called at module load time)."""
    _RESPONSE_RULES.append((re.compile(pattern, re.IGNORECASE), response))


# ── Identity / about ────────────────────────────────────────────────────
_rule(
    r"\b(who|what)\s+(are|r)\s+you\b",
    "I'm **SAARTHI** — your AI assistant for exploring RBI regulatory "
    "guidelines. I specialise in answering questions using indexed "
    "circulars and documents covering digital lending norms, KYC master "
    "directions, data protection (DPDP Act), compliance obligations, "
    "and more! I can also compare how regulations have changed across "
    "different versions.",
)

_rule(
    r"\bwhat\s+is\s+saarthi\b",
    "**SAARTHI** is a RAG-powered regulatory Q&A assistant that retrieves "
    "information from indexed RBI circulars and related documents — "
    "including digital lending guidelines, KYC master directions, and "
    "the DPDP Act — and provides accurate, source-backed answers to "
    "your compliance questions.",
)

_rule(
    r"\bwho\s+am\s+i\b",
    "You're the one asking the questions here! 😄 I'm **SAARTHI**, your "
    "regulatory assistant. I don't have information about you, but I'm "
    "ready to help you navigate RBI guidelines. What would you like to know?",
)

_rule(
    r"\bwho\s+made\s+you\b|\bwho\s+created\s+you\b|\bwho\s+built\s+you\b|\byour\s+creator\b",
    "I was built as part of an academic project focused on making regulatory "
    "compliance more accessible through AI. I use LangChain, FAISS, and "
    "Ollama under the hood to retrieve and reason over RBI circulars. "
    "Got a regulatory question? I'm here to help!",
)

_rule(
    r"\b(what\s+can\s+you\s+do|what\s+are\s+your\s+capabilities|how\s+can\s+you\s+help|help\s+me)\b",
    "Here's what I can do:\n\n"
    "- **Answer regulatory questions** — Ask about RBI guidelines on digital "
    "lending, KYC norms, data protection (DPDP Act), LSPs, and more.\n"
    "- **Cite sources** — Every answer is backed by specific sections from "
    "indexed circulars.\n"
    "- **Track changes** — I automatically detect when you're asking about "
    "changes and compare regulation versions side-by-side.\n\n"
    "Try asking something like: *\"What are the key digital lending guidelines?\"*",
)

# ── Greetings ───────────────────────────────────────────────────────────
_rule(
    r"^(hi|hello|hey|howdy|hola|namaste|namaskar|good\s*(morning|afternoon|evening))[\s!.,?]*$",
    "Hello! 👋 I'm **SAARTHI**, your regulatory Q&A assistant. "
    "Ask me anything about RBI guidelines and I'll find the answer "
    "from indexed circulars. How can I help you today?",
)

# ── Gratitude ───────────────────────────────────────────────────────────
_rule(
    r"^(thanks|thank\s*you|thx|ty|much\s+appreciated|appreciate\s+it)[\s!.,]*$",
    "You're welcome! 😊 If you have more questions about RBI regulations, "
    "feel free to ask anytime. That's what I'm here for!",
)

# ── Farewell ────────────────────────────────────────────────────────────
_rule(
    r"^(bye|goodbye|see\s+you|take\s+care|good\s*night|cya|later)[\s!.,]*$",
    "Goodbye! 👋 Feel free to come back whenever you have more regulatory "
    "questions. Have a great day!",
)

# ── Weather / off-topic chitchat ────────────────────────────────────────
_rule(
    r"\b(weather|temperature|rain(ing)?|sunny|forecast)\b",
    "I appreciate the curiosity, but I'm not a weather assistant! ☁️ "
    "I'm **SAARTHI**, and my expertise lies in RBI regulatory guidelines. "
    "Try asking me something like: *\"What are the disclosure requirements "
    "for digital lending?\"*",
)

_rule(
    r"\b(tell\s+(me\s+)?a\s+joke|funny|make\s+me\s+laugh)\b",
    "I'd love to lighten the mood, but my training is all about RBI "
    "regulations — and trust me, compliance is no joke! 😄 "
    "Ask me a regulatory question and I'll do my best to help.",
)

_rule(
    r"\b(who\s+is\s+the\s+president|prime\s+minister|capital\s+of|movie|song|recipe|cook|sport|cricket|football)\b",
    "That's a great question, but it's outside my area of expertise! "
    "I'm **SAARTHI**, a specialised assistant for RBI regulatory guidelines. "
    "I work best with questions about digital lending, KYC, compliance "
    "norms, and related topics. What can I help you with?",
)

_rule(
    r"\b(write\s+(me\s+)?(a\s+)?(code|program|script|essay|poem|story|email|letter))\b",
    "I'm not a general-purpose writing assistant — I'm **SAARTHI**, focused "
    "on answering questions about RBI regulatory documents. If you need "
    "help understanding a regulation or compliance requirement, I'm your go-to!",
)

# ── Catch-all for very short / empty-ish input ──────────────────────────
_rule(
    r"^[\s?!.]*$",
    "It looks like you haven't typed a question yet. "
    "Ask me anything about RBI regulatory guidelines — for example: "
    "*\"What are the key digital lending guidelines?\"*",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_predefined_response(query: str) -> Optional[str]:
    """Return a canned response if *query* matches a known pattern.

    Returns ``None`` when no rule matches, signalling that the query
    should be processed by the RAG pipeline.
    """
    if not query:
        return None

    cleaned = query.strip()
    for pattern, response in _RESPONSE_RULES:
        if pattern.search(cleaned):
            return response

    return None
