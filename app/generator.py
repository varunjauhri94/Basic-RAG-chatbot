"""Phase 8 — Facts-only generation (Architecture §9).

Builds source-tagged context blocks from retrieved hits, calls Groq
llama-3.3-70b-versatile in JSON mode, validates the Answer schema with Pydantic.
The orchestrator does an additional post-generation validation pass (§9.4).
"""
from __future__ import annotations

import json

from app.client import chat_with_retry
from app.config import CONFIG_DIR
from app.schemas import Answer, Hit

_GEN_MODEL = "llama-3.3-70b-versatile"


def _system_prompt() -> str:
    return (CONFIG_DIR / "prompts" / "system_facts_only.txt").read_text(encoding="utf-8")


def _build_context(hits: list[Hit]) -> str:
    """Render hits as fenced, source-tagged blocks the model treats as pure data."""
    blocks: list[str] = []
    for h in hits:
        blocks.append(
            f'<source url="{h.source_url}" as_of="{h.as_of_date}">\n'
            f"{h.chunk_text}\n"
            f"</source>"
        )
    return "\n\n".join(blocks)


def generate(query: str, hits: list[Hit]) -> Answer:
    """Generate a facts-only Answer grounded in the provided hits.

    Returns answer_type='refusal' if hits are empty or the model cannot find the fact.
    """
    if not hits:
        return Answer(
            answer_type="refusal",
            text="I don't have that information in my sources. I can answer questions about expense ratio, exit load, minimum investment, riskometer, benchmark, NAV, and fund size for the 5 covered schemes.",
            citation_url=None,
            as_of_date=None,
        )

    context = _build_context(hits)
    system = _system_prompt() + "\n" + context

    raw = chat_with_retry(
        model=_GEN_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": query},
        ],
        temperature=0,
        max_tokens=512,
        response_format={"type": "json_object"},
    )

    try:
        data = json.loads(raw)
        return Answer.model_validate(data)
    except (json.JSONDecodeError, Exception):
        return Answer(
            answer_type="refusal",
            text="I was unable to produce a verified answer. Please try rephrasing your question.",
            citation_url=None,
            as_of_date=None,
        )
