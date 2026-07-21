"""Engine/session lifecycle. This is the only module that touches the global
SQLAlchemy engine — everything else gets a `Session` handed to it (see
`session_scope` / `app.database.repository.get_repository`), which is what
keeps the repository layer unit-testable against an in-memory SQLite engine.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.database.models import Base
from app.utilities.logger import get_logger

logger = get_logger(__name__)


def _ensure_sqlite_dir(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    db_path = database_url.removeprefix("sqlite:///")
    if db_path == ":memory:":
        return
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def _make_engine():
    settings = get_settings()
    _ensure_sqlite_dir(settings.database_url)
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, connect_args=connect_args, future=True)


engine = _make_engine()
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create tables if they don't exist yet. Safe to call on every startup."""
    Base.metadata.create_all(engine)
    logger.info("Database schema ensured at %s", engine.url)


@contextmanager
def session_scope() -> Iterator[Session]:
    """One unit of work: commit on success, roll back on any exception."""
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
