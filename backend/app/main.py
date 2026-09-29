from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.netguard import activate as activate_netguard

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("minetrace")


def create_app() -> FastAPI:
    settings.ensure_dirs()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "tauri://localhost",
            "https://tauri.localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.db.session import init_db

    init_db()

    from app.api.approvals import router as approvals_router
    from app.api.audit import router as audit_router
    from app.api.auth import router as auth_router
    from app.api.descriptions import router as descriptions_router
    from app.api.documents import router as documents_router
    from app.api.health import router as health_router
    from app.api.masters import router as masters_router
    from app.api.reports import router as reports_router
    from app.api.shift_entries import router as shift_entries_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(masters_router, prefix="/api/v1")
    app.include_router(shift_entries_router, prefix="/api/v1")
    app.include_router(approvals_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(reports_router, prefix="/api/v1")
    app.include_router(descriptions_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")

    @app.on_event("startup")
    async def _startup():
        if not settings.debug:
            activate_netguard()
        logger.info("MineTrace backend started on %s:%s", settings.host, settings.port)

    return app


app = create_app()
