from __future__ import annotations

from app.services.chunking import chunk_pages, chunk_text
from app.services.rag import _bm25_scores, _reciprocal_rank_fusion


def test_chunk_text_basic():
    text = " ".join(f"word{i}" for i in range(100))
    chunks = chunk_text(text, chunk_size=30, overlap=5)
    assert len(chunks) >= 3
    assert all(c["token_count"] <= 30 for c in chunks)
    assert chunks[0]["char_start"] == 0


def test_chunk_pages():
    pages = [
        {"page": 1, "text": " ".join(f"alpha{i}" for i in range(50))},
        {"page": 2, "text": " ".join(f"beta{i}" for i in range(50))},
    ]
    chunks = chunk_pages(pages)
    assert len(chunks) >= 2
    assert chunks[0]["page_number"] == 1


def test_chunk_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_bm25_basic(client):
    from app.db.models import Document, DocumentChunk, Role, User
    from app.db.session import get_session_factory
    from app.security import hash_password

    session = get_session_factory()()
    if not session.query(User).filter(User.username == "rag_user").first():
        if not session.query(Role).filter(Role.code == "FOREMAN").first():
            session.add(Role(code="FOREMAN", rank=1, label="Foreman", can_enter=True, can_approve=False))
            session.flush()
        session.add(User(
            username="rag_user", full_name="RAG User",
            password_hash=hash_password("pass"), role_code="FOREMAN",
        ))
        session.flush()

    user = session.query(User).filter(User.username == "rag_user").first()

    if not session.query(Document).filter(Document.filename == "test_bm25.pdf").first():
        doc = Document(
            filename="test_bm25.pdf", file_path="/tmp/test.pdf",
            file_type="PDF", file_size=100, uploaded_by=user.id, status="READY",
        )
        session.add(doc)
        session.flush()

        texts = [
            "Coal production in opencast mines has increased this quarter",
            "Overburden removal exceeded targets in the northern sector",
            "Safety incidents were reported due to heavy rainfall",
        ]
        for i, t in enumerate(texts):
            session.add(DocumentChunk(
                document_id=doc.id, chunk_index=i, text=t,
                page_number=1, char_start=0, char_end=len(t),
                token_count=len(t.split()),
            ))
        session.commit()

    results = _bm25_scores(session, "coal production opencast")
    session.close()

    assert len(results) > 0
    top_id, top_score = results[0]
    assert top_score > 0


def test_rrf():
    dense_ids = [10, 20, 30, 40]
    bm25 = [(20, 5.0), (50, 3.0), (10, 2.0)]
    fused = _reciprocal_rank_fusion(dense_ids, bm25)
    assert 10 in fused
    assert 20 in fused
    assert fused.index(20) < fused.index(40)
