"""Load + validate config/corpus.yaml and config/pipeline.yaml (Phase 1)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from app.schemas import Scheme

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CLEANED_DIR = DATA_DIR / "cleaned"

# ET factsheet URL contract — corpus is locked to these (ProblemStatement 4.1.1).
ET_URL_RE = re.compile(
    r"^https://economictimes\.indiatimes\.com/[^/]+/mffactsheet/schemeid-\d+\.cms$"
)


def load_corpus(path: Path | None = None) -> list[Scheme]:
    """Return the 5 locked schemes; fail loudly on a malformed corpus."""
    path = path or (CONFIG_DIR / "corpus.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("schemes") or []
    if not entries:
        raise ValueError(f"No schemes found in {path}")

    schemes = [Scheme(**e) for e in entries]

    # validation: unique ids + valid ET URLs
    ids = [s.scheme_id for s in schemes]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate scheme_id in {path}: {ids}")
    for s in schemes:
        if not ET_URL_RE.match(s.url):
            raise ValueError(
                f"Scheme {s.scheme_id} ({s.name}) has a non-ET-factsheet URL: {s.url}"
            )
    return schemes


def load_pipeline(path: Path | None = None) -> dict[str, Any]:
    path = path or (CONFIG_DIR / "pipeline.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    # quick self-check (Phase 1 DoD)
    schemes = load_corpus()
    pipe = load_pipeline()
    print(f"Loaded {len(schemes)} schemes:")
    for s in schemes:
        print(f"  [{s.scheme_id}] {s.name} ({s.amc}, {s.category})")
    print(f"Embedding model: {pipe['embedding']['model']}")
    print(f"Generation model: {pipe['generation']['model']}")
    assert len(schemes) == 5, "expected exactly 5 schemes"
    print("OK: config valid.")
