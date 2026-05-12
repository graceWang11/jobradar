"""IMAP listener that surfaces replies to mail we've sent.

Reply-thread-only model (approach A): on each tick we list recent inbound
messages and keep only ones whose In-Reply-To / References header points at
an rfc_message_id we stored in outbound_emails. Everything else is ignored
so the dashboard inbox stays signal-only.

Lifecycle is owned by `PollerManager`:
  - On app boot (lifespan): if an EmailAccount row exists, manager.start_from_db()
  - On POST /api/email/account: manager.restart(account)
  - On DELETE /api/email/account: manager.stop()
  - On app shutdown: manager.stop()

imaplib is sync, so each tick runs in a thread via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import email as emaillib
import imaplib
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parseaddr, parsedate_to_datetime
from typing import List, Optional, Set, Tuple

from jobradar.api.db import EmailAccount, OutboundEmail, SessionLocal
from jobradar.api.recorder import record_inbound_reply

log = logging.getLogger(__name__)

POLL_SECONDS = int(os.environ.get("IMAP_POLL_SECONDS", "60"))
_SNIPPET_MAX = 280


@dataclass(frozen=True)
class _AccountSnapshot:
    """Immutable copy of the account row so the polling task doesn't hold a
    DB session across awaits."""

    email: str
    password: str
    imap_server: str
    imap_port: int
    imap_folder: str

    @classmethod
    def from_row(cls, row: EmailAccount) -> "_AccountSnapshot":
        return cls(
            email=row.email,
            password=row.password,
            imap_server=row.imap_server,
            imap_port=row.imap_port,
            imap_folder=row.imap_folder,
        )


def _extract_message_id(header_value: str) -> Optional[str]:
    """Return the first <id> found in a Message-ID / In-Reply-To header."""
    if not header_value:
        return None
    m = re.search(r"<[^>\s]+>", header_value)
    return m.group(0) if m else None


def _extract_referenced_ids(msg: emaillib.message.Message) -> List[str]:
    ids: List[str] = []
    in_reply_to = msg.get("In-Reply-To", "")
    primary = _extract_message_id(in_reply_to)
    if primary:
        ids.append(primary)
    references = msg.get("References", "")
    if references:
        ids.extend(re.findall(r"<[^>\s]+>", references))
    # Preserve order, dedupe
    seen: Set[str] = set()
    deduped: List[str] = []
    for mid in ids:
        if mid not in seen:
            seen.add(mid)
            deduped.append(mid)
    return deduped


def _text_snippet(msg: emaillib.message.Message) -> str:
    """Pull the first text/plain part (or fall back to text/html stripped)."""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True) or b""
                try:
                    return payload.decode(part.get_content_charset() or "utf-8", "replace")
                except Exception:
                    return payload.decode("utf-8", "replace")
    payload = msg.get_payload(decode=True) or b""
    try:
        text = payload.decode(msg.get_content_charset() or "utf-8", "replace")
    except Exception:
        text = payload.decode("utf-8", "replace")
    # Coarse HTML strip if needed — full HTML parsing isn't worth the dep.
    return re.sub(r"<[^>]+>", " ", text)


def _lookup_outbound_by_rfc_id(rfc_ids: List[str]) -> Optional[OutboundEmail]:
    if not rfc_ids:
        return None
    with SessionLocal() as session:
        from sqlalchemy import select

        result = session.execute(
            select(OutboundEmail).where(OutboundEmail.rfc_message_id.in_(rfc_ids))
        ).scalars().first()
        return result


def _poll_sync(account: _AccountSnapshot, since: datetime) -> Tuple[int, datetime]:
    """One synchronous polling tick. Returns (replies_recorded, polled_at)."""
    polled_at = datetime.utcnow()
    recorded = 0

    with imaplib.IMAP4_SSL(account.imap_server, account.imap_port) as M:
        M.login(account.email, account.password)
        M.select(account.imap_folder, readonly=True)

        # Search by date — server-side date math has 1-day granularity, so
        # we may re-see yesterday's mail; the Message-ID dedupe on insert
        # handles that idempotently.
        since_str = since.strftime("%d-%b-%Y")
        typ, data = M.search(None, f'(SINCE "{since_str}")')
        if typ != "OK" or not data or not data[0]:
            return 0, polled_at

        for uid in data[0].split():
            typ, msg_data = M.fetch(uid, "(RFC822)")
            if typ != "OK" or not msg_data or msg_data[0] is None:
                continue
            raw = msg_data[0][1]
            msg = emaillib.message_from_bytes(raw)

            referenced = _extract_referenced_ids(msg)
            outbound = _lookup_outbound_by_rfc_id(referenced)
            if outbound is None:
                continue

            inbound_msg_id = _extract_message_id(msg.get("Message-ID", "")) or f"imap-{uid.decode()}"
            from_name, from_email = parseaddr(msg.get("From", ""))
            subject = msg.get("Subject", "") or ""
            snippet = _text_snippet(msg).strip()
            if len(snippet) > _SNIPPET_MAX:
                snippet = snippet[:_SNIPPET_MAX].rstrip() + "…"

            received_at: Optional[datetime]
            try:
                received_at = parsedate_to_datetime(msg.get("Date", ""))
                if received_at is not None and received_at.tzinfo is not None:
                    received_at = received_at.astimezone(tz=None).replace(tzinfo=None)
            except Exception:
                received_at = None

            tid = record_inbound_reply(
                from_email=from_email,
                from_name=from_name,
                subject=subject,
                snippet=snippet,
                job_id=outbound.job_id,
                received_at=received_at,
                thread_id=inbound_msg_id,
            )
            if tid is not None:
                recorded += 1

    return recorded, polled_at


def _update_last_polled(at: datetime) -> None:
    try:
        with SessionLocal() as session:
            row = session.get(EmailAccount, 1)
            if row is not None:
                row.last_polled_at = at
                session.commit()
    except Exception as exc:
        log.warning("[imap] last_polled_at update failed: %s", exc)


class PollerManager:
    """Singleton that owns the running polling task.

    Sync FastAPI routes run in a worker thread with no running loop, so
    start/stop need to schedule onto the loop captured at lifespan boot —
    same pattern as `EventBus.attach_loop`.
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._snapshot: Optional[_AccountSnapshot] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start_from_db(self) -> None:
        """Look for an EmailAccount row and start the poller if present."""
        with SessionLocal() as session:
            row = session.get(EmailAccount, 1)
            if row is None:
                log.info("[imap] no EmailAccount configured — staying idle")
                return
            self.start(_AccountSnapshot.from_row(row))

    def start(self, snapshot: _AccountSnapshot) -> None:
        self.stop_sync()
        self._snapshot = snapshot
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                log.warning("[imap] no event loop attached; poller will start at next lifespan boot")
                return

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if running is loop:
            # We're on the loop's own thread — schedule directly.
            self._task = loop.create_task(self._run(), name="imap-poller")
        else:
            # Cross-thread (sync route handler in worker pool). Block briefly
            # so callers can observe is_running == True immediately.
            holder: dict = {}

            def _create() -> None:
                holder["task"] = loop.create_task(self._run(), name="imap-poller")

            loop.call_soon_threadsafe(_create)
            import time as _t

            for _ in range(50):
                if "task" in holder:
                    self._task = holder["task"]
                    break
                _t.sleep(0.01)
        log.info("[imap] poller started for %s", snapshot.email)

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        log.info("[imap] poller stopped")

    def stop_sync(self) -> None:
        """Cancel without awaiting — fine when called from a sync route since
        the cancelled task is left for the event loop to reap."""
        task = self._task
        self._task = None
        if task is None:
            return
        loop = self._loop
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if loop is not None and running is not loop:
            loop.call_soon_threadsafe(task.cancel)
        else:
            task.cancel()
        log.info("[imap] poller cancelled")

    async def _run(self) -> None:
        # Re-poll a 24h window on every start so we don't miss replies that
        # arrived while the API was down.
        cursor = datetime.utcnow() - timedelta(days=1)
        while True:
            snapshot = self._snapshot
            if snapshot is None:
                return
            try:
                recorded, polled_at = await asyncio.to_thread(_poll_sync, snapshot, cursor)
                if recorded:
                    log.info("[imap] %d new replies recorded", recorded)
                _update_last_polled(polled_at)
                # Step the cursor back ~5 min to absorb clock skew + server
                # SINCE granularity.
                cursor = polled_at - timedelta(minutes=5)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("[imap] tick failed: %s", exc)
            try:
                await asyncio.sleep(POLL_SECONDS)
            except asyncio.CancelledError:
                raise


poller_manager = PollerManager()
