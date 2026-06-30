"""Phase 4 — section-aware chunking from CleanedDoc JSON into Chunk objects.

Strategy: split by logical fact-group from the structured CleanedDoc fields, not
by token window. Each whole factsheet is ~420-490 tokens total, so a 300-500 token
window would collapse a fund into one chunk. Instead we produce 6-8 deterministic,
self-contained chunks per scheme (~35 total across the corpus).

Design rules (Architecture §6.3, pipeline.yaml):
- overlap_tokens = 0  (discrete fact-groups, not continuous prose)
- max_tokens = 256    (safety ceiling only; sections are far smaller)
- prefix_scheme_name  each chunk text starts with "<scheme> (<category>) — "
  so it embeds distinctly across the 5 funds and is citable on its own
- performance section is isolated so generation can apply the link-only rule (§5)
- chunk_id = {scheme_id}-{section}-{n}  (n counts if a section is split at ceiling)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Generator

from app.config import CLEANED_DIR, ensure_dirs, load_corpus, load_pipeline
from app.schemas import Chunk, CleanedDoc

_APPROX_CHARS_PER_TOKEN = 4  # good enough for English; used for ceiling check only


def _token_estimate(text: str) -> int:
    return max(1, len(text) // _APPROX_CHARS_PER_TOKEN)


def _prefix(doc: CleanedDoc) -> str:
    return f"{doc.name} ({doc.category}) — "


def _make_chunk(
    doc: CleanedDoc,
    section: str,
    body: str,
    n: int = 0,
) -> Chunk:
    """Wrap body text (already prefixed) into a fully-stamped Chunk."""
    return Chunk(
        chunk_id=f"{doc.scheme_id}-{section}-{n}",
        document=body,
        scheme=doc.name,
        scheme_id=doc.scheme_id,
        amc=doc.amc,
        category=doc.category,
        section=section,
        source_url=doc.source_url,
        as_of_date=doc.as_of_date,
    )


def _section_overview(doc: CleanedDoc) -> str | None:
    fd = doc.fund_details
    lines: list[str] = [_prefix(doc) + "Fund overview"]
    if fd.get("Fund House"):
        lines.append(f"Fund House: {fd['Fund House']}")
    if fd.get("Launch Date"):
        lines.append(f"Launch Date: {fd['Launch Date']}")
    if fd.get("Type"):
        lines.append(f"Type: {fd['Type']}")
    if doc.objective:
        lines.append(f"Investment Objective: {doc.objective}")
    return "\n".join(lines) if len(lines) > 1 else None


def _section_fees(doc: CleanedDoc) -> str | None:
    kf = doc.key_facts
    lines: list[str] = [_prefix(doc) + "Fees and loads"]
    if kf.get("Expense ratio"):
        lines.append(f"Expense ratio: {kf['Expense ratio']}")
    if kf.get("Exit Load"):
        lines.append(f"Exit Load: {kf['Exit Load']}")
    return "\n".join(lines) if len(lines) > 1 else None


def _section_investment(doc: CleanedDoc) -> str | None:
    mi = doc.key_facts.get("Minimum Investment")
    if not mi:
        return None
    return _prefix(doc) + f"Investment requirements\nMinimum Investment: {mi}"


def _section_risk(doc: CleanedDoc) -> str | None:
    fd = doc.fund_details
    lines: list[str] = [_prefix(doc) + "Risk profile"]
    for key in ("Riskometer", "Risk Grade", "Return Grade"):
        if fd.get(key):
            lines.append(f"{key}: {fd[key]}")
    return "\n".join(lines) if len(lines) > 1 else None


def _section_benchmark(doc: CleanedDoc) -> str | None:
    b = doc.fund_details.get("Benchmark")
    if not b:
        return None
    return _prefix(doc) + f"Benchmark\nBenchmark: {b}"


def _section_nav_size(doc: CleanedDoc) -> str | None:
    kf = doc.key_facts
    lines: list[str] = [_prefix(doc) + "NAV and fund size"]
    if kf.get("Current NAV"):
        lines.append(f"Current NAV: {kf['Current NAV']}")
    if kf.get("Fund Size"):
        lines.append(f"Fund Size: {kf['Fund Size']}")
    return "\n".join(lines) if len(lines) > 1 else None


def _section_performance(doc: CleanedDoc) -> str | None:
    if not doc.performance:
        return None
    lines: list[str] = [
        _prefix(doc) + "Performance (reference only — not for advice)"
    ]
    for k, v in doc.performance.items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines)


def _section_notes(doc: CleanedDoc) -> str | None:
    if not doc.extra_notes:
        return None
    lines = [_prefix(doc) + "Additional notes"]
    lines += [f"- {n}" for n in doc.extra_notes]
    return "\n".join(lines)


# Ordered section builders: (section_name, builder_fn)
_SECTIONS: list[tuple[str, object]] = [
    ("overview", _section_overview),
    ("fees", _section_fees),
    ("investment", _section_investment),
    ("risk", _section_risk),
    ("benchmark", _section_benchmark),
    ("nav_size", _section_nav_size),
    ("performance", _section_performance),
    ("notes", _section_notes),
]


def chunk_doc(doc: CleanedDoc, max_tokens: int = 256) -> list[Chunk]:
    """Return all non-empty chunks for one scheme, in section order."""
    chunks: list[Chunk] = []
    for section, builder in _SECTIONS:
        text = builder(doc)  # type: ignore[operator]
        if not text or not text.strip():
            continue
        if _token_estimate(text) > max_tokens:
            # warn only — splitting is a future concern; current sections are well under ceiling
            print(
                f"  WARNING [{doc.scheme_id}] section '{section}' "
                f"~{_token_estimate(text)} tokens > {max_tokens} ceiling",
                file=sys.stderr,
            )
        chunks.append(_make_chunk(doc, section, text))
    return chunks


def chunk_all(max_tokens: int = 256) -> Generator[tuple[str, list[Chunk]], None, None]:
    """Yield (scheme_id, chunks) for every cleaned JSON in CLEANED_DIR."""
    for json_path in sorted(CLEANED_DIR.glob("*.json")):
        if json_path.stem.startswith("_"):
            continue
        doc = CleanedDoc(**json.loads(json_path.read_text(encoding="utf-8")))
        yield doc.scheme_id, chunk_doc(doc, max_tokens=max_tokens)


def main() -> int:
    parser = argparse.ArgumentParser(description="Chunk cleaned factsheets (Phase 4)")
    parser.add_argument("--scheme", help="chunk a single scheme_id (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="print chunks, don't write")
    args = parser.parse_args()

    ensure_dirs()
    pipe = load_pipeline()
    max_tokens = int(pipe.get("chunking", {}).get("max_tokens", 256))

    schemes = load_corpus()
    target_ids = {args.scheme} if args.scheme else {s.scheme_id for s in schemes}

    total_chunks = 0
    for scheme_id, chunks in chunk_all(max_tokens=max_tokens):
        if scheme_id not in target_ids:
            continue
        scheme_name = chunks[0].scheme if chunks else scheme_id
        print(f"[{scheme_id}] {scheme_name}: {len(chunks)} chunks")
        for c in chunks:
            est = _token_estimate(c.document)
            print(f"  {c.chunk_id:<30}  ~{est:>3} tokens  |  {c.document[:60].replace(chr(10), ' ')}...")
            if args.dry_run:
                print()
                print(c.document)
                print()
        total_chunks += len(chunks)

    print(f"\nTotal: {total_chunks} chunks across {len(target_ids)} scheme(s).")
    if args.dry_run:
        print("(dry-run — nothing written; pass chunks to store.py to upsert)")
    else:
        print("Chunks ready. Run ingest/store.py (Phase 5) to upsert into ChromaDB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
