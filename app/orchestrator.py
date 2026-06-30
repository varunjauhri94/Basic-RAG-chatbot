"""Phase 9 — Orchestrator: full online query path (Architecture §9.4).

Pipeline: scrub → gate → (refuse or) retrieve → relevance floor → generate →
post-generation validation → assemble final response.

Post-generation validation (independent of model):
  1. sentence count ≤ 3
  2. citation_url is non-null and is a member of the retrieved source_url set
  3. footer assembled from cited chunk's as_of_date

Any validation failure downgrades the answer to a refusal — the facts-only contract
is enforced here, not merely prompted for.
"""
from __future__ import annotations

import re
import sys

from app.comparator import compare
from app.gate import classify, scheme_id_from_gate
from app.generator import generate
from app.retriever import retrieve
from app.scrubber import scrub
from app.schemas import Answer, GateResult, Hit

_AMFI_EDU = "https://www.amfi.org.in/investor-corner/investor-awareness.aspx"
_SEBI_EDU = "https://www.sebi.gov.in/investors.html"

_COVERED = (
    "SBI ELSS Tax Saver Fund, ICICI Prudential BHARAT 22 FOF, "
    "HSBC Midcap Fund, Groww Liquid Fund, Bank of India Flexi Cap Fund"
)


# ---------------------------------------------------------------------------
# Refusal builders
# ---------------------------------------------------------------------------

def _refusal(text: str) -> Answer:
    return Answer(answer_type="refusal", text=text, citation_url=None, as_of_date=None)


def _advisory_refusal() -> Answer:
    return _refusal(
        "I only answer factual questions about mutual fund schemes — I cannot give investment "
        "advice or recommendations. For guidance, please consult a SEBI-registered investment "
        f"advisor or visit AMFI's investor education resources: {_AMFI_EDU}"
    )


def _performance_refusal(scheme_url: str | None) -> Answer:
    base = (
        "I cannot provide return calculations, projections, or performance comparisons. "
        "For official performance data, please refer directly to the scheme's factsheet"
    )
    if scheme_url:
        return _refusal(f"{base}: {scheme_url}")
    return _refusal(f"{base} on the Economic Times mutual fund pages.")


def _out_of_scope_refusal() -> Answer:
    return _refusal(
        f"I only have information about these 5 schemes: {_COVERED}. "
        "Please ask a factual question about one of them (expense ratio, exit load, "
        "minimum investment, riskometer, benchmark, NAV, fund size, etc.)."
    )


def _no_coverage_refusal() -> Answer:
    return _refusal(
        "I don't have that specific information in my sources. I can answer questions about "
        "expense ratio, exit load, minimum investment, riskometer, benchmark, NAV, fund size, "
        f"lock-in period, and fund type for: {_COVERED}."
    )


def _unclear_refusal() -> Answer:
    return _refusal(
        "I couldn't understand what factual information you're looking for. "
        "Could you rephrase? For example: \"What is the expense ratio of the HSBC Midcap Fund?\""
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _count_sentences(text: str) -> int:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return len([p for p in parts if p])


def _validate(answer: Answer, source_urls: set[str]) -> Answer:
    """Independently verify the generated answer; downgrade to refusal if invalid."""
    if answer.answer_type == "refusal":
        return answer

    # rule 1: sentence count
    if _count_sentences(answer.text) > 3:
        return _refusal(
            "I was unable to produce a concise verified answer. Please try rephrasing."
        )

    # rule 2: citation must be from retrieved set
    if not answer.citation_url or answer.citation_url not in source_urls:
        return _refusal(
            "I could not verify the source for this answer. Please try rephrasing."
        )

    return answer


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ask(query: str) -> tuple[Answer, str]:
    """Run the full pipeline for a user query.

    Returns:
        (answer, footer) where footer is the "Last updated" line or empty string.
    """
    # 1. scrub PII before anything touches the query
    clean_query = scrub(query)

    # 2. intent gate
    gate: GateResult = classify(clean_query)

    if gate.intent == "advisory":
        return _advisory_refusal(), ""

    if gate.intent == "comparison":
        return compare(clean_query), ""

    if gate.intent == "performance":
        return _performance_refusal(None), ""

    if gate.intent == "out_of_scope":
        return _out_of_scope_refusal(), ""

    if gate.intent == "unclear":
        return _unclear_refusal(), ""

    # gate.intent == "factual" — proceed to retrieval
    scheme_id = scheme_id_from_gate(gate)
    hits: list[Hit] = retrieve(clean_query, scheme_id=scheme_id)

    if not hits:
        return _no_coverage_refusal(), ""

    # 3. generate
    answer = generate(clean_query, hits)

    # 4. post-generation validation
    source_urls = {h.source_url for h in hits}
    answer = _validate(answer, source_urls)

    # 5. build footer from cited chunk's as_of_date
    footer = ""
    if answer.answer_type == "fact" and answer.citation_url:
        cited_hit = next(
            (h for h in hits if h.source_url == answer.citation_url), hits[0]
        )
        footer = f"Last updated from sources: {cited_hit.as_of_date}"

    return answer, footer


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Mutual Fund FAQ — headless query (Phase 9)")
    parser.add_argument("--query", "-q", required=True, help="Question to ask")
    args = parser.parse_args()

    answer, footer = ask(args.query)

    print(f"\nType   : {answer.answer_type}")
    print(f"Answer : {answer.text}")
    if answer.citation_url:
        print(f"Source : {answer.citation_url}")
    if footer:
        print(f"        {footer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
