# MineTrace — HANDOVER

AI-Powered Geological, Mining & Reporting Platform (SIH26023 · TECH TITANS07X).
Fully offline at runtime · deterministic figures · every number traceable.

## Quick start

```bash
# 0) prerequisites: Python 3.12+, Node 20+, Ollama
# 1) backend venv
cd minetrace/backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # or pip install -e .
# 2) models (once, on a connected machine)
backend/.venv/Scripts/python.exe scripts/download_models.py --all
#    -> ollama pull qwen3:8b qwen2.5:7b llama3.1:8b
#    -> models/multilingual-e5-small, models/bge-reranker-v2-m3 (optional)
# 3) seed demo data (3 mines, FY2025-26 entries)
cd backend && .venv/Scripts/python.exe ../scripts/seed_demo.py
# 4) run
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MINETRACE_DEBUG=1 MINETRACE_PORT=19823 \
  .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 19823
cd ../frontend && npm install && npm run dev      # http://localhost:1420
# login: admin / demo123
```

## Model configuration (reconciled everywhere)

| Role | Model | Env (MINETRACE_) |
|---|---|---|
| LLM primary | qwen3:8b (Ollama) | OLLAMA_PRIMARY_MODEL |
| LLM fallback | qwen2.5:7b | OLLAMA_FALLBACK_1 |
| LLM fallback | llama3.1:8b | OLLAMA_SECONDARY_MODEL |
| Embeddings | intfloat/multilingual-e5-small (384-dim, EN+HI) | EMBEDDING_MODEL_PATH |
| Reranker | BAAI/bge-reranker-v2-m3 (optional) | RERANKER_ENABLED=false, RERANKER_MODEL_PATH |
| OCR | PaddleOCR cached; Tesseract eng+hin optional | — |

`/api/v1/health` → `models_loaded` reports each model's load state + dims.
Verification: `python scripts/download_models.py --verify`

## Offline checklist (air-gapped host)

1. Copy the whole `minetrace/` folder (incl. `models/`) to the host.
2. Set `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` (netguard also enforces
   loopback-only sockets at startup).
3. Weather: drop operator CSVs into `<data_dir>/weather/` —
   `history_<MINE>.csv`, `forecast_<MINE>.csv` (date,rain_mm,temp_max).
   Sample generator: `scripts/generate_weather_csv.py`.
   Online weather is OFF by default (`WEATHER_ONLINE=false`).
4. `python scripts/verify_demo_pipeline.py` → must print ALL CHECKS PASSED.

## Key endpoints (v1)

- Reports: `/reports/generate`, `/reports/{id}/export?format=docx|pdf|xlsx`,
  `/reports/{id}/lineage`, `/reports/{id}/children`, `/reports/{id}/sources`,
  `/reports/{id}/reconcile`, `/reports/{id}/approval-trail`,
  `/reports/query-pack(.pdf)`
- Ask: `/documents/query` (RAG+citations+grounded_pct),
  `/documents/sql` (scoped Text-to-SQL), `/documents/ask-routed` (router)
- Planning: `/planning/weather/import`, `/planning/weather/forecast`,
  `/planning/rain-impact`, `/planning/suggest`, `/planning/suggestions`,
  `/planning/suggestions/{id}/decide`, `/planning/backtest`
- Analytics: `/analytics/stoppage_pareto`, `/analytics/machine_utilization`,
  `/analytics/target_vs_actual`, `/analytics/anomalies`
- Sync: `/sync/shift-entries` (offline replay), `/sync/queue`
- Conflicts: `/conflicts`, `/conflicts/{id}/resolve` (human decides)

## Operations

- Backup: `python scripts/backup_db.py` (SQLite online backup + exports zip)
- RAG eval: `python scripts/eval_rag.py golden.csv`
- Tests: `cd backend && pytest -q` (50 tests)
- Ruff: `ruff check app ../scripts` (clean)

## Enterprise stack (exact abstract architecture, config-gated)

Every abstract component is implemented; each has a zero-dependency fallback
so the demo still runs on one air-gapped laptop. Live view: `GET /api/v1/stack`.

```bash
# bring up PostgreSQL/PostGIS+pgvector, MinIO, Keycloak, Temporal:
cd minetrace/infra && docker compose up -d
# then run the backend with:
#   MINETRACE_DB_BACKEND=postgres MINETRACE_STORAGE_BACKEND=s3
#   MINETRACE_KEYCLOAK_ENABLED=true MINETRACE_TEMPORAL_ENABLED=true
#   (env template: backend/.env.example)
# temporal worker (optional, for orchestrated approvals):
#   python -m app.services.workflows
```

- New endpoints: `/auth/enterprise/{status,login,callback,me}` (Keycloak OIDC),
  `/workflows/status` (Temporal), `/stack` (live stack report),
  `/analytics/word-cloud` (SVG)
- Flutter field app: `field_app/` (offline capture, encrypted SQLCipher queue,
  sync via `/sync/shift-entries`; build instructions in `field_app/README.md`)
- BGE-M3 exact-stack retrieval: set `MINETRACE_EMBEDDING_MODEL_PATH=models/bge-m3`
  and re-ingest (`python ../scripts/batch_ingest_dataset.py --reindex`)

## Known limitations

All four deck asterisks are now closed — see ABSTRACT_GAP_LOG.md §"Live
verification session (2026-10-01)" for the evidence: enterprise stack
exercised live (Postgres 16.9 multi-level approval E2E via Temporal, Keycloak
26.7.4 role mapping, S3 via s3proxy 4.1.1), BGE-M3 active in RAG with cited
answers, extraction review queue + per-field tagging with the FLAGGED-docs
retrieval gate (58 backend tests passing), and the Flutter app compiled
(analyze/test/build-web). Remaining documented limitation: scanned-image OCR
wants a Tesseract install (eng+hin) as backup to PaddleOCR.
