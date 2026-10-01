# Abstract / Description → Implementation Verification Log

Every claim in the SIH abstract & description (and the MINOVA deck) checked
against the codebase. Status: ✅ built · 🟡 partial (documented) · ➕ added
this phase to close the gap. Honest divergences are listed, not hidden.

## Workflow & roles
| Claim | Status | Where |
|---|---|---|
| Foreman shift-wise entry | ✅ | ShiftEntryPage.tsx, `POST /shift-entries` |
| **Mobile app, offline capture → secure sync** | ➕ | Desktop is offline-first by design (Tauri+SQLite). Sync contract added: `POST /sync/shift-entries` — client replays queued entries; server re-validates each (same rules as online), per-entry accept/reject, device-id audited. Same contract serves a future Flutter client. |
| Role-based access (foreman→…→CMPDI chain) | ✅ | roles table w/ ranks, ApprovalChain per mine/level, ApprovalQueuePage. Seed covers FOREMAN→GM; chain config allows the full hierarchy |
| Supervisor/engineer/manager review levels | ✅ | multi-step `current_step` approval (approvals.py) |

## Deterministic verification chain (the 8,000 t example)
| Claim | Status | Where |
|---|---|---|
| 3 shifts (3,100+2,900+2,000) → 8,000 t daily, by backend rules not LLM | ✅ | aggregation.py sums `report_metric` from APPROVED entries; LLM never computes (NumberGuard) |
| Value linked to source records, person, reviewers, timestamps | ✅ | LineageEdge+MetricContribution; foreman_id; ApprovalAction.ts; audit_log chain |
| **Conflict (8,000 vs 7,850) → human verification, AI not final authority** | ➕ | `data_conflict` table (OPEN/RESOLVED_*), `GET /conflicts`, `POST /conflicts/{id}/resolve` (resolution note REQUIRED, human only), audit-logged |
| Audit trail of submissions/corrections/reviews | ✅ | hash-chained audit_log + `/audit/verify` |

## Documents & retrieval
| Claim | Status | Where |
|---|---|---|
| PDFs/images/spreadsheets/historical ingestion | ✅ | ingestion.py (pdf, docx, xlsx/xls/csv, images) |
| Object storage separation (metadata in DB) | ✅(adapted) | files on disk under data_dir/uploads + document table metadata (MinIO-equivalent for desktop scale; documented divergence) |
| OCR + document understanding | 🟡 | PaddleOCR (digital PDFs fully supported). Scanned-image OCR needs Tesseract binary — documented limitation (deck lists Tesseract as the intended OCR) |
| Semantic retrieval (different wording finds doc) | ✅ | multilingual-e5-small embeddings + Chroma, hybrid BM25+dense+RRF |
| **Hindi & English support** | ✅ | e5-small multilingual, Hindi detection + local-LLM query translation (hindi.py), Devanagari-aware grounded_pct, answer-in-Hindi prompt |
| Identify document types / tag info | ✅ | file_type stored; corpus tags (`document.doc_tags`, tag-filtered review queue) + per-field chunk tags (`document_chunk.field_tags`, e.g. `ob:147203`) via review.py + `/documents/{id}/tags` + `/chunks/{id}/field-tags`; ReviewPage.tsx UI |

## AI layer
| Claim | Status | Where |
|---|---|---|
| **Query router: DB search / docs / both** | ➕ | query_router.py + `POST /documents/ask-routed` (merged structured narration + cited RAG answer) |
| Numeric questions from verified structured data | ✅ | Text-to-SQL w/ SELECT-only guard, table allow-list, per-user subsidiary scoping (injected in code), row cap |
| Combined structured+documents answers | ✅ | ask-routed merges both lanes |
| Cited answers, faithfulness score, no unsupported numbers | ✅ | [C1] citations, grounded_pct, unverified_numbers warning |

