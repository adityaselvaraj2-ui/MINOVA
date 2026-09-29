# MineTrace Architecture

## Overview
MineTrace is an offline, source-to-report intelligence platform for CMPDI/CIL subsidiaries.
It captures operational mining data at the shift level, aggregates it deterministically through
a strict period hierarchy, and provides AI-powered document search, topic discovery, and
cited question-answering — all running locally with zero cloud dependencies.

## Stack
- **Desktop shell:** Tauri v2 (Rust) wrapping a React+TypeScript+Vite frontend
- **Backend:** Python FastAPI, bound to 127.0.0.1 only, run as a sidecar process
- **Storage:** SQLite (relational), ChromaDB (vectors), local filesystem (documents)
- **AI:** Ollama (qwen2.5 primary, llama3.1 secondary), bge-small-en-v1.5 embeddings, PaddleOCR, BERTopic

## Key Invariants
1. **Deterministic arithmetic only** — all sums, totals, averages computed in Python/SQL, never by LLM
2. **Zero cloud calls at runtime** — netguard.py blocks all non-loopback connections
3. **Verified data only** — aggregates use only APPROVED shift entries
4. **Full traceability** — every number traces to source shift entries via lineage edges
5. **Facts vs interpretation** — AI text split into cited facts and labelled interpretation
6. **Human accountability** — approvals are human actions in an append-only audit log
7. **Graceful degradation** — everything except AI features works without Ollama

## Data Flow
```
Shift Entry (leaf) → Daily Report → Weekly → Monthly → Quarterly → Half-Yearly → Annual
     ↓                    ↓
  Downtime Events    Lineage Edges + Metric Contributions
     ↓                    ↓
  Cause Records      Fact Sheet → Grounded Description (LLM)
                          ↓
                     Number Guard (validates every figure)
```

## Module Map
- **Module 1:** Shift entry, deterministic reporting, data lineage
- **Module 2:** Topic modeling and interactive word cloud
- **Module 3:** Local RAG with cited answers
