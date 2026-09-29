from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, User
from app.db.session import get_db
from app.deps import get_current_user
from app.services.audit import append_audit
from app.services.chunking import chunk_pages
from app.services.embeddings import embed_texts
from app.services.ingestion import extract_text, save_upload
from app.services.rag import generate_cited_answer, retrieve
from app.services.vectorstore import add_embeddings, delete_by_doc_id

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    content = await file.read()
    filename = file.filename or "unknown"

    try:
        doc = save_upload(db, filename, content, user.id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    db.flush()

    try:
        doc.status = "PROCESSING"
        db.flush()

        pages = extract_text(doc)
        doc.page_count = len(pages)
        chunks = chunk_pages(pages)

        chunk_texts = []
        chunk_ids = []
        chunk_metas = []
        db_chunks = []

        for i, c in enumerate(chunks):
            chroma_id = f"doc{doc.id}_chunk{i}"
            db_chunk = DocumentChunk(
                document_id=doc.id,
                chunk_index=i,
                text=c["text"],
                page_number=c.get("page_number"),
                char_start=c["char_start"],
                char_end=c["char_end"],
                token_count=c["token_count"],
                chroma_id=chroma_id,
            )
            db.add(db_chunk)
            db.flush()

            chunk_texts.append(c["text"])
            chunk_ids.append(chroma_id)
            chunk_metas.append({
                "document_id": doc.id,
                "chunk_id": db_chunk.id,
                "filename": filename,
                "page_number": c.get("page_number", 0),
            })
            db_chunks.append(db_chunk)

        if chunk_texts:
            embeddings = embed_texts(chunk_texts)
            if embeddings:
                add_embeddings(chunk_ids, embeddings, chunk_texts, chunk_metas)

        doc.status = "READY"
    except Exception as e:
        doc.status = "ERROR"
        doc.error_msg = str(e)[:500]

    append_audit(db, user.id, "UPLOAD", "DOCUMENT", doc.id)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "page_count": doc.page_count,
        "chunk_count": len(chunks) if doc.status == "READY" else 0,
        "status": doc.status,
        "error_msg": doc.error_msg,
    }


@router.get("")
def list_documents(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    docs = db.query(Document).order_by(Document.uploaded_at.desc()).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "page_count": d.page_count,
            "status": d.status,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            "chunk_count": len(d.chunks),
        }
        for d in docs
    ]


@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    delete_by_doc_id(doc_id)
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()

    from app.services.ingestion import delete_document as del_doc

    del_doc(db, doc)
    append_audit(db, user.id, "DELETE", "DOCUMENT", doc_id)
    db.commit()
    return {"deleted": True}


@router.post("/query")
def query_documents(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = body.get("query", "").strip()
    if not query:
        raise HTTPException(422, "Query text required")

    contexts = retrieve(db, query)
    result = generate_cited_answer(query, contexts)

    return {
        "query": query,
        "answer": result["answer"],
        "citations": result["citations"],
        "model": result["model"],
        "context_count": len(contexts),
    }
