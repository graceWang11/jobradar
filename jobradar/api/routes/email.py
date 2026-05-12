"""Email activity endpoints — status hydration, SSE stream, follow-up CRUD,
thread mark-read, and reply intent recording.

Frontend contract source of truth: src/lib/email.ts (event names + payload
shapes). When you change a payload here, update the reducer there in lockstep.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from jobradar.api import events
from jobradar.api.auth import require_auth
from jobradar.api.db import (
    InboundThread,
    OutboundEmail,
    ScheduledFollowUp,
    get_session,
)
from jobradar.api.schemas import (
    Contact,
    CreateFollowUpBody,
    EmailStatus,
    FollowUpsStats,
    InboundStats,
    InboundThreadOut,
    OutboundStats,
    PatchThreadBody,
    ReplyBody,
    ScheduledFollowUpOut,
)

router = APIRouter(prefix="/api/email", tags=["email"], dependencies=[Depends(require_auth)])


def _start_of_today_utc() -> datetime:
    now = datetime.utcnow()
    return datetime(now.year, now.month, now.day)


# ── GET /api/email/status ────────────────────────────────────────────────────


@router.get("/status", response_model=EmailStatus)
def get_status(session: Session = Depends(get_session)) -> EmailStatus:
    today = _start_of_today_utc()

    sent_today = session.scalar(
        select(func.count(OutboundEmail.id)).where(OutboundEmail.sent_at >= today)
    ) or 0
    sent_all = session.scalar(select(func.count(OutboundEmail.id))) or 0
    in_flight = session.scalar(
        select(func.count(OutboundEmail.id)).where(OutboundEmail.sent_at.is_(None))
    ) or 0
    last_sent = session.scalar(
        select(func.max(OutboundEmail.sent_at))
    )

    unread = session.scalar(
        select(func.count(InboundThread.id)).where(InboundThread.read.is_(False))
    ) or 0
    replied_today = session.scalar(
        select(func.count(InboundThread.id)).where(InboundThread.replied_at >= today)
    ) or 0

    latest_rows: List[InboundThread] = list(
        session.scalars(
            select(InboundThread)
            .order_by(InboundThread.received_at.desc())
            .limit(5)
        )
    )
    latest_threads = [
        InboundThreadOut(
            threadId=row.id,
            jobId=row.job_id,
            **{"from": Contact(name=row.from_name, email=row.from_email)},
            subject=row.subject,
            snippet=row.snippet,
            receivedAt=row.received_at,
            read=row.read,
        )
        for row in latest_rows
    ]

    queued = session.scalar(
        select(func.count(ScheduledFollowUp.id)).where(ScheduledFollowUp.status == "scheduled")
    ) or 0
    upcoming_rows: List[ScheduledFollowUp] = list(
        session.scalars(
            select(ScheduledFollowUp)
            .where(ScheduledFollowUp.status == "scheduled")
            .order_by(ScheduledFollowUp.scheduled_for.asc())
            .limit(5)
        )
    )
    upcoming = [
        ScheduledFollowUpOut(
            id=row.id,
            jobId=row.job_id,
            to=Contact(name=row.to_name, email=row.to_email),
            scheduledFor=row.scheduled_for,
            template=row.template,
        )
        for row in upcoming_rows
    ]

    return EmailStatus(
        outbound=OutboundStats(
            sentToday=sent_today,
            sentAllTime=sent_all,
            inFlight=in_flight,
            lastSentAt=last_sent,
        ),
        inbound=InboundStats(
            unread=unread,
            repliedToday=replied_today,
            latestThreads=latest_threads,
        ),
        followUps=FollowUpsStats(queued=queued, items=upcoming),
    )


# ── GET /api/email/stream  (SSE) ─────────────────────────────────────────────


@router.get("/stream")
async def stream():
    """Server-Sent Events. Frontend EventSource consumes named events:
    email.sent, email.reply, followup.scheduled, followup.fired,
    followup.cancelled, thread.read.
    """

    async def gen():
        async for chunk in events.bus.stream():
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Follow-ups ───────────────────────────────────────────────────────────────


@router.post("/followups", response_model=ScheduledFollowUpOut, status_code=status.HTTP_201_CREATED)
def create_followup(body: CreateFollowUpBody, session: Session = Depends(get_session)):
    fid = str(uuid.uuid4())
    row = ScheduledFollowUp(
        id=fid,
        job_id=body.jobId,
        to_name=body.to.name,
        to_email=body.to.email,
        scheduled_for=body.scheduledFor.replace(tzinfo=None)
        if body.scheduledFor.tzinfo
        else body.scheduledFor,
        template=body.template,
        status="scheduled",
    )
    session.add(row)
    session.commit()

    out = ScheduledFollowUpOut(
        id=row.id,
        jobId=row.job_id,
        to=Contact(name=row.to_name, email=row.to_email),
        scheduledFor=row.scheduled_for,
        template=row.template,
    )
    events.bus.emit(
        events.EVENT_FOLLOWUP_SCHEDULED,
        {
            "id": out.id,
            "jobId": out.jobId,
            "to": out.to.model_dump(),
            "scheduledFor": out.scheduledFor,
            "template": out.template,
        },
    )
    return out


@router.delete("/followups/{followup_id}")
def cancel_followup(followup_id: str, session: Session = Depends(get_session)):
    row = session.get(ScheduledFollowUp, followup_id)
    if row is None:
        raise HTTPException(status_code=404, detail="follow-up not found")
    row.status = "cancelled"
    row.cancelled_reason = "user"
    session.commit()
    events.bus.emit(
        events.EVENT_FOLLOWUP_CANCELLED,
        {"id": followup_id, "reason": "user"},
    )
    return {"id": followup_id}


# ── Threads ──────────────────────────────────────────────────────────────────


@router.patch("/threads/{thread_id}")
def patch_thread(
    thread_id: str,
    body: PatchThreadBody,
    session: Session = Depends(get_session),
):
    row = session.get(InboundThread, thread_id)
    if row is None:
        raise HTTPException(status_code=404, detail="thread not found")
    if body.read is not None:
        row.read = body.read
    session.commit()
    events.bus.emit(events.EVENT_THREAD_READ, {"threadId": thread_id, "read": row.read})
    return {"id": thread_id, "read": row.read}


@router.post("/threads/{thread_id}/reply")
def reply_thread(
    thread_id: str,
    body: ReplyBody,
    session: Session = Depends(get_session),
):
    """Records the reply intent and marks the thread replied. Does not actually
    SMTP-send the reply yet — wire that to email_sender when the frontend
    composer is ready.
    """
    row = session.get(InboundThread, thread_id)
    if row is None:
        raise HTTPException(status_code=404, detail="thread not found")
    row.replied_at = datetime.utcnow()
    row.read = True
    session.commit()

    msg_id = str(uuid.uuid4())
    session.add(
        OutboundEmail(
            id=msg_id,
            job_id=row.job_id,
            to_email=row.from_email,
            subject=f"Re: {row.subject}",
            sent_at=datetime.utcnow(),
        )
    )
    session.commit()
    events.bus.emit(
        events.EVENT_EMAIL_SENT,
        {
            "messageId": msg_id,
            "jobId": row.job_id,
            "to": row.from_email,
            "sentAt": datetime.utcnow(),
        },
    )
    return {"threadId": thread_id, "messageId": msg_id}
