"""Cross-fund return comparison — reads cleaned JSONs directly (no LLM, no hallucination).

Called only when gate intent == "comparison". Detects the requested time period,
extracts trailing returns for all funds, ranks them, and returns a structured Answer
with the ranked table and a mandatory disclaimer.
"""
from __future__ import annotations

import json
import re

from app.config import CLEANED_DIR
from app.schemas import Answer, CleanedDoc, ReturnRow

_DISCLAIMER = (
    "Past performance is not indicative of future returns. "
    "This is factual data from official Economic Times factsheets — not investment advice."
)

# Maps query keywords to the label used inside trailing-returns text e.g. "19.45% (3yr)"
_PERIOD_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(since\s+launch|inception)\b", re.I), "since launch"),
    (re.compile(r"\b(5[\s-]?yr|5[\s-]?year|five[\s-]?year)\b", re.I), "5yr"),
    (re.compile(r"\b(3[\s-]?yr|3[\s-]?year|three[\s-]?year)\b", re.I), "3yr"),
    (re.compile(r"\b(1[\s-]?yr|1[\s-]?year|one[\s-]?year)\b", re.I), "1yr"),
]
_DEFAULT_PERIOD = "3yr"

_PERIOD_LABELS = {
    "1yr": "1-year",
    "3yr": "3-year",
    "5yr": "5-year",
    "since launch": "since-launch",
}


def _detect_period(query: str) -> str:
    for pattern, period in _PERIOD_MAP:
        if pattern.search(query):
            return period
    return _DEFAULT_PERIOD


def _parse_return(trailing_text: str, period: str) -> float | None:
    """Extract the return % for a given period label from trailing-returns prose."""
    if period == "since launch":
        m = re.search(r"(-?\d+\.?\d*)\s*%\s*\(since\s+launch\)", trailing_text, re.I)
    else:
        m = re.search(rf"(-?\d+\.?\d*)\s*%\s*\({re.escape(period)}\)", trailing_text, re.I)
    return float(m.group(1)) if m else None


def _load_all_docs() -> list[CleanedDoc]:
    docs = []
    for path in sorted(CLEANED_DIR.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        docs.append(CleanedDoc(**json.loads(path.read_text(encoding="utf-8"))))
    return docs


def compare(query: str) -> Answer:
    """Return a ranked comparison answer for the detected time period."""
    period = _detect_period(query)
    label = _PERIOD_LABELS.get(period, period)

    rows: list[ReturnRow] = []
    missing: list[str] = []

    for doc in _load_all_docs():
        trailing = doc.performance.get("Trailing/Category Returns", "")
        ret = _parse_return(trailing, period)
        if ret is None:
            # fall back to "Return Since Launch" if asking for since-launch
            if period == "since launch":
                sl = doc.performance.get("Return Since Launch", "")
                m = re.search(r"(-?\d+\.?\d*)", sl)
                ret = float(m.group(1)) if m else None
        if ret is not None:
            rows.append(ReturnRow(
                scheme=doc.name,
                category=doc.category,
                return_pct=ret,
                source_url=doc.source_url,
            ))
        else:
            missing.append(doc.name)

    if not rows:
        return Answer(
            answer_type="refusal",
            text=f"I could not find {label} return data for any of the covered funds. Please check the factsheets directly.",
        )

    rows.sort(key=lambda r: r.return_pct, reverse=True)
    winner = rows[0]

    # Summary sentence
    ranked = ", ".join(
        f"{r.scheme} ({r.return_pct:+.2f}%)" for r in rows
    )
    summary = (
        f"Based on {label} trailing returns from official ET factsheets, "
        f"{winner.scheme} has the highest {label} return at {winner.return_pct:+.2f}%. "
        f"Ranked: {ranked}."
    )

    return Answer(
        answer_type="comparison",
        text=summary,
        citation_url=None,
        as_of_date=rows[0].source_url and _load_all_docs()[0].as_of_date,
        comparison_period=label,
        comparison_rows=rows,
    )
