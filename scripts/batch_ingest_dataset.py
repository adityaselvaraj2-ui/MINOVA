"""Batch-ingest the NLC dataset into MineTrace's RAG corpus.

Walks dataset/<year>/<month>/ and uploads the machine-readable summaries
(daily_flat.csv, summary.csv, machine_utilization.csv, stoppage_log.csv)
through the normal /documents/upload pipeline so they are chunked, embedded
and queryable. Uses the direct service layer (no HTTP), so it works offline.

Usage:
    cd backend
    .venv/Scripts/python.exe ../scripts/batch_ingest_dataset.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import settings  # noqa: E402
from app.db.models import Document, Role, User  # noqa: E402
from app.db.session import get_session_factory, init_db  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import storage  # noqa: E402
from app.services.ingestion import _read_spreadsheet_rows  # noqa: E402


def ensure_user(session) -> User:
    if not session.query(Role).filter(Role.code == "ADMIN").first():
        session.add(Role(code="ADMIN", rank=0, label="Administrator",
                         can_enter=True, can_approve=True, verified=True))
        session.flush()
    user = session.query(User).filter(User.username == "admin").first()
    if not user:
        user = User(username="admin", full_name="System Administrator",
                    password_hash=hash_password("demo123"), role_code="ADMIN")
        session.add(user)
        session.commit()
    return user


def purge_nlc_docs(session) -> int:
    """--reindex support: drop existing NLC corpus docs (chunks, vectors, rows)
    so they can be re-embedded with the current embedding model."""
    from app.db.models import DocumentChunk
    from app.services.vector_dispatch import delete_by_doc_id

    # Stale collections first: when the embedding model changed (e.g. e5 384-dim
    # to BGE-M3 1024-dim), the old collection rejects new-width vectors.
    if settings.db_backend != "postgres":
        from app.services.vectorstore import drop_all_collections

        dropped = drop_all_collections()
        if dropped:
            print(f"Dropped {dropped} stale Chroma collection(s)")

    docs = session.query(Document).filter(Document.filename.like("NLC Mine-I%")).all()
    for d in docs:
        delete_by_doc_id(d.id)
        session.query(DocumentChunk).filter(DocumentChunk.document_id == d.id).delete()
        session.delete(d)
    session.commit()
    return len(docs)


def ingest_file(session, user: User, path: Path, label: str) -> bool:
    existing = (
        session.query(Document)
        .filter(Document.filename == label)
        .first()
    )
    if existing:
        return False

    content = path.read_bytes()
    key = storage.save_bytes(storage.new_key(label + path.suffix), content)
    doc = Document(
        filename=label,
        file_path=key,
        file_type="SPREADSHEET",
        file_size=len(content),
        uploaded_by=user.id,
        status="UPLOADED",
    )
    session.add(doc)
    session.flush()

    from app.services.chunking import chunk_pages
    from app.services.embeddings import embed_texts
    from app.services.vector_dispatch import add_embeddings

    # Spreadsheet parser needs a real file; materialize the stored object.
    tmp = settings.page_cache_path / f"ingest_{doc.id}{path.suffix}"
    tmp.write_bytes(content)
    try:
        rows = _read_spreadsheet_rows(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    lines = [" | ".join(c.strip() for c in row).strip(" |") for row in rows]
    text = "\n".join(line for line in lines if line)
    pages = [{"page": 1, "text": text}]

    doc.status = "PROCESSING"
    session.flush()
    chunks = chunk_pages(pages)
    chunk_texts, ids, metas = [], [], []
    for i, c in enumerate(chunks):
        chroma_id = f"doc{doc.id}_chunk{i}"
        from app.db.models import DocumentChunk
        db_chunk = DocumentChunk(
            document_id=doc.id, chunk_index=i, text=c["text"],
            page_number=1, char_start=c["char_start"], char_end=c["char_end"],
            token_count=c["token_count"], chroma_id=chroma_id,
        )
        session.add(db_chunk)
        session.flush()
        chunk_texts.append(c["text"])
        ids.append(chroma_id)
        metas.append({"document_id": doc.id, "chunk_id": db_chunk.id,
                      "filename": label, "page_number": 1})

    vecs = embed_texts(chunk_texts)
    if vecs:
        add_embeddings(ids, vecs, chunk_texts, metas)
    doc.page_count = 1
    doc.status = "READY"
    return True


def main() -> None:
    settings.ensure_dirs()
    init_db()
    session = get_session_factory()()
    user = ensure_user(session)

    if "--reindex" in sys.argv:
        n = purge_nlc_docs(session)
        print(f"Purged {n} existing NLC documents for re-embedding.")

    dataset_root = Path(__file__).resolve().parent.parent / "dataset"
    files = []
    for year_dir in sorted(dataset_root.glob("2*")):
        if not year_dir.is_dir():
            continue
        files.append((year_dir / "year_summary.csv",
                      f"NLC Mine-I year summary {year_dir.name}"))
        for month_dir in sorted(year_dir.glob("[0-1][0-9]")):
            if not month_dir.is_dir():
                continue
            ym = f"{year_dir.name}-{month_dir.name}"
            files.append((month_dir / "daily_flat.csv",
                          f"NLC Mine-I daily production {ym}"))
            files.append((month_dir / "summary.csv",
                          f"NLC Mine-I month summary {ym}"))
            files.append((month_dir / "machine_utilization.csv",
                          f"NLC Mine-I machine utilization {ym}"))
            files.append((month_dir / "stoppage_log.csv",
                          f"NLC Mine-I stoppage log {ym}"))

    added = skipped = 0
    for path, label in files:
        if not path.exists():
            continue
        if ingest_file(session, user, path, label):
            added += 1
        else:
            skipped += 1
    session.commit()
    session.close()
    print(f"Ingested {added} files ({skipped} already present) into the RAG corpus.")


if __name__ == "__main__":
    main()