## Reports & intelligence
| Claim | Status | Where |
|---|---|---|
| Daily/weekly/monthly/yearly deterministic aggregation | ✅ | rollup_reports chain, month-clipped weeks, FY Apr–Mar helper |
| Automated report generation in PDF/Excel/DOC | ✅ | export.py (DOCX/PDF) ➕ export_xlsx.py (XLSX); `/reports/{id}/export?format=` |
| **Prepared by / Verified by / Approved by on reports** | ➕ | `/reports/{id}/approval-trail` (aggregated SUBMIT/APPROVE/RETURN actors); traceability statement in every export |
| Word cloud + topic identification | ✅ | topics.py TF-IDF+KMeans, TopicsPage |
| **Anomaly detection → human review signals** | ✅(new) | anomalies.py: production z-score outliers (IsolationForest-equivalent deterministic z-test on trailing stats), operating-hours mismatch; `/analytics/anomalies`. ML (iForest/XGBoost) noted in deck as optional future predictive analytics — deterministic stats chosen so flags are explainable |
| Evidence & verification status inside reports | ✅ | lineage tables in DOCX/PDF/XLSX, description guard_result + human_reviewed flags |

## Weather-aware target recovery (deck's headline innovation)
| Claim | Status | Where |
|---|---|---|
| Weather + production gaps + history → feasible recovery plans | ✅ | weather.py (CSV provider offline default; open-meteo behind WEATHER_ONLINE=false), plan.py (rain-impact P25/50/75 per bin + lag, P95 capacity cap, redistribution, unrecoverable shortfall), plan_suggestion PENDING/ACCEPTED/REJECTED w/ required reason, never auto-applied |
| Offline import | ✅ | scripts/generate_weather_csv.py samples + operator CSV guide |
| Trust calibration | ✅ | /planning/backtest (predicted vs actual loss, MAE/MAPE); STALE badge on old forecasts |

## Stack claims (abstract) — IMPLEMENTED, config-gated with offline fallbacks

Every component from the abstract's technology architecture now exists as a
code-level implementation. Each one activates via an env switch (see
`backend/.env.example` + `infra/docker-compose.yml`); each degrades to a
zero-dependency fallback so the SIH demo still runs on one air-gapped laptop.
`GET /api/v1/stack` reports live which side of each switch is serving.

| Abstract says | Implemented in | Activates when | Offline fallback |
|---|---|---|---|
| Flutter offline-first field app | `field_app/` (lib/: login, offline capture, encrypted SQLCipher queue, sync service) — platform folders scaffolded via `flutter create .`, `flutter analyze` clean, `flutter test` 2/2, `flutter build web` ✔ | `flutter run` (needs Flutter SDK + device) | Tauri desktop UI + same `/sync/shift-entries` contract |
| PostgreSQL/PostGIS | `infra/docker-compose.yml` + `infra/Dockerfile.postgres`, backend-aware engine (`db/session.py`), `MINETRACE_DB_BACKEND=postgres` | compose up + env switch | SQLite (WAL) |
| pgvector semantic retrieval | `services/pgvector_store.py` (drop-in twin of the Chroma store, `services/vector_dispatch.py`) | same postgres switch | ChromaDB |
| MinIO/S3 object storage | `services/storage.py` (boto3 S3 API, auto-bucket) — live-verified against s3proxy 4.1.1 (SigV4, filesystem blobstore): bucket create + put/get/list roundtrip + app-layer save/open PASS | `MINETRACE_STORAGE_BACKEND=s3` | local filesystem + DB metadata |
| Keycloak auth | `services/keycloak.py` + `api/keycloak.py` (OIDC code flow, userinfo, role mapping) + `infra/keycloak/minetrace-realm.json` | `MINETRACE_KEYCLOAK_ENABLED=true` | local argon2 + JWT RBAC |
| Temporal workflows | `services/workflows.py` (workflow + signal + query + activities + worker `python -m app.services.workflows`) | `MINETRACE_TEMPORAL_ENABLED=true` | in-process approval state machine + hash-chained audit |
| PaddleOCR | ✅ primary OCR engine (`services/ingestion.py`) | always | Tesseract via pytesseract |
| BGE-M3 + pgvector | model downloaded at `models/bge-m3`; `services/embeddings.py` family-switch loads it with correct CLS pooling (1024-d) — live-verified: 98 files reindexed, health dim 1024, cited RAG answer end-to-end | `MINETRACE_EMBEDDING_MODEL_PATH=models/bge-m3` + re-ingest (RAM note: ~2.3 GB fp32 alongside qwen3) | multilingual-e5-small (384-d, EN+HI, demo default) |
| Qwen3 models | ✅ qwen3:8b primary via `services/llm/gateway.py` (think-off, keep-alive, fallback chain) | always | — |
| React.js web portal | ✅ existing frontend | always | — |

