# MineTrace — Judge Demo Walkthrough (SIH26023)

**Problem:** AI-Powered Geological, Mining and other Reporting Solution for CMPDI/CIL subsidiaries (Ministry of Coal, Smart Automation).

**One-line pitch:** *"Every number traceable to its source shift entry. Every answer cited to a document and page. Zero data leaves the premises."*

## The 3 required modules → where they live

| Problem statement module | MineTrace implementation |
|---|---|
| 1. Automated Report Generation Platform | Shift entry → deterministic aggregation (Daily → Annual) → AI/template narration → **one-click DOCX/PDF export** |
| 2. Automated Word Cloud & Topic Identification | `/topics` page — word cloud, clustered topics with keywords, month-by-month trends |
| 3. AI-Based Query and Response System | `/documents` "Ask the corpus" — RAG answer with [C1]-style citations (document + page) |

## 5-minute demo script

### Step 0 — Preparation (before judges arrive)
```bash
./scripts/run_dev.sh        # backend on 127.0.0.1:19823 + Tauri app
ollama serve                # if not already running as a service
```
Seed demo data if starting fresh:
```bash
cd backend && ../backend/.venv/Scripts/python.exe scripts/seed_demo.py
```
Have ready: 1 scanned-style PDF, 1 Excel/CSV production sheet, and one
"parliamentary question" (e.g. *"What was coal production in the northern sector
and what caused the stoppages?"*).

### Step 1 — Ingestion (shows it handles messy government inputs)
Open **Documents & Ask** → drag-drop the PDF + spreadsheet.
Point out: OCR for scanned pages, spreadsheet rows flattened into the same
searchable corpus, chunk counts, everything processed **locally**.

### Step 2 — Ask a question (Module 3, the wow moment)
Type the parliamentary question → **Ask**.
Point out: answer with **[C1] [C2] citations** — click a citation, it shows
filename + page + excerpt. Say: *"A Ministry official can defend every line of
this reply because it points back to a source document. This turns a
days-long manual search into minutes."*

### Step 3 — Topics & word cloud (Module 2)
Open **Topics** → word cloud of the whole corpus, clustered topics with
keywords, and upload-month trends.
Point out: *"Officials see what dominates their archive — and emerging
themes — without reading a single page."*

### Step 4 — Report with full traceability (Module 1)
Open **Reports** → generate (or open a seeded) Monthly report → open its
detail page. Show the **reconciliation banner (VALID)**, the lineage table
(every total broken down by source shift entry), then click
**Download DOCX** (and PDF).
Point out: *"Every figure is computed deterministically in code — the LLM
never does arithmetic. The exported report carries a traceability statement;
NumberGuard guarantees no invented number can appear in the narrative."*

### Step 5 — Trust & security (the closer)
Open **System** → netguard active, Ollama models local.
Closing line: *"No cloud, no internet at runtime — the network guard blocks
it. This is deployable inside CMPDI/CIL infrastructure today, satisfying
government data-sovereignty requirements."*

## Anticipated judge questions

- **"How do you prevent AI hallucinations in official reports?"**
  Three layers: (1) all arithmetic is deterministic code, never the LLM;
  (2) NumberGuard rejects any narrative containing a number not present in
  the fact sheet and falls back to a safe template; (3) RAG answers are
  restricted to retrieved context with citations, else they say so.
- **"What about decades of old scanned records?"**
  Batch ingestion pipeline (PDF/image OCR → chunk → embed → index) is format
  and era agnostic; spreadsheets flatten into the same corpus.
- **"Is data safe?"**
  Fully offline: SQLite + ChromaDB + local LLMs (Ollama). Netguard blocks
  non-loopback egress at runtime. On-premise deployment.
- **"Can all 8 subsidiaries use it?"**
  Master data model is subsidiary → mine → bench, configurable approval
  chains per mine/level, consistent metric schema across subsidiaries.
- **"How much faster is reporting?"**
  From days-to-weeks of manual compilation to minutes: ingestion is batch,
  reports generate on demand, and queries return in seconds with citations.

## Known limitations (say them before judges ask)
- Narration quality depends on local model size (qwen2.5:7b); an API-based
  or larger on-prem model would read better — the safety layer is unchanged.
- Topic clustering uses TF-IDF + KMeans; BERTopic is the upgrade path when
  dependencies are pinned.
- Hindi-language documents are not yet processed (roadmap: IndicOCR +
  multilingual embeddings).
