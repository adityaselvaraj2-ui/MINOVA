# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the MineTrace backend sidecar (lean build).

Produces dist/minetrace-backend.exe — a single-file FastAPI server the Tauri
desktop shell spawns on launch. Heavy AI engines are excluded on purpose
(the app degrades to BM25-only retrieval + local-LR fallbacks); the full
offline stack remains available when running from source.
"""
import os

block_cipher = None

hiddenimports = [
    # uvicorn resolves these dynamically via strings
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # app package (all routers register via create_app)
    "app",
    "app.main",
    "app.config",
    "app.api.analytics",
    "app.api.approvals",
    "app.api.audit",
    "app.api.auth",
    "app.api.descriptions",
    "app.api.documents",
    "app.api.health",
    "app.api.keycloak",
    "app.api.lineage",
    "app.api.masters",
    "app.api.planning",
    "app.api.querypack",
    "app.api.reports",
    "app.api.shift_entries",
    "app.api.stack",
    "app.api.sync",
    "app.api.workflows",
    "app.db.extended_models",
    "app.db.models",
    "app.db.schema_migration",
    "app.db.session",
    "app.schemas.documents",
    # background async runtime bits
    "anyio._backends._asyncio",
    # first-launch demo dataset seeder (scripts/seed_demo.py)
    "seed_demo",
]

# Excluded on purpose: multi-GB ML engines the frozen app cannot ship. Every
# one has a lazy-import site in app/, so excluding them here makes the frozen
# build take the documented zero-dependency fallback paths at runtime.
excludes = [
    "torch",
    "sentence_transformers",
    "transformers",
    "safetensors",
    "paddleocr",
    "paddle",
    "chromadb",
    "sklearn",
    "scipy",
    "matplotlib",
    "pandas",
    "onnxruntime",
    "temporalio",
    "keycloak",
    "pytest",
    "PyInstaller",
]

a = Analysis(
    ["sidecar_main.py"],
    pathex=[
        os.path.abspath("."),
        os.path.abspath(".."),
        os.path.abspath("../scripts"),  # seed_demo lives here (no package)
    ],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="minetrace-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # sidecar must not flash a console window
    icon=None,
)
