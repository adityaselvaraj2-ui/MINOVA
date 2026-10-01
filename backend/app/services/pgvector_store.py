"""pgvector retrieval backend - PostgreSQL/PostGIS + pgvector implementation of
the same interface as app.services.vectorstore (ChromaDB).

The abstract specifies PostgreSQL/PostGIS + pgvector for semantic retrieval.
When MINETRACE_DB_BACKEND=postgres, these drop-in functions serve embeddings
from Postgres instead of Chroma. The embedding lives on document_chunk
(pgvector `vector` column, added by ensure_pgvector()); lookups join the
document table so result metadata matches the Chroma contract exactly
(chunk_id / document_id / filename / page_number / mine_id).
"""
from __future__ import annotations

import logging

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

logger = logging.getLogger("minetrace.pgvector")

_ensured_urls: set[str] = set()


def _engine():
    from app.db.session import get_engine

    return get_engine()


def ensure_pgvector() -> bool:
    """CREATE EXTENSION vector + add the embedding column if missing.

    Safe to call repeatedly; returns False when the backend isn't Postgres.
    """
    try:
        engine = _engine()
        if engine.url.get_backend_name() != "postgresql":
            return False
        url_key = str(engine.url)
        if url_key in _ensured_urls:
            return True
        with engine.connect() as conn:
            conn.execute(sql_text("COMMIT"))  # end implicit txn for CREATE EXTENSION
            conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(
                sql_text(
                    "ALTER TABLE document_chunk ADD COLUMN IF NOT EXISTS "
                    "embedding vector"
                )
            )
            conn.execute(sql_text("COMMIT"))
        _ensured_urls.add(url_key)
        return True
    except Exception:
        logger.exception("pgvector setup failed")
        return False


def add_embeddings(
    ids: list[str],
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict],
    db: Session | None = None,
) -> bool:
    """Store chunk vectors in Postgres. `ids` are chroma_id strings
    (doc{document_id}_chunk{i}) matching document_chunk.chroma_id."""
    if not embeddings:
        return True
    try:
        if not ensure_pgvector():
            return False
        rows = [
            {"vec": "[" + ",".join(f"{x:.6f}" for x in vec) + "]",
             "cid": cid}
            for cid, vec in zip(ids, embeddings, strict=False)
        ]
        stmt = sql_text(
            "UPDATE document_chunk SET embedding = CAST(:vec AS vector) "
            "WHERE chroma_id = :cid"
        )
        if db is not None:
            db.execute(stmt, rows)
            return True
        with _engine().connect() as conn:
            conn.execute(stmt, rows)
            conn.execute(sql_text("COMMIT"))
        return True
    except Exception:
        logger.exception("pgvector add_embeddings failed")
        return False


def query_similar(
    query_embedding: list[float],
    n_results: int = 20,
    where: dict | None = None,
) -> list[dict]:
    """Cosine-distance KNN over document_chunk.embedding; same result shape as
    vectorstore.query_similar (chroma_id / text / metadata / distance)."""
    try:
        if not ensure_pgvector():
            return []
        vec_literal = "[" + ",".join(f"{x:.6f}" for x in query_embedding) + "]"
        sql = """
            SELECT c.chroma_id, c.text, c.id AS chunk_id, c.document_id,
                   c.page_number, d.mine_id, d.filename,
                   c.embedding <=> CAST(:vec AS vector) AS distance
            FROM document_chunk c
            JOIN document d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
        """
        params: dict = {"vec": vec_literal}
        if where and where.get("mine_id") is not None:
            sql += " AND d.mine_id = :mine_id"
            params["mine_id"] = where["mine_id"]
        sql += " ORDER BY distance LIMIT :limit"
        params["limit"] = n_results
        with _engine().connect() as conn:
            rows = conn.execute(sql_text(sql), params).mappings().all()
        return [
            {
                "chroma_id": r["chroma_id"],
                "text": r["text"],
                "metadata": {
                    "chunk_id": r["chunk_id"],
                    "document_id": r["document_id"],
                    "page_number": r["page_number"],
                    "mine_id": r["mine_id"],
                    "filename": r["filename"],
                },
                "distance": float(r["distance"]),
            }
            for r in rows
        ]
    except Exception:
        logger.exception("pgvector query_similar failed")
        return []


def delete_by_doc_id(doc_id: int) -> bool:
    try:
        with _engine().connect() as conn:
            conn.execute(
                sql_text(
                    "UPDATE document_chunk SET embedding = NULL "
                    "WHERE document_id = :did"
                ),
                {"did": doc_id},
            )
            conn.execute(sql_text("COMMIT"))
        return True
    except Exception:
        logger.exception("pgvector delete_by_doc_id failed")
        return False
