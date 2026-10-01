from __future__ import annotations

import logging
import math
import re
from collections import Counter

from sqlalchemy.orm import Session

from app.db.models import DocumentChunk
from app.services.embeddings import embed_single
from app.services.hindi import is_hindi, tokenize_bilingual, translate_to_english
from app.services.llm.gateway import chat
from app.services.reranker import rerank
from app.services.vector_dispatch import query_similar

logger = logging.getLogger("minetrace.rag")

TOP_K_DENSE = 24
TOP_K_BM25 = 24
TOP_K_FUSED = 12
RRF_K = 60
CONTEXT_CHARS = 900
LLM_TIMEOUT_S = 180.0  # qwen3:8b cold-load can exceed 2 minutes

# Tokens too generic to count as evidence in the grounding score
_GENERIC_TOKENS = frozenset([
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for",
    "with", "by", "from", "as", "is", "are", "was", "were", "this",
    "that", "it", "its", "at", "be", "has", "have", "had", "not",
    "no", "yes", "per", "etc",
])


def grounded_pct(answer: str, contexts: list[dict]) -> int:
    """Share of meaningful answer tokens found in the retrieved context.

    Lexical faithfulness metric (teammate's design): the higher, the more
    the answer is grounded in source text rather than invented. Returned
    with every RAG answer so officials can judge trust at a glance.
    Devanagari-aware so Hindi answers are scored correctly.
    """
    if not answer or not contexts:
        return 0
    corpus = " ".join(ctx["text"].lower() for ctx in contexts)
    tokens = [
        t for t in tokenize_bilingual(answer)
        if t not in _GENERIC_TOKENS and not t.isdigit() and len(t) >= 2
    ]
    if not tokens:
        return 100
    hits = sum(1 for t in tokens if t in corpus)
    return int(round(100 * hits / len(tokens)))


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
    # Hindi queries: try local-LLM translation so BM25 (English corpus) fires;
    # multilingual embeddings already handle the original Hindi text.
    translated = None
    if is_hindi(query):
        translated = translate_to_english(query)
    query_emb = embed_single(query, is_query=True)
    emb_query_text = translated or query

    dense_results = []
    dense_ids = []
    if query_emb:
        dense_results = query_similar(query_emb, n_results=TOP_K_DENSE)
        for r in dense_results:
            cid = r["metadata"].get("chunk_id")
            if cid is not None:
                dense_ids.append(int(cid))

    bm25_ranked = _bm25_scores(db, emb_query_text, TOP_K_BM25)

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
    # Extraction review gate: FLAGGED documents are excluded from retrieval
    # entirely so unverified numbers can never ground an answer.
    chunk_map: dict[int, DocumentChunk] = {}
    for c in chunks:
        if c.document.review_status == "FLAGGED":
            continue
        chunk_map[c.id] = c

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
                "review_status": chunk.document.review_status,
            })
    return rerank(query, results, TOP_K_FUSED)


def generate_cited_answer(query: str, contexts: list[dict]) -> dict:
    if not contexts:
        return {
            "answer": "No relevant documents found.",
            "citations": [],
            "model": None,
            "grounded_pct": 0,
        }

    context_block = ""
    for i, ctx in enumerate(contexts):
        ref = f"[C{i+1}]"
        context_block += (
            f"{ref} (doc: {ctx['filename']}, page {ctx['page_number']}):\n"
            f"{ctx['text'][:CONTEXT_CHARS]}\n\n"
        )

    hindi = is_hindi(query)
    question_for_llm = query
    if hindi:
        # Local models reason far better in English; retrieve used the
        # translation for BM25 - reuse it for generation, answer in Hindi.
        translated = translate_to_english(query)
        logger.info("hindi translate: %r -> %r", query[:60], translated)
        if translated:
            question_for_llm = translated
    system = (
        "You are a mining knowledge assistant for CMPDI/CIL. "
        "Answer questions using ONLY the provided context passages. "
        "Cite sources as [C1], [C2], etc. "
        "If the context doesn't contain the answer, say so."
    )
    if hindi:
        system += " Answer in Hindi (Devanagari script), keeping numbers as-is."
    user = (
        f"CONTEXT:\n{context_block}\n"
        f"QUESTION: {question_for_llm}\n\n"
        "Answer with citations:"
    )

    answer, model = chat(system, user, timeout=LLM_TIMEOUT_S, max_tokens=1024)
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
        "grounded_pct": grounded_pct(answer or "", contexts),
        "unverified_numbers": _unverified_numbers(answer or "", contexts),
    }


def _unverified_numbers(answer: str, contexts: list[dict]) -> list[str]:
    """Numbers in the answer that appear in NO retrieved context chunk.
    Surfaced to the UI as an 'unverified number' warning (constraint 3)."""
    import re as _re

    corpus = " ".join(c["text"] for c in contexts)
    found = _re.findall(r"\d[\d,]*\.?\d*", answer)
    return [n for n in found if n.replace(",", "") not in corpus.replace(",", "")]


def _call_ollama(system: str, user: str, model: str) -> str | None:
    """Backward-compatible wrapper over the shared LLM gateway.
    `model` is ignored; the gateway walks the configured model chain."""
    return chat(system, user, timeout=LLM_TIMEOUT_S)[0]


def _fallback_answer(contexts: list[dict]) -> str:
    parts = ["Based on available documents:\n"]
    for i, ctx in enumerate(contexts[:3]):
        parts.append(
            f"[C{i+1}] From {ctx['filename']} (page {ctx['page_number']}): "
            f"{ctx['text'][:200]}..."
        )
    parts.append("\n(AI narration unavailable — showing raw excerpts)")
    return "\n\n".join(parts)
