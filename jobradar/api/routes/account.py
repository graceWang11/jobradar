"""EmailAccount CRUD — frontend posts IMAP+SMTP creds here.

Singleton for v1: only one account row at any time (id=1). POST upserts.
Password is never echoed back. Domain-based defaults fill in
imap_server/smtp_server when the frontend omits them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from jobradar.api.auth import require_auth
from jobradar.api.db import EmailAccount, get_session
from jobradar.api.imap_poller import _AccountSnapshot, poller_manager
from jobradar.api.schemas import EmailAccountIn, EmailAccountOut

router = APIRouter(prefix="/api/email/account", tags=["account"], dependencies=[Depends(require_auth)])


# domain → (imap_host, imap_port, smtp_host, smtp_port)
_DOMAIN_DEFAULTS = {
    "gmail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 587),
    "googlemail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 587),
    "outlook.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "hotmail.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "live.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "yahoo.com": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587),
    "icloud.com": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587),
    "me.com": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587),
}


def _infer_defaults(email: str) -> Tuple[str, int, str, int]:
    domain = email.split("@", 1)[-1].strip().lower()
    if domain in _DOMAIN_DEFAULTS:
        return _DOMAIN_DEFAULTS[domain]
    # Best-effort guess for unknown domains.
    return (f"imap.{domain}", 993, f"smtp.{domain}", 587)


def _row_to_out(row: EmailAccount) -> EmailAccountOut:
    return EmailAccountOut(
        configured=True,
        email=row.email,
        imapServer=row.imap_server,
        imapPort=row.imap_port,
        imapFolder=row.imap_folder,
        smtpServer=row.smtp_server,
        smtpPort=row.smtp_port,
        lastPolledAt=row.last_polled_at,
    )


@router.get("", response_model=EmailAccountOut, response_model_exclude_none=True)
def get_account(session: Session = Depends(get_session)) -> EmailAccountOut:
    row = session.get(EmailAccount, 1)
    if row is None:
        return EmailAccountOut(configured=False)
    return _row_to_out(row)


@router.post("", response_model=EmailAccountOut, response_model_exclude_none=True)
def upsert_account(body: EmailAccountIn, session: Session = Depends(get_session)) -> EmailAccountOut:
    if "@" not in body.email or not body.password:
        raise HTTPException(status_code=400, detail="email and password are required")

    default_imap_host, default_imap_port, default_smtp_host, default_smtp_port = _infer_defaults(body.email)

    row = session.get(EmailAccount, 1)
    if row is None:
        row = EmailAccount(
            id=1,
            email=body.email,
            password=body.password,
            imap_server=body.imapServer or default_imap_host,
            imap_port=body.imapPort or default_imap_port,
            imap_folder=body.imapFolder or "INBOX",
            smtp_server=body.smtpServer or default_smtp_host,
            smtp_port=body.smtpPort or default_smtp_port,
            created_at=datetime.utcnow(),
        )
        session.add(row)
    else:
        row.email = body.email
        row.password = body.password
        row.imap_server = body.imapServer or default_imap_host
        row.imap_port = body.imapPort or default_imap_port
        row.imap_folder = body.imapFolder or "INBOX"
        row.smtp_server = body.smtpServer or default_smtp_host
        row.smtp_port = body.smtpPort or default_smtp_port
        # Clear last_polled_at so the new account's first tick re-scans the
        # full reply window.
        row.last_polled_at = None
    session.commit()
    session.refresh(row)

    poller_manager.start(_AccountSnapshot.from_row(row))

    return _row_to_out(row)


@router.delete("")
def delete_account(session: Session = Depends(get_session)) -> dict:
    poller_manager.stop_sync()
    row = session.get(EmailAccount, 1)
    if row is not None:
        session.delete(row)
        session.commit()
    return {"configured": False}
