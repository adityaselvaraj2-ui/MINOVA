# MineTrace — FEATURE_INVENTORY (Phase 0 Audit)

Date: 2026-09-30 (updated after gap-fill phases). Verified by reading source + running `pytest` (50/50 pass), `scripts/verify_demo_pipeline.py` (17/17 checks), ruff clean, and live UI walkthrough.

## Added in gap-fill phases (post-audit)
- XLSX export (`/reports/{id}/export?format=xlsx`) — deck promise "PDF, Excel, DOC"
- Approval trail `/reports/{id}/approval-trail` — Prepared by / Verified by / Approved by
- Offline sync `POST /sync/shift-entries` (per-entry validation + audit) + `/sync/queue`
- Query router `services/query_router.py` + `POST /documents/ask-routed` (structured / docs / both)
- Conflict detection `data_conflict` + `/conflicts` + human-only resolve (8,000 vs 7,850 t case)
- Anomaly detection `services/anomalies.py` + `/analytics/anomalies` (z-score outliers, hours mismatch)
- Target-vs-actual `services/targets.py` + `/analytics/target_vs_actual` (achievement %, prev-period delta, top downtime causes, factual summary)
- Ministry query pack `services/query_pack.py` + `/reports/query-pack(.pdf)`
- Weather layer `services/weather.py` (CSV offline default; open-meteo OFF by default) + rain-impact + plan engine `services/plan.py` + `/planning/*` + backtest + sample CSV generator
- Hindi support `services/hindi.py` (e5-small multilingual, query translation, Devanagari grounding) + optional reranker `services/reranker.py` (off by default)
- LLM chain qwen3:8b → qwen2.5:7b → llama3.1:8b with <think>-strip (`services/llm/gateway.py`); `/health` reports per-model state
- Fiscal year Apr–Mar helper; `scripts/download_models.py --verify`, `scripts/backup_db.py`, `scripts/eval_rag.py`, `scripts/verify_demo_pipeline.py` (17 checks), `scripts/generate_weather_csv.py`
- Docs: HANDOVER.md, ABSTRACT_GAP_LOG.md (claim-by-claim verification)
- **UI**: Planning page (`/planning` — forecast table w/ STALE badge, rain-impact model, 7-day recovery plan, accept/reject w/ audited reason, backtest); 401 auto-logout + redirect (stale sessions no longer break the Ask/chat flow); `/stack` + word-cloud endpoints

## A. SIH Modules

| # | Feature | Status | Evidence |
|---|---|---|---|
| 1 | Report generation Word+PDF, deterministic figures, LLM narration labelled | **DONE** | [export.py](../backend/app/services/export.py) (DOCX/PDF + "Narration source: LLM/TEMPLATE_FALLBACK" + traceability statement), [factsheet.py](../backend/app/services/factsheet.py), [numberguard.py](../backend/app/services/numberguard.py) guard_check, `/reports/{id}/export`; full chain DAILY→ANNUAL via [aggregation.py](../backend/app/services/aggregation.py) `rollup_reports` |
| 2 | Word cloud + topics, filters | **DONE** | [topics.py](../backend/app/services/topics/topics.py) TF-IDF+KMeans, GET `/documents/topics`, TopicsPage DOM cloud. Subsidiary/year filter: **PARTIAL** (corpus-wide only) |
| 3 | RAG: page-level citations, hybrid search, grounding, fallback | **DONE** | [rag.py](../backend/app/services/rag.py) dense+BM25+RRF, `grounded_pct`, "No relevant documents found." fallback, [Cn] citations |
| 3b | Hindi query support | **MISSING → BUILT** | No Hindi path existed. Built: `services/hindi.py` (transliteration-aware tokenizer + optional Hindi→English query translation via local LLM), tested |

## B. Field-study Features

| # | Feature | Status | Evidence |
|---|---|---|---|
| 4 | Foreman shift-entry form w/ downtime rows, weather, rainfall | **DONE** | [models.py](../backend/app/db/models.py) ShiftEntry (weather_code, rainfall_mm_x10, temperature_c_x10, remarks), DowntimeEvent; [validation.py](../backend/app/services/validation.py) rejects impossible values, uniqueness (mine/bench/date/shift + version); server recomputes operating_min; ShiftEntryPage.tsx UI |
| 5 | Approval workflow SUBMITTED→APPROVED/RETURNED, audit-logged | **DONE** | [approvals.py](../backend/app/services/approvals.py) state machine + ApprovalAction + hash-chained audit [audit.py](../backend/app/services/audit.py); ApprovalQueuePage.tsx |
| 6 | Lineage tables + cascade + drill-down | **MOSTLY DONE → EXTENDED** | LineageEdge/MetricContribution with exactly-one CHECK; rollup; `/reports/{id}/lineage`, `/reconcile`. **Added**: `/reports/{id}/children`, `/reports/{id}/sources` (recursive), FY Apr–Mar option `fiscal_year_boundaries`, UI drill-down links in ReportDetailPage |
| 7 | Target vs actual + achievement % + deterministic descriptions | **PARTIAL → BUILT** | Target table + fact sheet had targets; no achievement endpoint/descriptions. Built: `services/targets.py` (achievement_pct, top downtime causes, prev-period delta — all deterministic) + GET `/analytics/target_vs_actual` |
| 8 | Ministry query pack | **MISSING → BUILT** | Built: `services/query_pack.py` (evidence bundle: target vs actual, downtime causes, rainfall, lineage leaves, source docs → PDF via reportlab) + GET `/reports/query-pack?mine_id&period_start&period_end` |

