"""SQLite persistence for the email-activity API."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_DB_PATH = DATA_DIR / "api.sqlite"


def _database_url() -> str:
    override = os.environ.get("JOBRADAR_DB_URL")
    if override:
        return override
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_DB_PATH}"


engine = create_engine(
    _database_url(),
    future=True,
    connect_args={"check_same_thread": False} if _database_url().startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


class OutboundEmail(Base):
    __tablename__ = "outbound_emails"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    to_email: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, default="")
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InboundThread(Base):
    __tablename__ = "inbound_threads"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    from_name: Mapped[str] = mapped_column(String, default="")
    from_email: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, default="")
    snippet: Mapped[str] = mapped_column(String, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ScheduledFollowUp(Base):
    __tablename__ = "scheduled_followups"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    to_name: Mapped[str] = mapped_column(String, default="")
    to_email: Mapped[str] = mapped_column(String, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    template: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="scheduled")  # scheduled|fired|cancelled
    fired_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cancelled_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class JobMatchCache(Base):
    __tablename__ = "job_match_cache"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    jobs_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_mtime: Mapped[float] = mapped_column(Float, nullable=False)
    cached_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    """Create tables if they do not exist. Idempotent."""
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """FastAPI dependency: yields a session that closes after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
