# MineTrace

Offline source-to-report intelligence platform for CMPDI/CIL subsidiaries (SIH26023, Ministry of Coal).

## Setup Commands

```bash
# ---- 0. Prerequisites (all must succeed) ----
python3 --version            # >= 3.10 (3.11 recommended)
node --version               # >= 20
npm --version
rustc --version && cargo --version   # required by Tauri
ollama --version
git --version

# ---- 1. Local LLMs via Ollama ----
ollama serve &               # skip if Ollama already runs as a service
ollama pull qwen3:8b         # primary LLM (multilingual EN+HI)
ollama pull qwen2.5:7b       # smaller fallback
ollama pull llama3.1:8b      # English-strong fallback
ollama list

# Hugging Face models (once on a connected machine, then copy ./models)
#   hf download intfloat/multilingual-e5-small --local-dir models/multilingual-e5-small
#   hf download BAAI/bge-reranker-v2-m3 --local-dir models/bge-reranker-v2-m3   # optional
# or run: python scripts/download_models.py --all

# ---- 2. Backend (Python) ----
mkdir -p minetrace && cd minetrace
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install --upgrade pip wheel
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings sqlalchemy alembic \
  argon2-cffi pyjwt python-multipart httpx platformdirs \
  pandas numpy \
  chromadb sentence-transformers rank-bm25 \
  pdfplumber pypdfium2 pillow paddlepaddle paddleocr \
  bertopic umap-learn hdbscan scikit-learn nltk langdetect \
  reportlab python-docx ollama \
  pytest pytest-asyncio pytest-cov ruff mypy
pip freeze > backend/requirements.lock.txt

# ---- 3. Pre-download offline model assets (LAST step that needs internet) ----
python scripts/fetch_models.py
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ANONYMIZED_TELEMETRY=False PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

# ---- 4. Frontend (Tauri v2 + React + TypeScript) ----
cd frontend
npm install
cd ..

# ---- 5. Run ----
./scripts/run_dev.sh
```
