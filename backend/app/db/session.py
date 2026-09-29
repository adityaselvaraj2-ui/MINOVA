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
    url = db_url or settings.db_url
    engine = create_engine(url, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


_engine = None
_session_factory = None


def init_db(db_url: str | None = None) -> None:
    global _engine, _session_factory
    _engine = get_engine(db_url)
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
