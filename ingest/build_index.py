"""Phase 5 — End-to-end ingestion CLI: scrape → clean → chunk → embed → upsert.

Usage:
    python -m ingest.build_index              # all 5 schemes
    python -m ingest.build_index --scheme 16280   # single scheme
    python -m ingest.build_index --skip-scrape    # chunk+embed only (raw HTML already present)

Writes data/chroma/manifest.json on completion with chunk counts and build metadata.
Re-running is safe (idempotent upserts by chunk_id).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from app.config import CLEANED_DIR, RAW_DIR, ensure_dirs, load_corpus, load_pipeline
from app.schemas import CleanedDoc
from ingest.chunk import chunk_doc
from ingest.clean import clean_scheme, render_text
from ingest.embed import embed, _get_config
from ingest.scrape import ScrapeError, scrape_scheme
from ingest.store import collection_stats, upsert_chunks, _chroma_path


def _load_doc(scheme_id: str) -> CleanedDoc | None:
    path = CLEANED_DIR / f"{scheme_id}.json"
    if not path.exists():
        return None
    return CleanedDoc(**json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ChromaDB index (Phase 5)")
    parser.add_argument("--scheme", help="index a single scheme_id (default: all)")
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="skip scraping; use existing data/raw HTML (must have been scraped before)",
    )
    args = parser.parse_args()

    ensure_dirs()
    pipe = load_pipeline()
    sc = pipe.get("scrape", {})
    chunking = pipe.get("chunking", {})
    max_tokens = int(chunking.get("max_tokens", 256))

    schemes = load_corpus()
    if args.scheme:
        schemes = [s for s in schemes if s.scheme_id == args.scheme]
        if not schemes:
            print(f"ERROR: scheme_id '{args.scheme}' not found in corpus.yaml", file=sys.stderr)
            return 1

    model_name, _ = _get_config()
    print(f"Embedding model : {model_name}")
    print(f"Vector store    : {_chroma_path()}")
    print(f"Schemes to index: {len(schemes)}")
    print()

    total_chunks = 0
    indexed: list[str] = []

    for s in schemes:
        print(f"[{s.scheme_id}] {s.name}")

        # --- scrape ---
        if not args.skip_scrape:
            try:
                scrape_scheme(
                    s,
                    user_agent=sc.get("user_agent", "Mozilla/5.0"),
                    timeout=int(sc.get("timeout_seconds", 30)),
                    retries=int(sc.get("retries", 3)),
                )
                print(f"  scraped")
            except ScrapeError as exc:
                raw_exists = (RAW_DIR / f"{s.scheme_id}.html").exists()
                if raw_exists:
                    print(f"  scrape failed ({exc}), using cached HTML")
                else:
                    print(f"  scrape FAILED ({exc}), no cached HTML — skipping", file=sys.stderr)
                    continue
        else:
            if not (RAW_DIR / f"{s.scheme_id}.html").exists():
                print(f"  no raw HTML — run without --skip-scrape first", file=sys.stderr)
                continue

        # --- clean ---
        meta_path = RAW_DIR / f"{s.scheme_id}.meta.json"
        fetched_at = (
            json.loads(meta_path.read_text(encoding="utf-8")).get("fetched_at", "unknown")
            if meta_path.exists()
            else "unknown"
        )
        raw_html = (RAW_DIR / f"{s.scheme_id}.html").read_text(encoding="utf-8")
        doc = clean_scheme(s, raw_html, fetched_at)

        txt = render_text(doc)
        (CLEANED_DIR / f"{s.scheme_id}.txt").write_text(txt, encoding="utf-8")
        (CLEANED_DIR / f"{s.scheme_id}.json").write_text(
            doc.model_dump_json(indent=2), encoding="utf-8"
        )
        print(f"  cleaned: {len(doc.fund_details) + len(doc.key_facts) + len(doc.summary_facts)} fact fields")

        # --- chunk ---
        chunks = chunk_doc(doc, max_tokens=max_tokens)
        print(f"  chunked: {len(chunks)} chunks")

        # --- embed ---
        texts = [c.document for c in chunks]
        vectors = embed(texts, is_query=False)
        print(f"  embedded: {len(vectors)} vectors (dim={len(vectors[0])})")

        # --- upsert ---
        upsert_chunks(chunks, vectors)
        print(f"  upserted to ChromaDB (idempotent)")

        total_chunks += len(chunks)
        indexed.append(s.scheme_id)

    # --- manifest ---
    stats = collection_stats()
    manifest = {
        "build_date": str(date.today()),
        "embedding_model": model_name,
        "total_chunks": total_chunks,
        "chunks_per_scheme": stats,
        "schemes_indexed": indexed,
    }
    chroma_dir = _chroma_path()
    import os
    os.makedirs(chroma_dir, exist_ok=True)
    manifest_path = f"{chroma_dir}/manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDone: {total_chunks} chunks across {len(indexed)} scheme(s).")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
