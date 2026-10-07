"""SQLAlchemy engine + session. SQLite for dev; point DATABASE_URL at Postgres for prod."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


def _normalize(url: str) -> str:
    """Force the psycopg (v3) driver.

    Managed hosts (Railway, Heroku, Neon) hand out plain `postgresql://` or
    `postgres://` URLs, which SQLAlchemy would route to psycopg2 — a driver we
    don't install. Rewrite the scheme so the same URL works unchanged in prod.
    """
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _normalize(settings.database_url)
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_session():
    """FastAPI dependency yielding a session that always closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
