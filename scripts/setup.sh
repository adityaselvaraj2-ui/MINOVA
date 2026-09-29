#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== MineTrace Setup ==="

echo "[1/6] Checking prerequisites..."
python --version || python3 --version
node --version
npm --version
rustc --version && cargo --version
ollama --version || echo "WARNING: Ollama not on PATH"
git --version

echo "[2/6] Setting up Python backend..."
if [ ! -d "backend/.venv" ]; then
    python -m venv backend/.venv || python3 -m venv backend/.venv
fi
source backend/.venv/Scripts/activate 2>/dev/null || source backend/.venv/bin/activate
pip install --upgrade pip wheel
pip install -r backend/requirements.lock.txt 2>/dev/null || \
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings sqlalchemy alembic \
  argon2-cffi pyjwt python-multipart httpx platformdirs \
  pandas numpy \
  reportlab python-docx ollama \
  pytest pytest-asyncio pytest-cov ruff
pip freeze > backend/requirements.lock.txt

echo "[3/6] Downloading offline models (needs internet)..."
PYTHONPATH=backend python scripts/fetch_models.py || echo "WARNING: Model download failed, run manually later"

echo "[4/6] Setting offline environment..."
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export ANONYMIZED_TELEMETRY=False
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

echo "[5/6] Setting up frontend..."
cd frontend
npm install
cd ..

echo "[6/6] Pulling Ollama models..."
ollama pull qwen2.5:7b || echo "WARNING: Could not pull qwen2.5:7b"
ollama pull llama3.1:8b || echo "WARNING: Could not pull llama3.1:8b"

echo ""
echo "=== Setup complete! Run: ./scripts/run_dev.sh ==="
