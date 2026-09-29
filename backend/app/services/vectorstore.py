from __future__ import annotations

import logging
from functools import lru_cache

from app.config import settings

logger = logging.getLogger("minetrace.vectorstore")

COLLECTION_NAME = "minetrace_docs"


@lru_cache(maxsize=1)
def _get_collection():
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(settings.chroma_path))
        return client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
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
