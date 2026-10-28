"""Database engine and session management."""

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings

from . import models  # noqa: F401  (registers the tables on the metadata)


def make_engine(db_path: Path) -> Engine:
    """Create a SQLite engine for the given database file.

    Foreign keys must be enabled per connection on SQLite.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def get_engine() -> Engine:
    """Application engine backed by the file in the user data directory."""
    return make_engine(get_settings().db_path)


def get_session(engine: Engine | None = None) -> Session:
    """Session factory; pass a custom engine in tests."""
    return Session(engine or get_engine(), expire_on_commit=False)


__all__ = ["SQLModel", "get_engine", "get_session", "make_engine", "models"]
