"""Phase 7 — Intent gate: classify query before retrieval (Architecture §8.1).

Two-stage:
1. Cheap regex pre-filter for obvious advisory/performance — no LLM call.
2. Groq llama-3.1-8b-instant JSON-mode classification as authoritative backstop.

Covered schemes are embedded in the gate prompt so the LLM can identify out_of_scope.
"""
from __future__ import annotations

import json
import re

from app.client import chat_with_retry
from app.config import CONFIG_DIR, load_corpus
from app.schemas import GateResult

_GATE_MODEL = "llama-3.1-8b-instant"

# Regex pre-filter — checked in order: comparison first, then advisory, then performance.
# "comparison" covers cross-fund return ranking queries we can answer factually.
# "advisory" is narrow: unambiguous recommendation/opinion asks only.
# "performance" is the fallback for single-fund return questions we still refuse.
_COMPARISON_RE = re.compile(
    r"("
    r"(highest|best|lowest|worst|top)\s+(return|performing|performer)"
    r"|compare\s+(returns?|performance)"
    r"|which\s+fund\s+(has|gave|gives|performed|outperformed)"
    r"|return(s)?\s+comparison"
    r"|rank(ed|ing)?\s+(by\s+)?(return|performance)"
    r")",
    re.I,
)
_ADVISORY_RE = re.compile(
    r"\b(should\s+i|is\s+it\s+(good|bad|worth|safe)|better\s+than|worse\s+than"
    r"|which\s+(fund\s+is\s+better|is\s+(better|best|safer|riskier))"
    r"|recommend|advice|suggest|beat\s+inflation|outperform)\b",
    re.I,
)
_PERFORMANCE_RE = re.compile(
    r"\b(cagr|profit|loss|how\s+much\s+(will|can|would)|grow\s+(my\s+)?money"
    r"|xirr|irr|compounded|annualised|annualized)\b",
    re.I,
)

# Canonical scheme name → scheme_id mapping (used to resolve gate output → id for filtering)
_SCHEME_ALIASES: dict[str, str] = {}


def _build_alias_map() -> dict[str, str]:
    if _SCHEME_ALIASES:
        return _SCHEME_ALIASES
    for s in load_corpus():
        _SCHEME_ALIASES[s.name.lower()] = s.scheme_id
        # add common short forms
        words = s.name.lower().split()
        if len(words) >= 2:
            _SCHEME_ALIASES[" ".join(words[:2])] = s.scheme_id
    return _SCHEME_ALIASES


def _scheme_id_for(name: str | None) -> str | None:
    if not name:
        return None
    aliases = _build_alias_map()
    return aliases.get(name.lower())


def _gate_prompt() -> str:
    path = CONFIG_DIR / "prompts" / "gate_intent.txt"
    return path.read_text(encoding="utf-8")


def classify(query: str) -> GateResult:
    """Classify query intent. Regex short-circuits obvious cases; LLM handles the rest."""
    # --- stage 1: regex pre-filter (comparison checked before advisory/performance) ---
    if _COMPARISON_RE.search(query):
        return GateResult(intent="comparison", reason="matched cross-fund comparison pre-filter")
    if _ADVISORY_RE.search(query):
        return GateResult(intent="advisory", reason="matched advisory keyword pre-filter")
    if _PERFORMANCE_RE.search(query):
        return GateResult(intent="performance", reason="matched performance keyword pre-filter")

    # --- stage 2: LLM classification ---
    raw = chat_with_retry(
        model=_GATE_MODEL,
        messages=[
            {"role": "system", "content": _gate_prompt()},
            {"role": "user", "content": query},
        ],
        temperature=0,
        max_tokens=200,
        response_format={"type": "json_object"},
    )

    try:
        data = json.loads(raw)
        intent = data.get("intent", "unclear")
        scheme_name = data.get("scheme_mentioned") or None
        reason = data.get("reason", "")
        return GateResult(
            intent=intent,
            scheme_mentioned=scheme_name,
            reason=reason,
        )
    except (json.JSONDecodeError, ValueError):
        return GateResult(intent="unclear", reason="gate response could not be parsed")


def scheme_id_from_gate(result: GateResult) -> str | None:
    """Resolve the gate's scheme_mentioned string to a corpus scheme_id for retrieval."""
    return _scheme_id_for(result.scheme_mentioned)
