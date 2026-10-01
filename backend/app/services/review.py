"""Human extraction review + per-field document tagging.

Closes the last two abstract gaps:

- Extraction review queue: documents uploaded (scanned PDFs, spreadsheets,
  WhatsApp forwards) land in review_status='PENDING'. A reviewer verifies the
  extracted values (VERIFIED) or flags them (FLAGGED). FLAGGED documents are
  excluded from RAG retrieval so unverified numbers can never reach an answer;
  VERIFIED ones are surfaced with a trust marker. Every decision is written to
  the hash-chained audit log.

- Per-field tagging: document.doc_tags holds corpus-level tags (e.g. HEMM,
  OB, Mine-I, contract) and document_chunk.field_tags holds per-extracted-field
  tags (e.g. ob:147203, coal:38820, shift:A) so reviewers can mark exactly
  which extracted values they checked.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk
from app.db.schema_migration import dump_tags, parse_tags
from app.services.audit import append_audit

REVIEW_STATUSES = ("PENDING", "VERIFIED", "FLAGGED")


def set_doc_tags(db: Session, doc_id: int, tags: list[str]) -> Document | None:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return None
    doc.doc_tags = dump_tags(tags)
    db.flush()
    return doc


def add_doc_tag(db: Session, doc_id: int, tag: str) -> Document | None:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return None
    tags = parse_tags(doc.doc_tags)
    if tag.strip().lower() not in tags:
        tags.append(tag.strip().lower())
        doc.doc_tags = dump_tags(tags)
        db.flush()
    return doc


def remove_doc_tag(db: Session, doc_id: int, tag: str) -> Document | None:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return None
    tags = [t for t in parse_tags(doc.doc_tags) if t != tag.strip().lower()]
    doc.doc_tags = dump_tags(tags)
    db.flush()
    return doc


def set_chunk_field_tags(
    db: Session, chunk_id: int, tags: list[str]
) -> DocumentChunk | None:
    chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
    if not chunk:
        return None
    chunk.field_tags = dump_tags(tags)
    db.flush()
    return chunk


def review_document(
    db: Session,
    doc_id: int,
    decision: str,
    reviewer_id: int,
    note: str | None = None,
    field_tags: list[str] | None = None,
) -> tuple[Document | None, str | None]:
    """Record a review decision. Returns (document, error)."""
    decision = decision.upper()
    if decision not in ("VERIFIED", "FLAGGED"):
        return None, "decision must be VERIFIED or FLAGGED"
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return None, f"document {doc_id} not found"

    doc.review_status = decision
    doc.review_note = note
    doc.reviewed_by = reviewer_id
    doc.reviewed_at = datetime.now(timezone.utc)

    if field_tags is not None:
        tags = dump_tags(field_tags)
        for chunk in doc.chunks:
            chunk.field_tags = tags

    append_audit(
        db,
        reviewer_id,
        f"DOC_REVIEW_{decision}",
        "DOCUMENT",
        doc_id,
        {"note": note or "", "tags": field_tags or []},
    )
    db.flush()
    return doc, None


def review_queue(
    db: Session,
    status: str | None = None,
    tag: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Documents for the review queue, optionally filtered by status or tag."""
    q = db.query(Document)
    if status:
        q = q.filter(Document.review_status == status.upper())
    rows = q.order_by(Document.uploaded_at.desc()).limit(limit).all()
    items = []
    for d in rows:
        tags = parse_tags(d.doc_tags)
        if tag and tag.strip().lower() not in tags:
            continue
        items.append(_doc_summary(d))
    return items


def _doc_summary(d: Document) -> dict:
    return {
        "id": d.id,
        "filename": d.filename,
        "file_type": d.file_type,
        "status": d.status,
        "review_status": d.review_status,
        "review_note": d.review_note,
        "reviewed_by": d.reviewed_by,
        "reviewed_at": d.reviewed_at.isoformat() if d.reviewed_at else None,
        "doc_tags": parse_tags(d.doc_tags),
        "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        "chunk_count": len(d.chunks),
    }


def count_by_status(db: Session) -> dict:
    rows = db.query(Document.review_status, sql_text("count(*)")).group_by(
        Document.review_status
    ).all()
    counts = {s: 0 for s in REVIEW_STATUSES}
    for status_val, n in rows:
        counts[str(status_val)] = int(n)
    return counts
