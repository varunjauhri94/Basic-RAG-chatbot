"""Phase 3 - Clean ET factsheet HTML into reviewable, scheme-scoped facts.

Strips ET chrome (FEATURED FUNDS, tickers, ads, nav) by extracting ONLY three
known structures for the target fund:
  1. "Key Highlights" prose block  -> <b>Label:</b> sentences
  2. Fund-details key-value table   -> Launch Date / Benchmark / Riskometer / ...
  3. Summary list                   -> Expense Ratio, Fund Size (AUM)
Performance/returns are routed to a separate section so the chunk step can drop
them (the assistant is facts-only; no returns/comparison answers).
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from app.config import CLEANED_DIR, RAW_DIR, ensure_dirs, load_corpus
from app.schemas import CleanedDoc, Scheme

# Bold-labelled facts inside the "Key Highlights" prose block.
KEY_HIGHLIGHT_LABELS = [
    "Current NAV",
    "Returns",
    "Fund Size",
    "Expense ratio",
    "Exit Load",
    "Minimum Investment",
]
# Table rows we keep (everything else in the table is ignored).
TABLE_KEYS = {
    "fund house": "Fund House",
    "launch date": "Launch Date",
    "benchmark": "Benchmark",
    "type": "Type",
    "riskometer": "Riskometer",
    "risk grade": "Risk Grade",
    "return grade": "Return Grade",
    "return since launch": "Return Since Launch",  # -> performance
}


def _clean_text(s: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_lib.unescape(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip()


def extract_key_facts(raw_html: str) -> dict[str, str]:
    """Pull the <b>Label:</b> sentences from the main fund's Key Highlights block."""
    idx = raw_html.find("Key Highlights")
    region = raw_html[idx: idx + 9000] if idx >= 0 else raw_html
    facts: dict[str, str] = {}
    for label in KEY_HIGHLIGHT_LABELS:
        m = re.search(
            rf"<b>\s*{re.escape(label)}\s*:?\s*</b>(.*?)(?=<b>|</p>|<div|<section|<h[1-6])",
            region,
            re.S | re.I,
        )
        if m:
            # drop a trailing list marker like "<br> 2." that belongs to the NEXT item
            raw_val = re.sub(r"(?:<br\s*/?>\s*\d+\.\s*)+$", "", m.group(1), flags=re.I)
            val = _clean_text(raw_val)
            if val:
                facts[label] = val
    return facts


def _pick_facts_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        txt = table.get_text(" ", strip=True).lower()
        if "launch date" in txt and "riskometer" in txt:
            return table
    return None


def extract_table(soup: BeautifulSoup) -> dict[str, str]:
    table = _pick_facts_table(soup)
    out: dict[str, str] = {}
    if not table:
        return out
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) >= 2:
            key = cells[0].get_text(" ", strip=True).lower()
            if key in TABLE_KEYS:
                val = cells[1].get_text(" ", strip=True)
                if val:
                    out[TABLE_KEYS[key]] = html_lib.unescape(val)
    return out


def extract_summary_facts(raw_html: str) -> dict[str, str]:
    """The compact summary list: <p class="...fs13...">Label:<br>Value</p>."""
    out: dict[str, str] = {}
    for m in re.finditer(
        r'<p[^>]*class="[^"]*fs13[^"]*"[^>]*>\s*([A-Za-z ./]+?):\s*<br\s*/?>\s*([^<]+)</p>',
        raw_html,
        re.I,
    ):
        label = _clean_text(m.group(1))
        val = _clean_text(m.group(2))
        if label and val:
            out[label] = val
    return out


def extract_objective(soup: BeautifulSoup) -> str | None:
    table = _pick_facts_table(soup)
    if not table:
        return None
    p = table.find_previous("p")
    if p:
        txt = p.get_text(" ", strip=True)
        if len(txt) > 50 and " " in txt:
            return html_lib.unescape(re.sub(r"\s+", " ", txt))
    return None


def extract_notes(raw_html: str) -> list[str]:
    """Capture category-specific sentences (e.g. ELSS lock-in) if present."""
    text = _clean_text(raw_html)
    notes: list[str] = []
    for m in re.finditer(r"([^.]*?lock[\s-]?in[^.]*\.)", text, re.I):
        sentence = m.group(1).strip()
        if 10 < len(sentence) < 300 and sentence not in notes:
            notes.append(sentence)
    return notes[:3]


