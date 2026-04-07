"""Input sanitization helpers shared by request schemas."""

from __future__ import annotations

import re

# Keep tabs/newlines when requested, but strip non-printable control chars.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def sanitize_text(value: object, *, collapse_whitespace: bool) -> str:
    text = str(value or "")
    text = _CONTROL_CHARS_RE.sub("", text)
    text = text.replace("\u200b", "")

    if collapse_whitespace:
        text = " ".join(text.split())
    else:
        text = text.strip()

    return text
