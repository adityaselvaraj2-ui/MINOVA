"""Vector-store dispatch: Chroma (offline default) or pgvector (Postgres).

Keeps rag.py untouched: callers keep importing query_similar / add_embeddings
from here; the backend is selected by MINETRACE_DB_BACKEND.
"""
from __future__ import annotations

from app.config import settings


def _pg_mode() -> bool:
    return settings.db_backend == "postgres"


def add_embeddings(
    ids: list[str],
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict],
    db=None,
) -> bool:
    if _pg_mode():
        from app.services.pgvector_store import add_embeddings as pg_add

        return pg_add(ids, embeddings, documents, metadatas, db=db)
    from app.services.vectorstore import add_embeddings as chroma_add

    return chroma_add(ids, embeddings, documents, metadatas)


def query_similar(
    query_embedding: list[float],
    n_results: int = 20,
    where: dict | None = None,
    db=None,
) -> list[dict]:
    if _pg_mode():
        from app.services.pgvector_store import query_similar as pg_query

        return pg_query(query_embedding, n_results, where)
    from app.services.vectorstore import query_similar as chroma_query

    return chroma_query(query_embedding, n_results, where)


def delete_by_doc_id(doc_id: int, db=None) -> bool:
    if _pg_mode():
        from app.services.pgvector_store import delete_by_doc_id as pg_del

        return pg_del(doc_id)
    from app.services.vectorstore import delete_by_doc_id as chroma_del

    return chroma_del(doc_id)
