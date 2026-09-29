from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["MINETRACE_DATA_DIR"] = str(Path(tempfile.mkdtemp()) / "minetrace_test")
os.environ["MINETRACE_DEBUG"] = "1"


@pytest.fixture(scope="session")
def app():
    from app.main import create_app

    return create_app()


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)
