"""Standalone backend entrypoint for the Tauri sidecar (PyInstaller build).

Runs the same FastAPI app as `uvicorn app.main:app`, but as a frozen exe the
desktop shell can spawn and kill. Usage:

    minetrace-backend.exe [--port 19830]

The heavy AI engines (torch / sentence-transformers / paddle / chromadb) are
excluded from the frozen build on purpose: the packaged app degrades to
BM25-only retrieval, exactly like the documented zero-dependency fallbacks.
"""
from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
from pathlib import Path


def _default_data_dir() -> Path:
    """Keep user data next to the app config (Roaming), consistent with Tauri."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "minetrace"


def main() -> int:
    parser = argparse.ArgumentParser(description="MineTrace backend sidecar")
    parser.add_argument("--port", type=int, default=19830)
    args, _unknown = parser.parse_known_args()

    # Diagnostics: if boot has not finished in 30s, dump every thread's stack
    # so we can see exactly where the frozen build stalls.
    import faulthandler

    faulthandler.dump_traceback_later(30, exit=True)
    print("SIDECAR: starting boot", flush=True)

    # Frozen exe: point MineTrace at a stable per-user data dir and make sure
    # our own bundled modules import (PyInstaller puts them in the bundle).
    os.environ.setdefault("MINETRACE_DATA_DIR", str(_default_data_dir()))
    if getattr(sys, "frozen", False):
        os.environ.setdefault("MINETRACE_EMBEDDING_MODEL_PATH", "unavailable")

    multiprocessing.freeze_support()

    import uvicorn

    print("SIDECAR: importing app.main", flush=True)
    from app.main import create_app

    print("SIDECAR: calling create_app", flush=True)
    app = create_app()

    # First boot on a user machine: the DB is empty and login would 500.
    # Seed the deterministic demo dataset (idempotent — skips if data exists).
    if os.environ.get("MINETRACE_SIDECAR_SEED", "1") != "0":
        print("SIDECAR: seeding demo data (first launch may take a minute)", flush=True)
        # A fresh install has no tables: init_db() only builds the engine.
        # create_all is idempotent and matches the dev/test bootstrap pattern.
        from app.db.session import Base, get_engine

        Base.metadata.create_all(get_engine())
        import seed_demo

        seed_demo.seed()
        print("SIDECAR: seeding done", flush=True)

    print("SIDECAR: create_app done, starting uvicorn", flush=True)
    faulthandler.cancel_dump_traceback_later()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        log_level="info",
        # NOTE: never pass workers= here — on Windows it switches uvicorn to
        # its multiprocessing supervisor, which re-launches the frozen exe
        # (PyInstaller spawn deadlock). Default = in-process single server,
        # which is exactly what a sidecar needs: it dies with the shell.
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
