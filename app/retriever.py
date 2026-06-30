"""Phase 6 — Retrieval: embed query → ChromaDB → relevance floor → Hit list.

Architecture §7:
- top_k = 4 (tight context, small citation set)
- filter_by_scheme: if gate identifies a scheme, WHERE-filter to avoid cross-scheme contamination
- relevance floor: if best cosine similarity < min_similarity, return empty list (no-coverage signal)
"""
from __future__ import annotations

from app.config import load_pipeline
from app.schemas import Hit
from ingest.embed import embed_one
from ingest.store import get_collection


def retrieve(
    query: str,
    scheme_id: str | None = None,
) -> list[Hit]:
    """Return up to top_k Hit objects, or [] if best similarity is below the floor.

    Args:
        query: the (already-scrubbed) user question.
        scheme_id: if the gate identified a specific scheme, filter to it.
    """
    pipe = load_pipeline()
    ret = pipe.get("retrieval", {})
    top_k = int(ret.get("top_k", 4))
    min_sim = float(ret.get("min_similarity", 0.35))
    filter_by_scheme = bool(ret.get("filter_by_scheme", True))

    vector = embed_one(query, is_query=True)

    col = get_collection()
    where = {"scheme_id": scheme_id} if (scheme_id and filter_by_scheme) else None

    results = col.query(
        query_embeddings=[vector],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    ids = results["ids"][0]
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    # ChromaDB returns cosine distance (0 = identical, 2 = opposite); convert to similarity
    distances = results["distances"][0]
    similarities = [1.0 - (d / 2.0) for d in distances]

    if not ids or max(similarities) < min_sim:
        return []

    hits: list[Hit] = []
    for cid, doc, meta, sim in zip(ids, docs, metas, similarities):
        hits.append(
            Hit(
                chunk_id=cid,
                chunk_text=doc,
                source_url=meta["source_url"],
                scheme=meta["scheme"],
                scheme_id=meta["scheme_id"],
                amc=meta["amc"],
                category=meta["category"],
                section=meta["section"],
                as_of_date=meta["as_of_date"],
                similarity=round(sim, 4),
            )
        )
    return hits


if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) or "What is the exit load of HSBC Midcap Fund?"
    print(f"Query: {query}\n")
    hits = retrieve(query)
    if not hits:
        print("No hits above the relevance floor.")
    for h in hits:
        print(f"[{h.chunk_id}] sim={h.similarity:.3f}  {h.section}")
        print(f"  {h.chunk_text[:120]}...")
        print(f"  source: {h.source_url}")
        print()
