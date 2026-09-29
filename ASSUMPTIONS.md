# MineTrace Assumptions

Decisions made during development that need validation.

## A1: Python version compatibility
- Python 3.14.3 is installed. Some packages (PaddleOCR, hdbscan C extension) may lack wheels for 3.14.
- Fallback: use sklearn.cluster.HDBSCAN (scikit-learn >= 1.3) for BERTopic.
- PaddleOCR: will attempt install; if it fails, will use pdfplumber-only with OCR disabled and document the limitation.

## A2: Week convention — MONTH_CLIPPED
- Planning weeks are numbered within a month, clipped at month boundaries: days 1-7, 8-14, 15-21, 22-28, 29-end.
- This keeps Weekly→Monthly as a strict tree. ISO weeks straddle months and would break lineage.
- **Needs validation with CMPDI field operations.**

## A3: Stripping ratio definition
- Defined as OB_m3 / production_t. Made configurable.
- **Needs validation with mining engineers** — some sites may use weight-based OB.

## A4: Approval hierarchy
- The hierarchy (Foreman → Exec Supervisor → AE → EE → DCM → ACM → CM → DGM → GM → CGM → Directors → CMD) is from field notes and treated as UNVERIFIED and configurable.

## A5: Shift structure
- 3 shifts per day (A, B, C), ~8 hours each. Configurable.

## A6: Rust PATH
- Rust installed at C:/Users/Aditya/.cargo/bin/ but not on Git Bash PATH.
- Using full paths or PATH export for cargo/rustc commands.

## A7: Ollama PATH
- Ollama installed at C:/Users/Aditya/AppData/Local/Programs/Ollama/ollama.exe.
- Backend connects to http://127.0.0.1:11434 at runtime.
