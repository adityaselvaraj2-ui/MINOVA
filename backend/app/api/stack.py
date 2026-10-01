from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text as sql_text

from app.config import settings
from app.services import keycloak as kc
from app.services import storage, workflows

router = APIRouter(prefix="/stack", tags=["Platform Stack"])


@router.get("")
def stack_status():
    """Live view of the abstract's technology architecture: which enterprise
    components are active and which documented fallback is serving."""
    postgis = pgvector = False
    if settings.db_backend == "postgres":
        try:
            from app.db.session import get_engine

            with get_engine().connect() as conn:
                exts = conn.execute(sql_text("SELECT extname FROM pg_extension")).scalars().all()
                postgis = "postgis" in exts
                pgvector = "vector" in exts
        except Exception:
            pass

    s3_mode = storage.backend_name() == "s3"
    return {
        "database": {
            "backend": settings.db_backend,
            "postgis": postgis,
            "pgvector": pgvector,
            "fallback": "SQLite (WAL)" if settings.db_backend != "postgres" else None,
        },
        "object_storage": {
            "backend": storage.backend_name(),
            "endpoint": settings.minio_endpoint if s3_mode else None,
            "fallback": None if s3_mode else "local filesystem + DB metadata",
        },
        "auth": {
            "keycloak_enabled": kc.enabled(),
            "realm": settings.keycloak_realm,
            "fallback": None if kc.enabled() else "local argon2 + JWT RBAC",
        },
        "orchestration": {
            "temporal_enabled": settings.temporal_enabled,
            "temporal_available": workflows.temporal_available(),
            "fallback": None if settings.temporal_enabled
            else "in-process approval state machine",
        },
        "ocr": {"engine": "PaddleOCR", "fallback": "Tesseract via pytesseract"},
        "llm": {
            "primary": settings.ollama_primary_model,
            "fallbacks": [settings.ollama_fallback_1, settings.ollama_secondary_model],
        },
        "retrieval": {
            "embedding_model": settings.embedding_model_path,
            "embedding_dim": settings.embedding_dim,
            "vector_backend": "pgvector" if settings.db_backend == "postgres" else "ChromaDB",
        },
    }
