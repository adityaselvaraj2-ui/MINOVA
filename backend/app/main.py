from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.db.extended_models  # noqa: F401  (registers weather/plan/conflict tables)
import app.db.models  # noqa: F401
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
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "tauri://localhost",
            "https://tauri.localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.db.session import init_db

    init_db()

    from app.api.analytics import router as analytics_router
    from app.api.approvals import router as approvals_router
    from app.api.audit import router as audit_router
    from app.api.auth import router as auth_router
    from app.api.descriptions import router as descriptions_router
    from app.api.documents import router as documents_router
    from app.api.health import router as health_router
    from app.api.keycloak import router as keycloak_router
    from app.api.lineage import router as lineage_router
    from app.api.masters import router as masters_router
    from app.api.planning import router as planning_router
    from app.api.querypack import router as querypack_router
    from app.api.reports import router as reports_router
    from app.api.shift_entries import router as shift_entries_router
    from app.api.stack import router as stack_router
    from app.api.sync import router as sync_router
    from app.api.workflows import router as workflows_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(keycloak_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(masters_router, prefix="/api/v1")
    app.include_router(shift_entries_router, prefix="/api/v1")
    app.include_router(approvals_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(reports_router, prefix="/api/v1")
    app.include_router(lineage_router, prefix="/api/v1")
    app.include_router(descriptions_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(planning_router, prefix="/api/v1")
    app.include_router(querypack_router, prefix="/api/v1")
    app.include_router(sync_router, prefix="/api/v1")
    app.include_router(stack_router, prefix="/api/v1")
    app.include_router(workflows_router, prefix="/api/v1")

    @app.on_event("startup")
    async def _startup():
        if not settings.debug:
            activate_netguard()
        logger.info("MineTrace backend started on %s:%s", settings.host, settings.port)

    return app


app = create_app()
