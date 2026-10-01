"""Extraction review queue + per-field document tagging (asterisk 4).

Covers the review service layer, the document review/tag API routes, the
hash-chained audit trail for decisions, and the RAG gate that keeps FLAGGED
documents out of retrieval.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def review_user(client):
    from app.db.models import Role, User
    from app.db.session import get_session_factory
    from app.security import hash_password

    session = get_session_factory()()
    if not session.query(Role).filter(Role.code == "FOREMAN").first():
        session.add(Role(code="FOREMAN", rank=1, label="Foreman",
                         can_enter=True, can_approve=False))
        session.flush()
    if not session.query(User).filter(User.username == "review_user").first():
        session.add(User(
            username="review_user", full_name="Review User",
            password_hash=hash_password("pass"), role_code="FOREMAN",
        ))
        session.commit()
    user = session.query(User).filter(User.username == "review_user").first()
    uid = user.id
    session.close()
    return uid


@pytest.fixture()
def review_doc(client, review_user):
    """A READY document with two chunks, directly via the DB."""
    from app.db.models import Document, DocumentChunk
    from app.db.session import get_session_factory

    session = get_session_factory()()
    doc = Document(
        filename="test_review_doc.pdf", file_path="/tmp/test_review.pdf",
        file_type="PDF", file_size=100, uploaded_by=review_user, status="READY",
    )
    session.add(doc)
    session.flush()
    # Unique token keeps this doc's chunks at the top of BM25 even though the
    # shared test database accumulates identically-worded chunks from other
    # tests in this file.
    for i, text in enumerate([
        f" OB removal 147203 cum zztok{doc.id}",
        f" Coal produced 38820 t zztok{doc.id}",
    ]):
        session.add(DocumentChunk(
            document_id=doc.id, chunk_index=i, text=text,
            page_number=1, char_start=0, char_end=len(text),
            token_count=len(text.split()),
        ))
    session.commit()
    doc_id = doc.id
    session.close()
    return doc_id


def _review_token(client) -> str:
    resp = client.post("/api/v1/auth/login", json={
        "username": "review_user", "password": "pass",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ---------- service layer ----------


def test_review_service_verify_and_flag(client, review_doc, review_user):
    from app.db.models import DocumentChunk
    from app.db.schema_migration import parse_tags
    from app.db.session import get_session_factory
    from app.services import review as review_svc

    session = get_session_factory()()

    doc, err = review_svc.review_document(
        session, review_doc, "VERIFIED", reviewer_id=review_user,
        note="checked", field_tags=["ob:147203", "coal:38820"],
    )
    assert err is None
    assert doc.review_status == "VERIFIED"
    # field_tags land on the document's chunks (per-extracted-field tags).
    chunk0 = session.query(DocumentChunk).filter(
        DocumentChunk.document_id == review_doc,
        DocumentChunk.chunk_index == 0,
    ).first()
    assert parse_tags(chunk0.field_tags) == ["ob:147203", "coal:38820"]

    doc, err = review_svc.review_document(
        session, review_doc, "FLAGGED", reviewer_id=review_user, note="wrong",
    )
    assert err is None
    assert doc.review_status == "FLAGGED"
    session.commit()

    bad, err = review_svc.review_document(
        session, review_doc, "MAYBE", reviewer_id=review_user,
    )
    assert bad is None and err and "VERIFIED or FLAGGED" in err
    session.close()


def test_doc_tag_crud(client, review_doc):
    from app.db.models import Document
    from app.db.schema_migration import parse_tags
    from app.db.session import get_session_factory
    from app.services import review as review_svc

    session = get_session_factory()()
    review_svc.set_doc_tags(session, review_doc, ["Mine-I", "HEMM"])
    review_svc.add_doc_tag(session, review_doc, "hemm")  # dup, no-op
    review_svc.add_doc_tag(session, review_doc, "OB")
    review_svc.remove_doc_tag(session, review_doc, "mine-i")

    doc = session.query(Document).filter(Document.id == review_doc).first()
    assert parse_tags(doc.doc_tags) == ["hemm", "ob"]
    session.close()


def test_chunk_field_tags(client, review_doc):
    from app.db.models import DocumentChunk
    from app.db.schema_migration import parse_tags
    from app.db.session import get_session_factory
    from app.services import review as review_svc

    session = get_session_factory()()
    chunk = session.query(DocumentChunk).filter(
        DocumentChunk.document_id == review_doc,
        DocumentChunk.chunk_index == 0,
    ).first()
    updated = review_svc.set_chunk_field_tags(session, chunk.id, ["ob:147203"])
    assert parse_tags(updated.field_tags) == ["ob:147203"]

    assert review_svc.set_chunk_field_tags(session, -1, ["x"]) is None
    session.close()


def test_review_queue_and_counts(client, review_doc, review_user):
    from app.db.session import get_session_factory
    from app.services import review as review_svc

    session = get_session_factory()()
    review_svc.review_document(
        session, review_doc, "FLAGGED", reviewer_id=review_user, note="gate",
    )
    session.commit()
    queue = review_svc.review_queue(session, status="FLAGGED")
    assert any(d["id"] == review_doc for d in queue)
    counts = review_svc.count_by_status(session)
    assert counts["FLAGGED"] >= 1
    session.close()


def test_review_decision_is_audited(client, review_doc, review_user):
    from app.db.models import AuditLog
    from app.db.session import get_session_factory
    from app.services import review as review_svc
    from app.services.audit import verify_audit_chain

    session = get_session_factory()()
    review_svc.review_document(
        session, review_doc, "VERIFIED", reviewer_id=review_user, note="audit",
    )
    session.commit()
    actions = {
        e.action for e in session.query(AuditLog)
        .filter(AuditLog.subject_type == "DOCUMENT",
                AuditLog.subject_id == review_doc).all()
    }
    assert "DOC_REVIEW_VERIFIED" in actions
    # Full-chain verification includes the review decision entry above.
    assert verify_audit_chain(session)["valid"] is True
    session.close()


# ---------- API layer ----------


def test_api_review_flow(client, review_doc):
    token = _review_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        f"/api/v1/documents/review/{review_doc}",
        json={"decision": "VERIFIED", "note": "api check",
              "field_tags": ["coal:38820"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["review_status"] == "VERIFIED"

    resp = client.put(
        f"/api/v1/documents/{review_doc}/tags",
        json={"tags": ["hemm", "mine-i"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert set(resp.json()["doc_tags"]) == {"hemm", "mine-i"}

    resp = client.post(
        f"/api/v1/documents/{review_doc}/tags",
        json={"tag": "extra"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert "extra" in resp.json()["doc_tags"]

    resp = client.delete(
        f"/api/v1/documents/{review_doc}/tags/extra", headers=headers,
    )
    assert resp.status_code == 200
    assert "extra" not in resp.json()["doc_tags"]

    resp = client.get("/api/v1/documents/review/queue?status=VERIFIED",
                      headers=headers)
    assert resp.status_code == 200
    assert any(d["id"] == review_doc for d in resp.json())

    resp = client.get("/api/v1/documents/review/counts", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["VERIFIED"] >= 1


def test_api_invalid_decision_rejected(client, review_doc):
    token = _review_token(client)
    resp = client.post(
        f"/api/v1/documents/review/{review_doc}",
        json={"decision": "NOPE"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_rag_gate_excludes_flagged_docs(client, review_doc, review_user, monkeypatch):
    from app.db.session import get_session_factory
    from app.services import rag
    from app.services import review as review_svc

    # Model-free: stub the dense embedder so retrieval runs on the BM25 path
    # only (no sentence-transformers load); the FLAGGED gate is DB-side logic.
    monkeypatch.setattr(rag, "embed_single", lambda *a, **k: None)

    session = get_session_factory()()

    # Verify first: doc is retrievable and carries its review status.
    review_svc.review_document(
        session, review_doc, "VERIFIED", reviewer_id=review_user,
    )
    session.commit()
    contexts = rag.retrieve(session, f"zztok{review_doc}")
    mine = [c for c in contexts if c["document_id"] == review_doc]
    assert mine and mine[0]["review_status"] == "VERIFIED"

    # Flag: the same query must drop every chunk of this document.
    review_svc.review_document(
        session, review_doc, "FLAGGED", reviewer_id=review_user,
    )
    session.commit()
    contexts = rag.retrieve(session, f"zztok{review_doc}")
    assert all(c["document_id"] != review_doc for c in contexts)
    session.close()
