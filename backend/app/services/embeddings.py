from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from app.config import settings

logger = logging.getLogger("minetrace.embeddings")

# Project root = minetrace/ (parents: services -> app -> backend -> minetrace)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

E5_QUERY_PREFIX = "query: "
E5_PASSAGE_PREFIX = "passage: "
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _resolve_model_path() -> str:
    """Resolve the embedding model dir against CWD first, then project root."""
    raw = Path(settings.embedding_model_path)
    if raw.is_absolute():
        return str(raw)
    for base in (Path.cwd(), _PROJECT_ROOT):
        candidate = base / raw
        if candidate.exists():
            return str(candidate)
    return str(raw)


def model_family() -> str:
    """bge-m3 | e5 | bge - decides which instruction prefix is applied."""
    name = _resolve_model_path().lower().replace("\\", "/")
    if "bge-m3" in name:
        return "bge-m3"  # BGE-M3 dense is trained without task prefixes
    if "e5" in name:
        return "e5"  # e5 wants "query: " / "passage: "
    return "bge"  # classic BGE retrieval instruction on queries only


def _prefixes() -> tuple[str, str]:
    family = model_family()
    if family == "e5":
        return E5_QUERY_PREFIX, E5_PASSAGE_PREFIX
    if family == "bge":
        return BGE_QUERY_PREFIX, ""
    return "", ""


@lru_cache(maxsize=4)
def _load_model(path: str):
    """Keyed by resolved path so a config switch loads the right model."""
    try:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model from %s", path)
        if model_family() == "bge-m3":
            # BGE-M3 dense embeddings = CLS pooling over XLM-R (1024-dim);
            # sentence-transformers defaults to mean pooling, so build modules.
            from sentence_transformers.models import Pooling, Transformer

            modules = [
                Transformer(path),
                Pooling(
                    word_embedding_dimension=settings.bge_m3_dim,
                    pooling_mode_cls_token=True,
                ),
            ]
            return SentenceTransformer(modules=modules)
        return SentenceTransformer(path)
    except Exception:
        logger.exception("Failed to load embedding model from %s", path)
        return None


def embed_texts(texts: list[str], is_query: bool = False) -> list[list[float]] | None:
    model = _load_model(_resolve_model_path())
    if model is None:
        return None
    query_prefix, passage_prefix = _prefixes()
    prefix = query_prefix if is_query else passage_prefix
    if prefix:
        texts = [prefix + t for t in texts]
    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()


def embed_single(text: str, is_query: bool = False) -> list[float] | None:
    result = embed_texts([text], is_query=is_query)
    if result is None:
        return None
    return result[0]
