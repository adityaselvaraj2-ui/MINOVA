from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _set_sqlite_pragmas(dbapi_conn: object, _connection_record: object) -> None:
    cursor = dbapi_conn.cursor()  # type: ignore[union-attr]
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_engine(db_url: str | None = None):
    from app.db.schema_migration import ensure_document_review_columns

    url = db_url or settings.db_url
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})
        event.listen(engine, "connect", _set_sqlite_pragmas)
    else:
        # PostgreSQL/PostGIS (psycopg3): no SQLite pragmas, verify liveness
        engine = create_engine(url, pool_pre_ping=True)
    ensure_document_review_columns(engine)
    return engine


_engine = None
_engine_url: str | None = None
_session_factory = None


def init_db(db_url: str | None = None) -> None:
    global _engine, _engine_url, _session_factory
    url = db_url or settings.db_url
    if _engine is not None and _engine_url != url:
        # Data dir changed (test isolation): drop the cached engine so the
        # new SQLite file is used instead of the previously-bound one.
        _engine = None
        _session_factory = None
    _engine = get_engine(url)
    _engine_url = url
    _session_factory = sessionmaker(bind=_engine, class_=Session, expire_on_commit=False)


def get_session_factory() -> sessionmaker:
    if _session_factory is None:
        init_db()
    return _session_factory  # type: ignore[return-value]


def get_db():
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()
