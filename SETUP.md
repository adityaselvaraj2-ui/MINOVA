# MineTrace Setup Commands

## 0. Prerequisites (all must succeed)

```bash
python3 --version            # >= 3.10 (3.11 recommended)
node --version               # >= 20
npm --version
rustc --version && cargo --version   # required by Tauri
ollama --version
git --version
```

## 1. Local LLMs via Ollama

```bash
ollama serve &               # skip if Ollama already runs as a service
ollama pull qwen2.5
ollama pull llama3.1
ollama list
```

## 2. Backend (Python)

```bash
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
# If hdbscan fails to build: install build tools, or use sklearn.cluster.HDBSCAN
# (scikit-learn >= 1.3) and pass it to BERTopic as hdbscan_model.
```

## 3. Pre-download offline model assets (LAST step that needs internet)

```bash
python scripts/fetch_models.py   # BAAI/bge-small-en-v1.5 -> models/, PaddleOCR models -> models/paddleocr/
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ANONYMIZED_TELEMETRY=False PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
```

## 4. Frontend (Tauri v2 + React + TypeScript)

```bash
npm create tauri-app@latest frontend -- --template react-ts --manager npm --yes
cd frontend
npm install
npm install react-d3-cloud d3 recharts @tanstack/react-query react-router-dom \
  react-hook-form zod @hookform/resolvers i18next react-i18next date-fns clsx
npm install -D tailwindcss @tailwindcss/vite vitest @testing-library/react \
  @testing-library/jest-dom jsdom @types/d3 eslint
# If react-d3-cloud reports a peer-dependency conflict, pin react/react-dom to 18.x. Do not use --force.
cd ..
```

## 5. Run

```bash
./scripts/run_dev.sh         # starts FastAPI on 127.0.0.1 and `npm run tauri dev`
```
