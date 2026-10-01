from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.netguard import is_active as netguard_active

router = APIRouter(tags=["health"])
logger = logging.getLogger("minetrace.health")


def _check_db(db: Session) -> dict:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "path": str(settings.db_path)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_ollama() -> dict:
    try:
        resp = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3.0)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            wanted = [
                settings.ollama_primary_model,
                settings.ollama_fallback_1,
                settings.ollama_secondary_model,
            ]
            availability = {
                w: any(m == w or m.startswith(w + ":") for m in models)
                for w in wanted
            }
            return {
                "status": "ok",
                "models": models,
                "primary_available": availability[settings.ollama_primary_model],
                "secondary_available": availability[settings.ollama_secondary_model],
                "fallback_1_available": availability[settings.ollama_fallback_1],
                "model_availability": availability,
            }
        return {"status": "error", "detail": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "unavailable", "detail": str(e)}


def _check_embeddings() -> dict:
    try:
        from app.services.embeddings import _load_model, _resolve_model_path

        model = _load_model(_resolve_model_path())
        if model is None:
            return {"status": "unavailable"}
        dim = model.get_sentence_embedding_dimension()
        return {
            "status": "ok",
            "model_path": settings.embedding_model_path,
            "dim": dim,
            "expected_dim": settings.embedding_dim,
            "match": dim == settings.embedding_dim,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_reranker() -> dict:
    if not settings.reranker_enabled:
        return {"status": "disabled"}
    try:
        path = settings.models_root / "bge-reranker-v2-m3"
        return {
            "status": "ok" if path.exists() else "missing",
            "model_path": str(path),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_ocr() -> dict:
    try:
        import shutil

        return {
            "tesseract_binary": shutil.which("tesseract"),
            "paddleocr_dir": str(settings.models_root / "paddleocr"),
        }
    except Exception:
        return {}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db_status = _check_db(db)
    ollama_status = _check_ollama()

    overall = "ok"
    if db_status["status"] != "ok":
        overall = "degraded"
    if ollama_status["status"] != "ok":
        overall = "degraded" if overall == "ok" else overall

    return {
        "status": overall,
        "app": settings.app_name,
        "version": "0.1.0",
        "netguard_active": netguard_active(),
        "database": db_status,
        "ollama": ollama_status,
        "models_loaded": {
            "embeddings": _check_embeddings(),
            "reranker": _check_reranker(),
            "ocr": _check_ocr(),
            "llm_primary": settings.ollama_primary_model,
            "llm_fallback_1": settings.ollama_fallback_1,
            "llm_secondary": settings.ollama_secondary_model,
            "hindi_translation_enabled": settings.hindi_query_translation,
        },
    }
