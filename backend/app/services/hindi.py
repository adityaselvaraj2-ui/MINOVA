"""Bilingual (EN + HI) support.

Air-gapped approach, no fine-tuning:
- Query tokenizer keeps Devanagari + Latin tokens (works with
  multilingual-e5-small embeddings, which are trained on both).
- Optional Hindi -> English query translation via the LOCAL Ollama model
  (qwen3 handles Hindi), so BM25 over English documents still fires.
- Embedded values in chunks stay original; answers are generated in the
  language of the question (prompt instruction); the grounding metric is
  token-based and extended to Devanagari.
"""
from __future__ import annotations

import re

from app.config import settings
from app.services.llm.gateway import chat

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def is_hindi(text: str) -> bool:
    """True when Devanagari characters make up the majority of letters."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    deva = sum(1 for c in letters if _DEVANAGARI_RE.match(c))
    return deva / len(letters) > 0.4


def tokenize_bilingual(text: str) -> list[str]:
    """Tokenize keeping Devanagari words, Latin words and digits."""
    return re.findall(r"[\u0900-\u097F\u00e0-\u00ff\w]+", text.lower())


_TRANSLATE_SYSTEM = (
    "You are a translator. Translate the user's Hindi mining question into "
    "natural English. Output ONLY the English translation, nothing else. "
    "Keep numbers and mine names unchanged."
)


def translate_to_english(query: str) -> str | None:
    """Translate a Hindi query to English using the local LLM.

    Returns None on any failure - callers then fall back to the raw query
    (multilingual embeddings still retrieve; only BM25 would be weaker).
    """
    if not settings.hindi_query_translation:
        return None
    # Gateway strips <think> blocks and walks the fallback model chain.
    out, _model = chat(_TRANSLATE_SYSTEM, query, timeout=180.0, max_tokens=256)
    return out or None
