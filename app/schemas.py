"""Pydantic models shared across the pipeline (Architecture sections 6.5, 8.1, 9.1)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Scheme(BaseModel):
    """One corpus entry from config/corpus.yaml (the 5 locked ET factsheets)."""

    scheme_id: str
    name: str
    amc: str
    category: str
    url: str


class CleanedDoc(BaseModel):
    """Output of the clean step (Phase 3) — reviewable structured facts per scheme."""

    scheme_id: str
    name: str
    amc: str
    category: str
    source_url: str
    as_of_date: str  # ISO date the page was scraped (drives the "Last updated" footer)

    # extracted, normalized fact fields (any may be empty if absent on the page)
    fund_details: dict[str, str] = Field(default_factory=dict)   # table key->value
    key_facts: dict[str, str] = Field(default_factory=dict)      # prose highlights label->sentence
    summary_facts: dict[str, str] = Field(default_factory=dict)  # summary list label->value
    performance: dict[str, str] = Field(default_factory=dict)    # returns / since-launch (reference only)
    objective: Optional[str] = None
    extra_notes: list[str] = Field(default_factory=list)         # e.g. lock-in sentences


# --- models used by later phases (defined now for stability) ---


class Chunk(BaseModel):
    chunk_id: str
    document: str
    scheme: str
    scheme_id: str
    amc: str
    category: str
    section: str
    source_url: str
    as_of_date: str


class Hit(BaseModel):
    """One retrieved chunk from ChromaDB, with similarity score."""

    chunk_id: str
    chunk_text: str
    source_url: str
    scheme: str
    scheme_id: str
    amc: str
    category: str
    section: str
    as_of_date: str
    similarity: float  # cosine similarity, 0–1


class GateResult(BaseModel):
    intent: Literal["factual", "advisory", "performance", "comparison", "out_of_scope", "unclear"]
    scheme_mentioned: Optional[str] = None
    reason: str = ""


class ReturnRow(BaseModel):
    """One fund's return for a given period — used in comparison answers."""
    scheme: str
    category: str
    return_pct: float
    source_url: str


class Answer(BaseModel):
    answer_type: Literal["fact", "refusal", "comparison"]
    text: str
    citation_url: Optional[str] = None
    as_of_date: Optional[str] = None
    # populated only for answer_type="comparison"
    comparison_period: Optional[str] = None
    comparison_rows: list[ReturnRow] = Field(default_factory=list)
