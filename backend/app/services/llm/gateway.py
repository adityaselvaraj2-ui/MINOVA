"""Shared Ollama helpers: model chain + qwen3 <think> block stripping."""
from __future__ import annotations

import re

import httpx

from app.config import settings

_THINK_RE = re.compile(r"(?s)<think>.*?</think>\s*")


def strip_think(text: str) -> str:
    """qwen3 emits <think>...</think> reasoning blocks; they must never leak
    into user-facing answers or exported reports."""
    return _THINK_RE.sub("", text).strip()


def model_chain() -> list[str]:
    """Primary -> fallback_1 -> secondary, deduplicated."""
    seen: list[str] = []
    for m in (settings.ollama_primary_model, settings.ollama_fallback_1,
              settings.ollama_secondary_model):
        if m and m not in seen:
            seen.append(m)
    return seen


def chat(
    system: str,
    user: str,
    timeout: float = 180.0,
    max_tokens: int | None = None,
) -> tuple[str | None, str | None]:
    """Try each model in the chain. Returns (text, model_used) or (None, None).

    - think:false skips qwen3's reasoning tokens (deterministic tasks only;
      strip_think still guards any stragglers)
    - keep_alive keeps the model warm across demo queries
    - max_tokens caps generation (SQL/narration never need thousands)
    - default timeout covers qwen3:8b cold-load (~2 min first call)"""
    for model in model_chain():
        try:
            options = {
                "temperature": settings.ollama_temperature,
                "seed": settings.ollama_seed,
                "num_ctx": settings.ollama_num_ctx,
            }
            if max_tokens:
                options["num_predict"] = max_tokens
            resp = httpx.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "think": False,
                    "keep_alive": "30m",
                    "options": options,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                content = strip_think(resp.json()["message"]["content"])
                if content:
                    return content, model
        except Exception:
            continue
    return None, None
