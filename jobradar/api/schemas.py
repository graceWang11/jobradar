"""Pydantic schemas matching the frontend EmailStatus contract.

Field names mirror what the frontend (src/lib/email.ts) expects; do not rename
without coordinating with the frontend reducer in useEmailFeed.ts.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Contact(BaseModel):
    name: str = ""
    email: str


class OutboundStats(BaseModel):
    sentToday: int
    sentAllTime: int
    inFlight: int
    lastSentAt: Optional[datetime] = None


class InboundThreadOut(BaseModel):
    threadId: str
    jobId: Optional[str] = None
    from_: Contact = Field(..., alias="from")
    subject: str
    snippet: str
    receivedAt: datetime
    read: bool

    model_config = ConfigDict(populate_by_name=True)


class InboundStats(BaseModel):
    unread: int
    repliedToday: int
    latestThreads: List[InboundThreadOut]


class ScheduledFollowUpOut(BaseModel):
    id: str
    jobId: Optional[str] = None
    to: Contact
    scheduledFor: datetime
    template: str


class FollowUpsStats(BaseModel):
    queued: int
    items: List[ScheduledFollowUpOut]


class EmailStatus(BaseModel):
    outbound: OutboundStats
    inbound: InboundStats
    followUps: FollowUpsStats


# ── Request bodies ───────────────────────────────────────────────────────────


class CreateFollowUpBody(BaseModel):
    jobId: Optional[str] = None
    to: Contact
    scheduledFor: datetime
    template: str = ""


class PatchThreadBody(BaseModel):
    read: Optional[bool] = None


class ReplyBody(BaseModel):
    body: str


class LoginBody(BaseModel):
    password: str