## Not built (documented limitations)
1. Scanned-image OCR requires installing Tesseract (eng+hin) as backup to PaddleOCR.

## Live verification session (2026-10-01) — all four asterisks closed
Every item the deck previously asterisked was exercised live on this machine
(Windows, portable stack under `.tools/`, all localhost, zero cloud):

1. **Enterprise stack exercised end-to-end**
   - PostgreSQL 16.9 (portable, port 5434): 23 tables created + review/tagging
     migration ensured; 13,068 shift entries seeded (BigInteger fix for
     milli-unit columns verified); backend healthy in `postgres` mode.
   - Keycloak 26.7.4 (port 8180): realm `minetrace` imported; ROPC token for
     `s.iyer` → `/auth/enterprise/me` returns `minetrace_role: GM` from JWT
     realm roles.
   - Temporal 1.9.1 (port 7233, UI 8233): single worker on the PG task queue;
     **full multi-level approval E2E** — `start_entry_workflow` → APPROVE
     (AE) → activity commits step 1 to Postgres → APPROVE (EE) → outcome
     APPROVED; history `['STARTED:AE','APPROVE:AE','APPROVE:EE']`, DB status
     APPROVED step 2. Fixes applied this session: module-level workflow class
     (temporalio rejects decorated functions), `UnsandboxedWorkflowRunner`,
     `wait_condition` TimeoutError handling, `timedelta` timeouts, no logging
     inside workflow code, already-started-as-resume.
   - S3-compatible object storage: MinIO binaries are gone upstream (project
     archived, dl.min.io returns 410) — substituted **s3proxy 4.1.1** (fat jar
     on JDK 21, port 8333, SigV4 auth; anonymous request → 403). boto3 bucket
     create + put/get/list roundtrip PASS; app `services/storage.py` in
     `s3` mode PASS. docker-compose still ships real MinIO for Linux demos.
2. **BGE-M3 active and verified in RAG**: reindexed corpus (98 files, 122
   chunks) with `MINETRACE_EMBEDDING_MODEL_PATH=models/bge-m3` (1024-dim CLS
   pooling); embedding_dim auto-synced via `model_post_init` (collection
   `minetrace_docs_1024`); health reports `dim 1024 / match true`. Live query
   → RRF fusion → qwen3:8b returned a cited answer (`10,348 kt [C1]` →
   *NLC Mine-I year summary 2026 p1*).
3. **Extraction review queue + per-field tagging built and gated**: docs land
   PENDING; reviewer VERIFIED/FLAGGED with note + per-field tags
   (`ob:147203`); every decision hash-chain-audited. **Gate proven live**:
   flagging the cited doc dropped contexts 12→11, removed it from citations,
   and the answer re-grounded on other docs. 8 new pytest cases
   (`tests/test_review.py`) — full suite **58 passed**, ruff clean on touched
   files. UI: `/review` ReviewPage (filters w/ counts, verify/flag, tag
   CRUD).
4. **Flutter app compiled**: `flutter create .` scaffolded android/ios/web;
   `flutter analyze` 0 issues (fixed real `String`/`double` getter bug in
   models.dart); `flutter test` 2/2; `flutter build web --release` succeeds
   (55s, artifact `build/web`). APK build needs the Android SDK (not
   installed on this box); analyze/test/build-web are the verification bar.
