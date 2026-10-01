from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger("minetrace.vectorstore")


def _collection_name() -> str:
    """Dimension-suffixed so switching embedding models (e.g. e5 384-dim to
    BGE-M3 1024-dim) never collides with vectors of the wrong width."""
    return f"minetrace_docs_{settings.embedding_dim}"


_collections: dict[str, object] = {}


def _get_collection():
    name = _collection_name()
    cached = _collections.get(name)
    if cached is not None:
        return cached
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(settings.chroma_path))
        col = client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )
        _collections[name] = col
        return col
    except Exception:
        logger.exception("Failed to init ChromaDB")
        return None


def add_embeddings(
    ids: list[str],
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict],
) -> bool:
    collection = _get_collection()
    if collection is None:
        return False

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )
    return True


def query_similar(
    query_embedding: list[float],
    n_results: int = 20,
    where: dict | None = None,
) -> list[dict]:
    collection = _get_collection()
    if collection is None:
        return []

    kwargs: dict = {
        "query_embeddings": [query_embedding],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)

    items = []
    if results and results["ids"] and results["ids"][0]:
        for i, chroma_id in enumerate(results["ids"][0]):
            items.append({
                "chroma_id": chroma_id,
                "text": results["documents"][0][i] if results["documents"] else "",
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 1.0,
            })
    return items


def delete_by_doc_id(doc_id: int) -> bool:
    collection = _get_collection()
    if collection is None:
        return False

    collection.delete(where={"document_id": doc_id})
    return True


def drop_all_collections() -> int:
    """Drop every minetrace_docs* collection (reindex across model switches).
    Returns how many collections were removed."""
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(settings.chroma_path))
        dropped = 0
        for c in client.list_collections():
            name = c if isinstance(c, str) else getattr(c, "name", str(c))
            if str(name).startswith("minetrace_docs"):
                client.delete_collection(str(name))
                dropped += 1
        _collections.clear()
        return dropped
    except Exception:
        logger.exception("Failed to drop Chroma collections")
        return 0
