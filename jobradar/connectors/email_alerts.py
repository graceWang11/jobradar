"""Email alert connector – parses LinkedIn & Seek job alert emails via IMAP.

Setup:
  1. Create job alerts on LinkedIn and Seek (email delivery)
  2. Configure IMAP credentials in .env:
       IMAP_SERVER=imap.gmail.com
       IMAP_EMAIL=you@gmail.com
       IMAP_PASSWORD=your_app_password
       IMAP_FOLDER=INBOX   (optional, default INBOX)

The connector scans unread emails from known alert senders and extracts
job listings from the HTML email body. No site login required.
"""

from __future__ import annotations

import email
import imaplib
import os
import re
from email.header import decode_header
from typing import Any, Dict, List

from bs4 import BeautifulSoup

from jobradar.connectors.base import BaseConnector


# Known sender addresses for alert emails
_ALERT_SENDERS = {
    "jobalerts@linkedin.com",
    "jobs-noreply@linkedin.com",
    "noreply@seek.com.au",
    "jobs@seek.com.au",
}

_LINKEDIN_JOB_URL_RE = re.compile(
    r"https?://www\.linkedin\.com/jobs/view/[^\s\"'>]+"
)
_SEEK_JOB_URL_RE = re.compile(
    r"https?://www\.seek\.com\.au/job/[^\s\"'>]+"
)


class EmailAlertsConnector(BaseConnector):
    name = "EmailAlerts"
    rate_limit_seconds = 0.5

    def __init__(self) -> None:
        self.imap_server = os.environ.get("IMAP_SERVER", "imap.gmail.com")
        self.imap_email = os.environ.get("IMAP_EMAIL", "")
        self.imap_password = os.environ.get("IMAP_PASSWORD", "")
        self.imap_folder = os.environ.get("IMAP_FOLDER", "INBOX")

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        if not self.imap_email or not self.imap_password:
            print("[EmailAlerts] IMAP credentials not set – skipping.")
            return []

        try:
            return self._fetch_from_imap(locations)
        except Exception as exc:
            print(f"[EmailAlerts] IMAP error: {exc}")
            return []

    def _fetch_from_imap(self, locations: List[str]) -> List[Dict[str, Any]]:
        jobs: List[Dict[str, Any]] = []

        with imaplib.IMAP4_SSL(self.imap_server) as mail:
            mail.login(self.imap_email, self.imap_password)
            mail.select(self.imap_folder)

            # Search for unseen emails from known alert senders
            for sender in _ALERT_SENDERS:
                _, data = mail.search(None, f'(UNSEEN FROM "{sender}")')
                if not data or not data[0]:
                    continue

                msg_ids = data[0].split()
                print(f"[EmailAlerts] {len(msg_ids)} unread alert(s) from {sender}")

                for msg_id in msg_ids[-20:]:  # cap at last 20 per sender
                    try:
                        _, msg_data = mail.fetch(msg_id, "(RFC822)")
                        raw_email = msg_data[0][1]
                        parsed = email.message_from_bytes(raw_email)
                        extracted = self._extract_jobs(parsed, locations)
                        jobs.extend(extracted)
                        self._sleep()
                    except Exception as exc:
                        print(f"[EmailAlerts] Error parsing email {msg_id}: {exc}")

        return jobs

    def _extract_jobs(
        self, msg: email.message.Message, locations: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract job links and details from an alert email."""
        html_body = ""
        text_body = ""

        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/html":
                    html_body = self._decode_part(part)
                elif ct == "text/plain" and not html_body:
                    text_body = self._decode_part(part)
        else:
            ct = msg.get_content_type()
            if ct == "text/html":
                html_body = self._decode_part(msg)
            else:
                text_body = self._decode_part(msg)

        body = html_body or text_body
        if not body:
            return []

        # Determine source from sender
        from_addr = str(msg.get("From", "")).lower()
        source_hint = "LinkedIn" if "linkedin" in from_addr else "Seek"

        return self._parse_html_alert(body, source_hint, locations)

    def _parse_html_alert(
        self, html: str, source_hint: str, locations: List[str]
    ) -> List[Dict[str, Any]]:
        """Parse the HTML body of an alert email to extract job listings."""
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        if source_hint == "LinkedIn":
            jobs = self._parse_linkedin_alert(soup, locations)
        else:
            jobs = self._parse_seek_alert(soup, locations)

        return jobs

    def _parse_linkedin_alert(
        self, soup: BeautifulSoup, locations: List[str]
    ) -> List[Dict[str, Any]]:
        jobs = []
        # LinkedIn alert emails contain job blocks with title, company, location links
        job_blocks = soup.find_all("table", class_=re.compile(r"job|listing", re.I))
        if not job_blocks:
            # Fallback: find all LinkedIn job URLs in the page
            for a in soup.find_all("a", href=_LINKEDIN_JOB_URL_RE):
                title = a.get_text(strip=True)
                url = a.get("href", "")
                # Clean tracking params
                url = re.sub(r"\?.*", "", url)
                if title and url:
                    jobs.append({
                        "title": title,
                        "company": "Unknown",
                        "location": _guess_location(locations),
                        "url": url,
                        "summary": "",
                    })
            return jobs

        for block in job_blocks:
            try:
                link = block.find("a", href=_LINKEDIN_JOB_URL_RE)
                if not link:
                    continue
                title = link.get_text(strip=True)
                url = re.sub(r"\?.*", "", link.get("href", ""))
                company_td = block.find(class_=re.compile(r"company|employer"))
                company = company_td.get_text(strip=True) if company_td else "Unknown"
                loc_td = block.find(class_=re.compile(r"location|city"))
                location = loc_td.get_text(strip=True) if loc_td else _guess_location(locations)
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": url,
                    "summary": "",
                })
            except Exception:
                continue

        return jobs

    def _parse_seek_alert(
        self, soup: BeautifulSoup, locations: List[str]
    ) -> List[Dict[str, Any]]:
        jobs = []
        for a in soup.find_all("a", href=_SEEK_JOB_URL_RE):
            title = a.get_text(strip=True)
            url = re.sub(r"\?.*", "", a.get("href", ""))
            if title and url:
                # Try to find company near the link
                parent = a.find_parent()
                company = "Unknown"
                location = _guess_location(locations)
                if parent:
                    next_sibling = parent.find_next_sibling()
                    if next_sibling:
                        sibling_text = next_sibling.get_text(strip=True)
                        if sibling_text:
                            company = sibling_text
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": url,
                    "summary": "",
                })
        return jobs

    @staticmethod
    def _decode_part(part: email.message.Message) -> str:
        payload = part.get_payload(decode=True)
        if not payload:
            return ""
        charset = part.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except Exception:
            return payload.decode("utf-8", errors="replace")


def _guess_location(locations: List[str]) -> str:
    """Return the first configured location as a fallback."""
    return locations[0] if locations else "Australia"
