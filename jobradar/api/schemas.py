"""Pydantic schemas matching the frontend EmailStatus contract.

Field names mirror what the frontend (src/lib/email.ts) expects; do not rename
without coordinating with the frontend reducer in useEmailFeed.ts.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Contact(BaseModel):
    name: str = ""
    email: str


class OutboundStats(BaseModel):
    sentTotal: int
    sentToday: int
    lastSentAt: Optional[datetime] = None
    inFlight: int


class InboundThreadOut(BaseModel):
    threadId: str
    jobId: Optional[str] = None
    from_: Contact = Field(..., alias="from")
    subject: str
    snippet: str
    receivedAt: datetime
    unread: bool

    model_config = ConfigDict(populate_by_name=True)


class InboundStats(BaseModel):
    threadsTotal: int
    unread: int
    repliesToday: int
    latestThreads: List[InboundThreadOut]


class ScheduledFollowUpOut(BaseModel):
    id: str
    jobId: Optional[str] = None
    to: Contact
    scheduledFor: datetime
    template: str


class FollowUpsStats(BaseModel):
    scheduledTotal: int
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


class ReplyBody(BaseModel):
    body: str


class LoginBody(BaseModel):
    password: str


# ── Email account (frontend-supplied IMAP+SMTP creds) ───────────────────────


class EmailAccountIn(BaseModel):
    """POST body. Only email + password are required; servers/ports are
    inferred from the email domain when omitted."""

    email: str
    password: str
    imapServer: Optional[str] = None
    imapPort: Optional[int] = None
    imapFolder: Optional[str] = None
    smtpServer: Optional[str] = None
    smtpPort: Optional[int] = None


class EmailAccountOut(BaseModel):
    """GET response. Never echoes the password."""

    configured: bool
    email: Optional[str] = None
    imapServer: Optional[str] = None
    imapPort: Optional[int] = None
    imapFolder: Optional[str] = None
    smtpServer: Optional[str] = None
    smtpPort: Optional[int] = None
    lastPolledAt: Optional[datetime] = None


# ── Jobs feed (src/lib/types.ts contract) ───────────────────────────────────

JobType = Literal["remote", "hybrid", "onsite"]
ExperienceLevel = Literal["intern", "entry", "mid", "senior", "lead"]
WorkAuthorization = Literal["citizen", "permanent", "visa-required", "student"]
JobSource = Literal["LinkedIn", "Indeed", "Wellfound", "Greenhouse", "Lever", "Direct"]
ApplicationStatus = Literal[
    "saved", "applied", "screening", "interview", "offer", "rejected"
]


class UserPreferences(BaseModel):
    jobTypes: List[JobType]
    locations: List[str]
    visaSponsorship: bool
    workAuthorization: WorkAuthorization
    experienceLevel: ExperienceLevel
    desiredRoles: List[str]
    keywords: List[str]
    minSalary: int
    maxSalary: int
    willingToRelocate: bool
    remoteOnly: bool


class Job(BaseModel):
    id: str
    title: str
    company: str
    companyEmoji: str = ""
    location: str
    type: JobType
    salaryMin: int = 0
    salaryMax: int = 0
    postedAt: datetime
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    visaSponsorship: bool
    experience: ExperienceLevel
    matchScore: int = Field(ge=0, le=100)
    source: JobSource
    status: Optional[ApplicationStatus] = None


class JobMatchBody(BaseModel):
    preferences: UserPreferences
    resumeSkills: List[str] = Field(default_factory=list)
    limit: Optional[int] = None


class JobMatchResponse(BaseModel):
    cachedAt: datetime
    fresh: bool
    jobs: List[Job]
