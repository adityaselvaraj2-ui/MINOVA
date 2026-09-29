from __future__ import annotations

import logging
from functools import lru_cache

from app.config import settings

logger = logging.getLogger("minetrace.embeddings")

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _load_model():
    try:
        from sentence_transformers import SentenceTransformer

        model_path = settings.embedding_model_path
        logger.info("Loading embedding model from %s", model_path)
        return SentenceTransformer(model_path)
    except Exception:
        logger.exception("Failed to load embedding model")
        return None


def embed_texts(texts: list[str], is_query: bool = False) -> list[list[float]] | None:
    model = _load_model()
    if model is None:
        return None

    if is_query:
        texts = [BGE_QUERY_PREFIX + t for t in texts]

    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()


def embed_single(text: str, is_query: bool = False) -> list[float] | None:
    result = embed_texts([text], is_query=is_query)
    if result is None:
        return None
    return result[0]
