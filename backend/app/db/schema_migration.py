"""Lightweight runtime schema migration for document review + tagging.

The project has no Alembic; tests and dev databases are created with
Base.metadata.create_all(). Existing installs (e.g. the live AppData SQLite
file) predate the review/tagging columns, so ensure_document_review_columns()
adds them idempotently on first boot. Pure SQL: never imports db.models at
module level (models.py calls this at import time).
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text as sql_text

logger = logging.getLogger("minetrace.schema_migration")

_done: set[str] = set()


def ensure_document_review_columns(engine) -> None:
    """Add doc_tags / review_status / review_note / reviewed_by / reviewed_at
    to document, field_tags to document_chunk, and ix_document_tag — idempotent.
    """
    try:
        url_key = str(engine.url)
        if url_key in _done:
            return
        with engine.connect() as conn:
            is_pg = engine.url.get_backend_name() == "postgresql"
            if is_pg:
                # End the implicit transaction so ALTERs can run (matches
                # pgvector_store's CREATE EXTENSION pattern).
                conn.execute(sql_text("COMMIT"))
                existing_tables = {
                    r[0] for r in conn.execute(
                        sql_text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = 'public'"
                        )
                    )
                }
                doc_cols = {
                    r[0] for r in conn.execute(
                        sql_text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'document'"
                        )
                    )
                }
                chunk_cols = {
                    r[0] for r in conn.execute(
                        sql_text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'document_chunk'"
                        )
                    )
                }
            else:
                # SQLite: information_schema does not exist; use pragma/catalog.
                existing_tables = {
                    r[0] for r in conn.execute(
                        sql_text("SELECT name FROM sqlite_master WHERE type='table'")
                    )
                }
                doc_cols = {
                    r[1] for r in conn.execute(
                        sql_text("PRAGMA table_info(document)")
                    )
                }
                chunk_cols = {
                    r[1] for r in conn.execute(
                        sql_text("PRAGMA table_info(document_chunk)")
                    )
                }
            if "document" not in existing_tables:
                # Fresh database: create_all() will build the full schema
                # including these columns; nothing to migrate.
                return
            for col, ddl in [
                ("doc_tags", "ALTER TABLE document ADD COLUMN doc_tags TEXT DEFAULT '[]'"),
                ("review_status",
                 "ALTER TABLE document ADD COLUMN review_status VARCHAR(20) "
                 "DEFAULT 'PENDING'"),
                ("review_note", "ALTER TABLE document ADD COLUMN review_note TEXT"),
                ("reviewed_by", "ALTER TABLE document ADD COLUMN reviewed_by INTEGER"),
                ("reviewed_at", "ALTER TABLE document ADD COLUMN reviewed_at TIMESTAMP"),
            ]:
                if col not in doc_cols:
                    conn.execute(sql_text(ddl))
            if "field_tags" not in chunk_cols:
                conn.execute(
                    sql_text(
                        "ALTER TABLE document_chunk ADD COLUMN field_tags "
                        "TEXT DEFAULT '[]'"
                    )
                )
            conn.execute(
                sql_text(
                    "CREATE INDEX IF NOT EXISTS ix_document_tag ON document "
                    "(doc_tags)"
                )
            )
            if is_pg:
                conn.execute(sql_text("COMMIT"))
            else:
                conn.commit()
        _done.add(url_key)
        logger.info("document review/tagging schema ensured")
    except Exception:
        logger.exception("ensure_document_review_columns failed")


def parse_tags(raw: str | None) -> list[str]:
    """Decode a stored JSON tag list; tolerant of legacy/garbage values."""
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return [str(t) for t in val] if isinstance(val, list) else []
    except Exception:
        return []


def dump_tags(tags: list[str]) -> str:
    """Encode a tag list for storage (lowercase, trimmed, de-duplicated)."""
    seen: list[str] = []
    for t in tags:
        norm = str(t).strip().lower()
        if norm and norm not in seen:
            seen.append(norm)
    return json.dumps(seen)
