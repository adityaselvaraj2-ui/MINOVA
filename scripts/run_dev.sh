#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export ANONYMIZED_TELEMETRY=False
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
export MINETRACE_DEBUG=1
export MINETRACE_PORT=19823

cd "$PROJECT_DIR/backend"
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port $MINETRACE_PORT --reload &
BACKEND_PID=$!
echo "Backend started on 127.0.0.1:$MINETRACE_PORT (PID: $BACKEND_PID)"

cd "$PROJECT_DIR/frontend"
export PATH="$HOME/.cargo/bin:$PATH"
npm run tauri dev &
FRONTEND_PID=$!
echo "Frontend dev started (PID: $FRONTEND_PID)"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
