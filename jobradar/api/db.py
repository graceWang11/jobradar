"""SQLite persistence for the email-activity API."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, create_engine
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
    # RFC 5322 Message-ID header on the outgoing MIME message. Separate from
    # `id` (which is a UUID used as the SSE messageId) — this is the value
    # the IMAP poller matches against an inbound reply's In-Reply-To header.
    rfc_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)


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


class EmailAccount(Base):
    """Singleton row holding the user's IMAP + SMTP credentials.

    Posted by the frontend once. Password is stored in plaintext for v1
    (localhost single-user). TODO(v1.1): Fernet-encrypt password at rest with
    a key derived from API_SESSION_SECRET.
    """

    __tablename__ = "email_account"

    # Singleton — always 1 for v1.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    email: Mapped[str] = mapped_column(String, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)
    imap_server: Mapped[str] = mapped_column(String, nullable=False)
    imap_port: Mapped[int] = mapped_column(Integer, nullable=False, default=993)
    imap_folder: Mapped[str] = mapped_column(String, nullable=False, default="INBOX")
    smtp_server: Mapped[str] = mapped_column(String, nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class JobMatchCache(Base):
    __tablename__ = "job_match_cache"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    jobs_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_mtime: Mapped[float] = mapped_column(Float, nullable=False)
    cached_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrackedJob(Base):
    """User-saved/applied jobs. job_json is a snapshot of the Job object at the
    time of tracking so the listing stays accessible even after the source CSV
    rotates or preferences change to filter it out."""

    __tablename__ = "tracked_jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)  # saved|applied|screening|interview|offer
    job_json: Mapped[str] = mapped_column(Text, nullable=False)
    tracked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
