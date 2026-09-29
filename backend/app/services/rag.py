from __future__ import annotations

import logging
import math
import re
from collections import Counter

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import DocumentChunk
from app.services.embeddings import embed_single
from app.services.vectorstore import query_similar

logger = logging.getLogger("minetrace.rag")

TOP_K_DENSE = 20
TOP_K_BM25 = 20
TOP_K_FUSED = 10
RRF_K = 60


def _bm25_scores(
    db: Session, query: str, limit: int = TOP_K_BM25,
) -> list[tuple[int, float]]:
    terms = re.findall(r"\w+", query.lower())
    if not terms:
        return []

    all_chunks = db.query(DocumentChunk.id, DocumentChunk.text).all()
    if not all_chunks:
        return []

    n_docs = len(all_chunks)
    avg_dl = sum(len(c.text.split()) for c in all_chunks) / n_docs if n_docs else 1

    df: Counter = Counter()
    for chunk in all_chunks:
        words = set(chunk.text.lower().split())
        for t in terms:
            if t in words:
                df[t] += 1

    scores: list[tuple[int, float]] = []
    k1, b = 1.5, 0.75
    for chunk in all_chunks:
        words = chunk.text.lower().split()
        dl = len(words)
        freq = Counter(words)
        score = 0.0
        for t in terms:
            tf = freq.get(t, 0)
            if tf == 0:
                continue
            idf = math.log((n_docs - df[t] + 0.5) / (df[t] + 0.5) + 1)
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
        if score > 0:
            scores.append((chunk.id, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:limit]


def _reciprocal_rank_fusion(
    dense_ids: list[int],
    bm25_ranked: list[tuple[int, float]],
) -> list[int]:
    scores: dict[int, float] = {}

    for rank, chunk_id in enumerate(dense_ids):
        scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (RRF_K + rank + 1)

    for rank, (chunk_id, _) in enumerate(bm25_ranked):
        scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (RRF_K + rank + 1)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [cid for cid, _ in ranked[:TOP_K_FUSED]]


def retrieve(db: Session, query: str) -> list[dict]:
    query_emb = embed_single(query, is_query=True)

    dense_results = []
    dense_ids = []
    if query_emb:
        dense_results = query_similar(query_emb, n_results=TOP_K_DENSE)
        for r in dense_results:
            cid = r["metadata"].get("chunk_id")
            if cid is not None:
                dense_ids.append(int(cid))

    bm25_ranked = _bm25_scores(db, query, TOP_K_BM25)

    if dense_ids or bm25_ranked:
        fused_ids = _reciprocal_rank_fusion(dense_ids, bm25_ranked)
    elif dense_ids:
        fused_ids = dense_ids[:TOP_K_FUSED]
    elif bm25_ranked:
        fused_ids = [cid for cid, _ in bm25_ranked[:TOP_K_FUSED]]
    else:
        return []

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.id.in_(fused_ids))
        .all()
    )
    chunk_map = {c.id: c for c in chunks}

    results = []
    for cid in fused_ids:
        chunk = chunk_map.get(cid)
        if chunk:
            results.append({
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "filename": chunk.document.filename,
                "page_number": chunk.page_number,
                "text": chunk.text,
            })
    return results


def generate_cited_answer(query: str, contexts: list[dict]) -> dict:
    if not contexts:
        return {
            "answer": "No relevant documents found.",
            "citations": [],
            "model": None,
        }

    context_block = ""
    for i, ctx in enumerate(contexts):
        ref = f"[C{i+1}]"
        context_block += (
            f"{ref} (doc: {ctx['filename']}, page {ctx['page_number']}):\n"
            f"{ctx['text'][:500]}\n\n"
        )

    system = (
        "You are a mining knowledge assistant for CMPDI/CIL. "
        "Answer questions using ONLY the provided context passages. "
        "Cite sources as [C1], [C2], etc. "
        "If the context doesn't contain the answer, say so."
    )
    user = (
        f"CONTEXT:\n{context_block}\n"
        f"QUESTION: {query}\n\n"
        "Answer with citations:"
    )

    model = settings.ollama_primary_model
    answer = _call_ollama(system, user, model)
    if answer is None:
        model = settings.ollama_secondary_model
        answer = _call_ollama(system, user, model)
    if answer is None:
        answer = _fallback_answer(contexts)
        model = None

    citations = []
    for i, ctx in enumerate(contexts):
        ref = f"[C{i+1}]"
        if ref in (answer or ""):
            citations.append({
                "ref": ref,
                "chunk_id": ctx["chunk_id"],
                "document_id": ctx["document_id"],
                "filename": ctx["filename"],
                "page_number": ctx["page_number"],
                "excerpt": ctx["text"][:200],
            })

    return {
        "answer": answer or "",
        "citations": citations,
        "model": model,
    }


def _call_ollama(system: str, user: str, model: str) -> str | None:
    try:
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {
                    "temperature": settings.ollama_temperature,
                    "seed": settings.ollama_seed,
                    "num_ctx": settings.ollama_num_ctx,
                },
            },
            timeout=120.0,
        )
        if resp.status_code == 200:
            return resp.json()["message"]["content"]
        return None
    except Exception:
        logger.exception("Ollama RAG call failed")
        return None


def _fallback_answer(contexts: list[dict]) -> str:
    parts = ["Based on available documents:\n"]
    for i, ctx in enumerate(contexts[:3]):
        parts.append(
            f"[C{i+1}] From {ctx['filename']} (page {ctx['page_number']}): "
            f"{ctx['text'][:200]}..."
        )
    parts.append("\n(AI narration unavailable — showing raw excerpts)")
    return "\n\n".join(parts)
