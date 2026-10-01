"""Optional cross-encoder reranker (BAAI/bge-reranker-v2-m3).

Disabled by default (RERANKER_ENABLED=false). When enabled and the model
is present locally, it re-scores retrieved chunks against the query and
returns the top-k in better order. Falls back silently to the input order.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from app.config import settings

logger = logging.getLogger("minetrace.reranker")


@lru_cache(maxsize=1)
def _load_model():
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        logger.info("sentence-transformers CrossEncoder unavailable; reranker off")
        return None
    try:
        path = str(settings.models_root / "bge-reranker-v2-m3")
        return CrossEncoder(path, max_length=512)
    except Exception:
        logger.exception("Failed to load reranker model")
        return None


def rerank(query: str, contexts: list[dict], top_k: int = 12) -> list[dict]:
    """Rerank contexts by relevance to the query. Falls back to input order."""
    if not settings.reranker_enabled or not contexts:
        return contexts[:top_k]
    model = _load_model()
    if model is None:
        return contexts[:top_k]
    try:
        pairs = [[query, c["text"][:1000]] for c in contexts]
        scores = model.predict(pairs)
        ranked = sorted(zip(contexts, scores, strict=True), key=lambda x: x[1], reverse=True)
        return [c for c, _ in ranked[:top_k]]
    except Exception:
        logger.exception("Rerank failed; returning original order")
        return contexts[:top_k]
