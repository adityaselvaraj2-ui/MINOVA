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
            primary_ok = any(settings.ollama_primary_model in m for m in models)
            secondary_ok = any(settings.ollama_secondary_model in m for m in models)
            return {
                "status": "ok",
                "models": models,
                "primary_available": primary_ok,
                "secondary_available": secondary_ok,
            }
        return {"status": "error", "detail": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "unavailable", "detail": str(e)}


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
    }
