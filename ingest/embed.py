"""Phase 5 — local BGE embeddings via sentence-transformers.

Model choice: bge-small-en-v1.5 (384-dim, ~130 MB).
Rationale: corpus is 35 short chunks (<110 tokens each); scheme-name prefix already
does the inter-fund disambiguation. bge-large adds no measurable retrieval gain here
and is 10x bigger. Swap via pipeline.yaml embedding.model — a full re-index is needed
when the model changes because embedding spaces are not comparable across models.

BGE convention: documents are embedded as-is; queries get the task instruction prefix.
This module applies the prefix automatically via is_query=True.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Sequence

from sentence_transformers import SentenceTransformer

from app.config import load_pipeline

_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
_DEFAULT_INSTRUCTION = "Represent this sentence for searching relevant passages:"


@lru_cache(maxsize=1)
def _load_model(model_name: str) -> SentenceTransformer:
    """Load and cache the model (downloaded on first call, cached locally after)."""
    return SentenceTransformer(model_name)


def _get_config() -> tuple[str, str]:
    pipe = load_pipeline()
    emb = pipe.get("embedding", {})
    model = emb.get("model", _DEFAULT_MODEL)
    instruction = emb.get("query_instruction", _DEFAULT_INSTRUCTION)
    return model, instruction


def embed(texts: Sequence[str], is_query: bool = False) -> list[list[float]]:
    """Return embedding vectors for texts.

    Args:
        texts: one or more strings to embed.
        is_query: if True, prepend the BGE query instruction to each string.
    """
    model_name, instruction = _get_config()
    model = _load_model(model_name)

    if is_query:
        inputs = [f"{instruction} {t}" for t in texts]
    else:
        inputs = list(texts)

    vectors = model.encode(inputs, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vectors]


def embed_one(text: str, is_query: bool = False) -> list[float]:
    return embed([text], is_query=is_query)[0]


if __name__ == "__main__":
    model_name, _ = _get_config()
    print(f"Model: {model_name}")
    v = embed_one("What is the expense ratio?", is_query=True)
    print(f"Vector dim: {len(v)}, first 4 values: {[round(x, 4) for x in v[:4]]}")
    print("OK: embed works.")
