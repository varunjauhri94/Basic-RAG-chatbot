"""Phase 7 — PII scrubber.

Runs on the raw query BEFORE any logging or LLM call (Architecture §8.2).
Patterns match Indian financial context: PAN, Aadhaar, phone, email, account numbers.
"""
from __future__ import annotations

import re

_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "[PAN]"),
    (re.compile(r"\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b"), "[AADHAAR]"),
    (re.compile(r"(\+91[\s\-]?)?[6-9][0-9]{9}\b"), "[PHONE]"),
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b[0-9]{8,18}\b"), "[ACCT]"),
]


def scrub(text: str) -> str:
    """Return text with all PII patterns replaced by safe tags."""
    for pattern, tag in _RULES:
        text = pattern.sub(tag, text)
    return text
