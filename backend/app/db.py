from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False, "timeout": 30},
    future=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    """WAL so background email sync doesn't freeze the API/UI."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import models so they are registered on the metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_columns()


def _migrate_sqlite_columns() -> None:
    """Add columns introduced after initial create_all (SQLite has no ALTER via ORM)."""
    if not settings.db_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(applications)").fetchall()
        cols = {r[1] for r in rows}
        if "job_id" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE applications ADD COLUMN job_id VARCHAR(128)"
            )
