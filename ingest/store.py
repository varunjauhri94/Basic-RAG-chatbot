"""Phase 5 — ChromaDB persistent vector store.

Vector DB choice: ChromaDB (not FAISS).
Rationale: filter_by_scheme=true requires metadata WHERE filtering — native in ChromaDB,
absent in FAISS (which is pure ANN with no metadata layer). ChromaDB also provides
idempotent upsert by chunk_id and persistence without extra code. At 35 chunks there
is no scale argument for FAISS.

Collection: mf_factsheets (persistent at data/chroma/).
Upserts are idempotent — re-running ingestion replaces a chunk in place (same chunk_id
→ same Chroma document id → overwrite). Changing the embedding model requires a
full rebuild: delete data/chroma/ and re-run build_index.
"""
from __future__ import annotations

import chromadb
from chromadb.config import Settings

from app.config import DATA_DIR, load_pipeline
from app.schemas import Chunk


def _get_collection_name() -> str:
    pipe = load_pipeline()
    return pipe.get("vector_store", {}).get("collection", "mf_factsheets")


def _chroma_path() -> str:
    pipe = load_pipeline()
    rel = pipe.get("vector_store", {}).get("path", "data/chroma")
    return str(DATA_DIR.parent / rel)


from functools import lru_cache

@lru_cache(maxsize=1)
def _get_persistent_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(
        path=_chroma_path(),
        settings=Settings(anonymized_telemetry=False),
    )

def get_collection() -> chromadb.Collection:
    """Return (or create) the persistent ChromaDB collection."""
    client = _get_persistent_client()
    return client.get_or_create_collection(
        name=_get_collection_name(),
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(chunks: list[Chunk], vectors: list[list[float]]) -> None:
    """Idempotent upsert: chunk_id is the Chroma document id."""
    if not chunks:
        return
    col = get_collection()
    col.upsert(
        ids=[c.chunk_id for c in chunks],
        documents=[c.document for c in chunks],
        embeddings=vectors,
        metadatas=[
            {
                "scheme": c.scheme,
                "scheme_id": c.scheme_id,
                "amc": c.amc,
                "category": c.category,
                "section": c.section,
                "source_url": c.source_url,
                "as_of_date": c.as_of_date,
            }
            for c in chunks
        ],
    )


def collection_stats() -> dict[str, int]:
    """Return chunk count per scheme_id (for manifest.json)."""
    col = get_collection()
    total = col.count()
    if total == 0:
        return {}

    results = col.get(include=["metadatas"])
    counts: dict[str, int] = {}
    for m in results["metadatas"] or []:
        sid = m.get("scheme_id", "unknown")
        counts[sid] = counts.get(sid, 0) + 1
    return counts
