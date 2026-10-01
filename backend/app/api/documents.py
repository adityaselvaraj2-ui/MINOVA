from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, User
from app.db.schema_migration import parse_tags
from app.db.session import get_db
from app.deps import get_current_user
from app.schemas.documents import (
    ChunkFieldTagsUpdate,
    Citation,
    DocTagAdd,
    DocTagsUpdate,
    QueryRequest,
    QueryResponse,
    ReviewDecision,
)
from app.services import review as review_svc
from app.services import storage
from app.services.audit import append_audit
from app.services.chunking import chunk_pages
from app.services.embeddings import embed_texts
from app.services.ingestion import extract_text, save_upload
from app.services.query_router import route_query
from app.services.rag import generate_cited_answer, retrieve
from app.services.text_to_sql import run_text_to_sql
from app.services.topics import compute_topics
from app.services.vector_dispatch import add_embeddings, delete_by_doc_id

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
        "storage": storage.backend_name(),
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
            "review_status": getattr(d, "review_status", "PENDING"),
            "doc_tags": parse_tags(d.doc_tags),
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


@router.get("/review/queue")
def get_review_queue(
    status: str | None = None,
    tag: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Extraction review queue (asterisk-4 feature).

    Returns documents with review status, review metadata and per-field tags.
    `?status=PENDING` shows what still needs a human pass; `?tag=hemm`
    filters by document tag.
    """
    if limit < 1 or limit > 500:
        raise HTTPException(422, "limit must be 1-500")
    if status and status.upper() not in review_svc.REVIEW_STATUSES:
        raise HTTPException(422, "status must be PENDING, VERIFIED or FLAGGED")
    return review_svc.review_queue(db, status=status, tag=tag, limit=limit)


@router.get("/review/counts")
def get_review_counts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return review_svc.count_by_status(db)


@router.post("/review/{doc_id}")
def review_document(
    doc_id: int,
    body: ReviewDecision,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Record a review decision (VERIFIED keeps the doc in retrieval; FLAGGED
    removes it until corrected). Optionally tags the specific extracted
    fields that were checked."""
    doc, err = review_svc.review_document(
        db,
        doc_id,
        body.decision,
        reviewer_id=user.id,
        note=body.note,
        field_tags=body.field_tags,
    )
    if err:
        raise HTTPException(422, err)
    db.commit()
    return {"ok": True, "review_status": doc.review_status,
            "reviewed_at": doc.reviewed_at.isoformat()}


@router.put("/{doc_id}/tags")
def set_tags(
    doc_id: int,
    body: DocTagsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Replace the document's corpus tags (lower-cased, de-duplicated)."""
    doc = review_svc.set_doc_tags(db, doc_id, body.tags)
    if not doc:
        raise HTTPException(404, "Document not found")
    append_audit(db, user.id, "DOC_TAGS_SET", "DOCUMENT", doc_id,
                 {"tags": body.tags})
    db.commit()
    return {"id": doc.id, "doc_tags": parse_tags(doc.doc_tags)}


@router.post("/{doc_id}/tags")
def add_tag(
    doc_id: int,
    body: DocTagAdd,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = review_svc.add_doc_tag(db, doc_id, body.tag)
    if not doc:
        raise HTTPException(404, "Document not found")
    append_audit(db, user.id, "DOC_TAG_ADD", "DOCUMENT", doc_id,
                 {"tag": body.tag})
    db.commit()
    return {"id": doc.id, "doc_tags": parse_tags(doc.doc_tags)}


@router.delete("/{doc_id}/tags/{tag}")
def remove_tag(
    doc_id: int,
    tag: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = review_svc.remove_doc_tag(db, doc_id, tag)
    if not doc:
        raise HTTPException(404, "Document not found")
    append_audit(db, user.id, "DOC_TAG_REMOVE", "DOCUMENT", doc_id,
                 {"tag": tag})
    db.commit()
    return {"id": doc.id, "doc_tags": parse_tags(doc.doc_tags)}


@router.put("/chunks/{chunk_id}/field-tags")
def set_chunk_tags(
    chunk_id: int,
    body: ChunkFieldTagsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Per-field tags on a chunk, e.g. ["ob:147203", "coal:38820"] — marks
    exactly which extracted values a reviewer has checked."""
    chunk = review_svc.set_chunk_field_tags(db, chunk_id, body.tags)
    if not chunk:
        raise HTTPException(404, "Chunk not found")
    append_audit(db, user.id, "CHUNK_TAGS_SET", "DOCUMENT",
                 chunk.document_id, {"chunk_id": chunk_id, "tags": body.tags})
    db.commit()
    return {"chunk_id": chunk.id, "field_tags": parse_tags(chunk.field_tags)}


@router.get("/topics")
def get_topics(
    n_topics: int = 8,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    n_topics = max(2, min(n_topics, 15))
    return compute_topics(db, n_topics=n_topics)


@router.post("/query", response_model=QueryResponse)
def query_documents(
    body: QueryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = body.query.strip()
    if not query:
        raise HTTPException(422, "Query text required")

    contexts = retrieve(db, query)
    result = generate_cited_answer(query, contexts)

    append_audit(db, user.id, "QUERY", "DOCUMENT", 0, {"query": query[:200]})
    db.commit()

    source = "LLM" if result["model"] else "FALLBACK"
    return QueryResponse(
        query=query,
        answer=result["answer"],
        citations=[Citation(**c) for c in result["citations"]],
        model=result["model"],
        context_count=len(contexts),
        source=source,
        grounded_pct=result.get("grounded_pct", 0),
    )


@router.post("/ask-routed")
def ask_routed(
    body: QueryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Abstract: 'A query-routing layer determines whether the question
    requires database search, document retrieval or both.' One endpoint
    that routes and merges: structured narration + cited RAG answer."""
    question = body.query.strip()
    if not question:
        raise HTTPException(422, "Question text required")
    decision = route_query(question)

    result: dict = {"question": question, "routing": decision}

    if decision["structured"]:
        sql_res = run_text_to_sql(db, question, user=user)
        result["structured"] = {
            "ok": sql_res.get("ok"),
            "sql": sql_res.get("sql"),
            "columns": sql_res.get("columns"),
            "rows": sql_res.get("rows")[:25],
            "narrative": sql_res.get("narrative"),
            "error": sql_res.get("error"),
        }

    if decision["documents"]:
        contexts = retrieve(db, question)
        rag_res = generate_cited_answer(question, contexts)
        result["documents"] = rag_res

    append_audit(db, user.id, "ASK_ROUTED", "DOCUMENT", 0,
                 {"q": question[:200], "mode": decision["mode"]})
    db.commit()
    return result


@router.post("/sql")
def text_to_sql_endpoint(
    body: QueryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Structured question -> safe generated SELECT -> narrated result.
    Read-only; guarded against injection and writes."""
    question = body.query.strip()
    if not question:
        raise HTTPException(422, "Question text required")
    result = run_text_to_sql(db, question, user=user)
    append_audit(db, user.id, "SQL_QUERY", "DOCUMENT", 0, {"q": question[:200]})
    db.commit()
    return result
