from __future__ import annotations

from pydantic import BaseModel


class Citation(BaseModel):
    ref: str
    chunk_id: int
    document_id: int
    filename: str
    page_number: int | None
    excerpt: str
    review_status: str | None = None


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    query: str
    answer: str
    citations: list[Citation]
    model: str | None
    context_count: int
    source: str = "LLM"
    grounded_pct: int = 0


class ReviewDecision(BaseModel):
    decision: str  # VERIFIED | FLAGGED
    note: str | None = None
    field_tags: list[str] | None = None


class DocTagsUpdate(BaseModel):
    tags: list[str] = []


class DocTagAdd(BaseModel):
    tag: str


class ChunkFieldTagsUpdate(BaseModel):
    tags: list[str] = []
