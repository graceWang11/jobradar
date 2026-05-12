"""Helpers that persist a domain event AND push it onto the event bus.

These are the seams pipeline code (or future inbound listeners) should call.
Every function is fail-soft: if the DB or bus errors, we log to stdout and move
on so the CLI never breaks because of API plumbing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from jobradar.api import events
from jobradar.api.db import (
    InboundThread,
    OutboundEmail,
    ScheduledFollowUp,
    SessionLocal,
    init_db,
)

_initialized = False


def _ensure_init() -> None:
    global _initialized
    if _initialized:
        return
    try:
        init_db()
        _initialized = True
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[api.recorder] DB init failed: {exc}")


def record_outbound(
    *,
    to_email: str,
    subject: str = "",
    job_id: Optional[str] = None,
    sent_at: Optional[datetime] = None,
    message_id: Optional[str] = None,
    rfc_message_id: Optional[str] = None,
) -> Optional[str]:
    """Insert an outbound row and emit email.sent. Returns the row id (UUID).

    `rfc_message_id` is the value of the outgoing MIME Message-ID header.
    The IMAP poller matches inbound replies' In-Reply-To against this column.
    """
    _ensure_init()
    msg_id = message_id or str(uuid.uuid4())
    now = sent_at or datetime.utcnow()
    try:
        with SessionLocal() as session:
            session.add(
                OutboundEmail(
                    id=msg_id,
                    job_id=job_id,
                    to_email=to_email,
                    subject=subject,
                    sent_at=now,
                    rfc_message_id=rfc_message_id,
                )
            )
            session.commit()
    except Exception as exc:
        print(f"[api.recorder] outbound persist failed: {exc}")
        return None

    events.bus.emit(
        events.EVENT_EMAIL_SENT,
        {"messageId": msg_id, "jobId": job_id, "to": to_email, "sentAt": now},
    )
    return msg_id


def record_inbound_reply(
    *,
    from_email: str,
    from_name: str = "",
    subject: str = "",
    snippet: str = "",
    job_id: Optional[str] = None,
    received_at: Optional[datetime] = None,
    thread_id: Optional[str] = None,
) -> Optional[str]:
    """Idempotent on thread_id — duplicate calls silently return None.

    The IMAP poller re-scans an overlapping window every tick, so the same
    Message-ID can be observed multiple times. Pass the RFC Message-ID as
    thread_id to get free dedup.
    """
    _ensure_init()
    tid = thread_id or str(uuid.uuid4())
    now = received_at or datetime.utcnow()
    try:
        with SessionLocal() as session:
            if session.get(InboundThread, tid) is not None:
                return None
            session.add(
                InboundThread(
                    id=tid,
                    job_id=job_id,
                    from_email=from_email,
                    from_name=from_name,
                    subject=subject,
                    snippet=snippet,
                    received_at=now,
                    read=False,
                )
            )
            session.commit()
    except Exception as exc:
        print(f"[api.recorder] inbound persist failed: {exc}")
        return None

    events.bus.emit(
        events.EVENT_EMAIL_REPLY,
        {
            "threadId": tid,
            "jobId": job_id,
            "from": {"name": from_name, "email": from_email},
            "subject": subject,
            "snippet": snippet,
            "receivedAt": now,
        },
    )
    return tid


def record_followup_fired(*, followup_id: str, message_id: str) -> None:
    _ensure_init()
    try:
        with SessionLocal() as session:
            row = session.get(ScheduledFollowUp, followup_id)
            if row is None:
                return
            row.status = "fired"
            row.fired_message_id = message_id
            session.commit()
    except Exception as exc:
        print(f"[api.recorder] followup fire persist failed: {exc}")
        return
    events.bus.emit(
        events.EVENT_FOLLOWUP_FIRED,
        {"id": followup_id, "messageId": message_id},
    )