## C. Platform Capabilities

| Feature | Status | Evidence |
|---|---|---|
| Extraction + review queue | **DONE** | ingestion.py extracts (PDF/DOCX/XLSX/CSV/images w/ OCR fallback); review queue built: review.py + `/documents/review/*` + `/{id}/tags` + `/chunks/{id}/field-tags`; ReviewPage.tsx; FLAGGED docs excluded from RAG (gate live-tested); 8 pytest cases in tests/test_review.py |
| Unit normalisation | **DONE** | units.py |
| Text-to-SQL | **DONE, now scoped** | text_to_sql.py SELECT-only guard; **added**: table allow-list, subsidiary scoping in code (junction on mine.subsidiary_id), scoped-vs-cross-subsidiary tests |
| RBAC role + mine scoping | **DONE** | deps.py get_current_user, role.can_approve, mine_id binding; approvals check |
| Audit log | **DONE** | hash-chained AuditLog + `/audit/verify` |
| Job queue/worker | **PARTIAL** | jobs.py in-process queue; no separate worker (documented) |
| Docker/nginx | **NOT BUILT (by design)** | zero-dependency desktop app (Tauri). Documented as deliberate divergence from teammate repo |
| Backup script | **MISSING → BUILT** | scripts/backup_db.py (SQLite online backup + zip of exports) |
| Eval harness | **MISSING → BUILT (light)** | scripts/eval_rag.py (retrieval hit-rate + grounded_pct on golden Q/A CSV) |

## D. Offline/AI Constraints

| Constraint | Status |
|---|---|
| No cloud calls at runtime | **DONE** — netguard blocks non-loopback sockets; HF_HUB_OFFLINE set at startup |
| Pre-trained models only, no fine-tuning | **DONE** |
| LLM never computes numbers | **DONE** — NumberGuard + fact-sheet-only narration |
| Bilingual EN+HI | **BUILT this phase** (embeddings e5-small multilingual, query translation, tokenizer) |

## E. Weather module (Phase 2) — see WEATHER_MODULE.md

## Model configuration (reconciled)

| Role | Old | Now |
|---|---|---|
| LLM primary | qwen2.5:7b | **qwen3:8b** (config.ollama_primary_model; falls back qwen2.5:7b → llama3.1:8b) |
| Embeddings | bge-small-en-v1.5 (EN only) | **multilingual-e5-small** (384-dim, EN+HI) at `models/multilingual-e5-small` |
| Reranker | none | **BAAI/bge-reranker-v2-m3**, toggle `RERANKER_ENABLED=false` default |
| OCR | PaddleOCR cached + pytesseract fallback | unchanged (Tesseract eng+hin install documented; scanned-page OCR remains a limitation) |
| Time-series | — | **deliberately skipped**: ours is deterministic Monte Carlo (forecast_production.py); zero-shot Chronos would violate "deterministic figures" for official reports. Documented |

Download automation: `scripts/download_models.py` (ollama pulls + hf download + dim/checksum verify). Health: `/api/v1/health` now reports each model (loaded, dims, path) — see `models_loaded` block.

## How to run

```bash
# backend
cd minetrace/backend
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MINETRACE_DEBUG=1 MINETRACE_PORT=19823 \
  .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 19823
# frontend
cd minetrace/frontend && npm run dev   # http://localhost:1420 (login admin/demo123)
# tests
cd minetrace/backend && .venv/Scripts/python.exe -m pytest -q
# model download (once, on a connected machine)
.venv/Scripts/python.exe ../scripts/download_models.py --all
```

## Env vars (prefix MINETRACE_)

DEBUG, PORT, DATA_DIR, OLLAMA_BASE_URL, OLLAMA_PRIMARY_MODEL (qwen3:8b), OLLAMA_SECONDARY_MODEL (llama3.1:8b), EMBEDDING_MODEL_PATH (models/multilingual-e5-small), RERANKER_ENABLED (false), RERANKER_MODEL_PATH, WEATHER_ONLINE (false), WEATHER_PROVIDER (csv), FISCAL_YEAR_START_MONTH (4), ANOMALY_Z_THRESHOLD (3.0)

## DB schema summary

subsidiary, sector, mine, bench, equipment, role, user, approval_chain, shift_entry (+downtime_event), target, report, report_metric, lineage_edge, metric_contribution, report_description, approval_action, audit_log, document, document_chunk, **weather_daily** (new), **plan_suggestion** (new), **data_conflict** (new)

## Known limitations (honest list)

1. Scanned-image OCR falls back to Tesseract when PaddleOCR cannot read a page (install Tesseract eng+hin for best coverage); digital PDFs fully supported.
2. Job worker is in-process (Temporal available as the orchestrated option — multi-level approval E2E verified live on Temporal 1.9.1 + Postgres).
3. Flutter field app (`field_app/`): compiled and verified — `flutter analyze` 0 issues, `flutter test` 2/2, `flutter build web --release` succeeds; an APK additionally needs the Android SDK on the build machine.
5. Enterprise components (PostgreSQL/PostGIS+pgvector, MinIO, Keycloak, Temporal) are fully implemented and config-gated — activate via `infra/docker-compose.yml` + `backend/.env.example`; each falls back to its zero-dependency offline equivalent. See ABSTRACT_GAP_LOG.md §stack.
