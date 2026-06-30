"""Phases 2+3 driver - scrape then clean all schemes for review (before chunking)."""
from __future__ import annotations

import sys

from app.config import ensure_dirs, load_corpus, load_pipeline
from ingest.clean import clean_scheme, render_text
from ingest.scrape import ScrapeError, scrape_scheme
from app.config import CLEANED_DIR, RAW_DIR
import json


def main() -> int:
    ensure_dirs()
    pipe = load_pipeline()
    sc = pipe.get("scrape", {})
    ua = sc.get("user_agent", "Mozilla/5.0")
    timeout = int(sc.get("timeout_seconds", 30))
    retries = int(sc.get("retries", 3))

    schemes = load_corpus()
    review_blocks: list[str] = []
    ok = 0

    for s in schemes:
        print(f"[{s.scheme_id}] {s.name}")
        try:
            scrape_scheme(s, user_agent=ua, timeout=timeout, retries=retries)
        except ScrapeError as exc:
            print(f"    scrape SKIPPED: {exc}", file=sys.stderr)
            continue

        meta = json.loads((RAW_DIR / f"{s.scheme_id}.meta.json").read_text(encoding="utf-8"))
        raw_html = (RAW_DIR / f"{s.scheme_id}.html").read_text(encoding="utf-8")
        doc = clean_scheme(s, raw_html, meta["fetched_at"])

        text = render_text(doc)
        (CLEANED_DIR / f"{s.scheme_id}.txt").write_text(text, encoding="utf-8")
        (CLEANED_DIR / f"{s.scheme_id}.json").write_text(doc.model_dump_json(indent=2), encoding="utf-8")
        review_blocks.append(text)
        n = len(doc.fund_details) + len(doc.key_facts) + len(doc.summary_facts)
        print(f"    cleaned: {n} fact fields")
        ok += 1

    if review_blocks:
        review = "# Cleaned Factsheets — Review\n\n" + "\n\n".join(f"```\n{b}\n```" for b in review_blocks)
        (CLEANED_DIR / "_review.md").write_text(review, encoding="utf-8")

    print(f"\nDone: {ok}/{len(schemes)} schemes scraped+cleaned.")
    print(f"Review: {CLEANED_DIR / '_review.md'}  (per-scheme: data/cleaned/<id>.txt / .json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
