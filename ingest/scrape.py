"""Phase 2 - Scrape ET factsheet pages (HTML only).

Fetches each locked ET factsheet, saves a raw snapshot + metadata for review.
Server-rendered pages -> plain requests, no headless browser. No PDF/other types.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import requests

from app.config import RAW_DIR, ensure_dirs, load_corpus, load_pipeline
from app.schemas import Scheme


class ScrapeError(RuntimeError):
    pass


def fetch(url: str, *, user_agent: str, timeout: int = 30, retries: int = 3) -> tuple[str, int]:
    """Return (html, status). Retries 5xx/timeouts; rejects non-HTML responses."""
    headers = {"User-Agent": user_agent, "Accept-Language": "en-IN,en;q=0.9"}
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if resp.status_code >= 500:
                raise ScrapeError(f"server error {resp.status_code}")
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "")
            if "text/html" not in ctype.lower():
                # scope lock: ET HTML factsheets only — never parse PDFs/other types
                raise ScrapeError(f"unexpected content-type '{ctype}' (HTML only)")
            return resp.text, resp.status_code
        except (requests.RequestException, ScrapeError) as exc:
            last_exc = exc
            if attempt < retries:
                backoff = 2 ** attempt
                print(f"    attempt {attempt} failed ({exc}); retrying in {backoff}s")
                time.sleep(backoff)
    raise ScrapeError(f"failed to fetch {url}: {last_exc}")


def scrape_scheme(scheme: Scheme, *, user_agent: str, timeout: int, retries: int) -> Path:
    """Fetch one scheme, write data/raw/{id}.html and {id}.meta.json. Returns the html path."""
    html, status = fetch(scheme.url, user_agent=user_agent, timeout=timeout, retries=retries)
    fetched_at = date.today().isoformat()

    html_path = RAW_DIR / f"{scheme.scheme_id}.html"
    html_path.write_text(html, encoding="utf-8")

    meta = {
        "scheme_id": scheme.scheme_id,
        "name": scheme.name,
        "amc": scheme.amc,
        "category": scheme.category,
        "url": scheme.url,
        "fetched_at": fetched_at,
        "http_status": status,
        "bytes": len(html.encode("utf-8")),
    }
    (RAW_DIR / f"{scheme.scheme_id}.meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return html_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape ET mutual-fund factsheets (Phase 2)")
    parser.add_argument("--scheme", help="scrape a single scheme_id (default: all)")
    args = parser.parse_args()

    ensure_dirs()
    pipe = load_pipeline()
    sc = pipe.get("scrape", {})
    ua = sc.get("user_agent", "Mozilla/5.0")
    timeout = int(sc.get("timeout_seconds", 30))
    retries = int(sc.get("retries", 3))

    schemes = load_corpus()
    if args.scheme:
        schemes = [s for s in schemes if s.scheme_id == args.scheme]
        if not schemes:
            print(f"No scheme with id {args.scheme}", file=sys.stderr)
            return 2

    ok, failed = 0, 0
    for s in schemes:
        print(f"[{s.scheme_id}] {s.name} -> {s.url}")
        try:
            path = scrape_scheme(s, user_agent=ua, timeout=timeout, retries=retries)
            size = path.stat().st_size
            print(f"    saved {path.name} ({size:,} bytes)")
            ok += 1
        except ScrapeError as exc:
            print(f"    SKIPPED: {exc}", file=sys.stderr)
            failed += 1

    print(f"\nScrape complete: {ok} ok, {failed} failed. Raw -> {RAW_DIR}")
    return 1 if failed and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