def clean_scheme(scheme: Scheme, raw_html: str, fetched_at: str) -> CleanedDoc:
    soup = BeautifulSoup(raw_html, "lxml")

    key_facts = extract_key_facts(raw_html)
    table = extract_table(soup)
    summary = extract_summary_facts(raw_html)

    # split performance/returns out of the factual sets
    performance: dict[str, str] = {}
    if "Returns" in key_facts:
        performance["Trailing/Category Returns"] = key_facts.pop("Returns")
    if "Return Since Launch" in table:
        performance["Return Since Launch"] = table.pop("Return Since Launch")

    return CleanedDoc(
        scheme_id=scheme.scheme_id,
        name=scheme.name,
        amc=scheme.amc,
        category=scheme.category,
        source_url=scheme.url,
        as_of_date=fetched_at,
        fund_details=table,
        key_facts=key_facts,
        summary_facts=summary,
        performance=performance,
        objective=extract_objective(soup),
        extra_notes=extract_notes(raw_html),
    )


def render_text(doc: CleanedDoc) -> str:
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"{doc.name}  (Direct Plan - Growth)")
    lines.append(f"AMC: {doc.amc} | Category: {doc.category}")
    lines.append(f"Source: {doc.source_url}")
    lines.append(f"Last updated from sources: {doc.as_of_date}")
    lines.append("=" * 70)

    def section(title: str, kv: dict[str, str]):
        if kv:
            lines.append(f"\n[{title}]")
            for k, v in kv.items():
                lines.append(f"{k}: {v}")

    section("Fund Details", doc.fund_details)
    section("Summary", doc.summary_facts)
    section("Key Facts", doc.key_facts)
    if doc.objective:
        lines.append("\n[Objective]")
        lines.append(doc.objective)
    if doc.extra_notes:
        lines.append("\n[Notes]")
        for n in doc.extra_notes:
            lines.append(f"- {n}")
    section("Performance (reference only - not for advice)", doc.performance)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean scraped ET factsheets (Phase 3)")
    parser.add_argument("--scheme", help="clean a single scheme_id (default: all)")
    args = parser.parse_args()

    ensure_dirs()
    schemes = load_corpus()
    if args.scheme:
        schemes = [s for s in schemes if s.scheme_id == args.scheme]

    review_blocks: list[str] = []
    done, missing = 0, 0
    for s in schemes:
        html_path = RAW_DIR / f"{s.scheme_id}.html"
        meta_path = RAW_DIR / f"{s.scheme_id}.meta.json"
        if not html_path.exists():
            print(f"[{s.scheme_id}] no raw HTML — run scrape first", file=sys.stderr)
            missing += 1
            continue
        fetched_at = s.url and ""
        fetched_at = (
            json.loads(meta_path.read_text(encoding="utf-8")).get("fetched_at")
            if meta_path.exists()
            else "unknown"
        )
        raw_html = html_path.read_text(encoding="utf-8")
        doc = clean_scheme(s, raw_html, fetched_at)

        text = render_text(doc)
        (CLEANED_DIR / f"{s.scheme_id}.txt").write_text(text, encoding="utf-8")
        (CLEANED_DIR / f"{s.scheme_id}.json").write_text(
            doc.model_dump_json(indent=2), encoding="utf-8"
        )
        review_blocks.append(text)

        n_facts = len(doc.fund_details) + len(doc.key_facts) + len(doc.summary_facts)
        print(f"[{s.scheme_id}] {s.name}: {n_facts} fact fields extracted")
        done += 1

    if review_blocks:
        review = "# Cleaned Factsheets — Review\n\n" + "\n\n".join(
            f"```\n{b}\n```" for b in review_blocks
        )
        (CLEANED_DIR / "_review.md").write_text(review, encoding="utf-8")

    print(f"\nClean complete: {done} cleaned, {missing} missing. Output -> {CLEANED_DIR}")
    print(f"Review all in one file: {CLEANED_DIR / '_review.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
