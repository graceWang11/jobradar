"""SMTP email delivery – sends the daily job summary."""

from __future__ import annotations

import os
import smtplib
from datetime import date
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List

from jobradar.core.models import JobListing


def _build_top5_email(jobs: List[JobListing]) -> str:
    candidates = sorted(jobs, key=lambda j: -(j.match_score * 2 + j.visa_score))
    top5 = candidates[:5]
    if not top5:
        return ""
    items = []
    for i, j in enumerate(top5, 1):
        match_str = f"{j.match_score}/10" if j.match_score >= 0 else "–"
        visa_str = f"{j.visa_score}/5" if j.visa_score >= 0 else "–"
        if j.recruiter_contacts:
            contact_parts = []
            for c in j.recruiter_contacts[:3]:
                name = c.get("name", "")
                title = c.get("title", "")
                url = c.get("linkedin_url", "")
                line = f'<a href="{url}" style="color:#1a6fa0;font-size:11px">{name}</a>' if url else name
                if title:
                    line += f'<span style="color:#888;font-size:10px"> · {title}</span>'
                contact_parts.append(line)
            recruiter_cell = "<br>".join(contact_parts)
        else:
            recruiter_cell = (
                f'<a href="{j.recruiter_url}" style="color:#1a6fa0;font-size:11px">Find recruiter →</a>'
                if j.recruiter_url else "–"
            )
        outreach_cell = (
            f'<span style="font-family:monospace;font-size:10px;color:#444">{j.outreach_msg}</span>'
            if j.outreach_msg else ""
        )
        items.append(
            f'<tr style="background:#f0f7ff">'
            f'<td style="padding:8px;font-weight:bold">{i}</td>'
            f'<td style="padding:8px"><a href="{j.url}" style="color:#1a6fa0">{j.title}</a></td>'
            f'<td style="padding:8px">{j.company}</td>'
            f'<td style="padding:8px">{j.location}</td>'
            f'<td style="padding:8px;color:#1a6fa0;font-weight:bold">{match_str}</td>'
            f'<td style="padding:8px;color:green;font-weight:bold">{visa_str}</td>'
            f'<td style="padding:8px;color:#555;font-size:11px">{j.match_skills}</td>'
            f'<td style="padding:8px">{recruiter_cell}<br>{outreach_cell}</td>'
            f'</tr>'
        )
    rows_html = "\n".join(items)
    return f"""\
<h3 style="color:#1a6fa0;margin-bottom:6px">&#11088; Top 5 – Apply Today</h3>
<table border="1" cellspacing="0" cellpadding="0"
       style="border-collapse:collapse;font-size:12px;margin-bottom:20px">
  <thead style="background:#1a6fa0;color:white">
    <tr>
      <th style="padding:6px">#</th><th style="padding:6px">Title</th>
      <th style="padding:6px">Company</th><th style="padding:6px">Location</th>
      <th style="padding:6px">Match</th><th style="padding:6px">Visa</th>
      <th style="padding:6px">Skills</th>
      <th style="padding:6px">Recruiter / Outreach</th>
    </tr>
  </thead>
  <tbody>
{rows_html}
  </tbody>
</table>
"""


def build_html_body(jobs: List[JobListing], run_date: date) -> str:
    """Inline HTML email body (compact table)."""
    rows = []
    for j in jobs:
        score_color = "green" if j.visa_score >= 4 else ("red" if j.visa_score <= 1 else "gray")
        match_color = "#1a6fa0" if j.match_score >= 6 else "#888"
        if j.recruiter_contacts:
            recruiter_cell = " · ".join(
                f'<a href="{c.get("linkedin_url","")}" style="color:#1a6fa0;font-size:11px">'
                f'{c.get("name","")}</a>'
                for c in j.recruiter_contacts[:3]
                if c.get("name")
            ) or "–"
        else:
            recruiter_cell = (
                f'<a href="{j.recruiter_url}" style="color:#1a6fa0;font-size:11px">Search →</a>'
                if j.recruiter_url else "–"
            )
        rows.append(
            f"<tr>"
            f"<td>{j.date_found}</td>"
            f"<td>{j.source}</td>"
            f'<td><a href="{j.url}">{j.title}</a></td>'
            f"<td>{j.company}</td>"
            f"<td>{j.location}</td>"
            f"<td>{', '.join(j.tags)}</td>"
            f'<td style="color:{match_color};font-weight:bold">{j.match_score if j.match_score >= 0 else "–"}</td>'
            f'<td style="font-size:11px;color:#555">{j.match_skills}</td>'
            f'<td style="color:{score_color};font-weight:bold">{j.visa_score if j.visa_score >= 0 else "–"}</td>'
            f"<td>{j.visa_reason}</td>"
            f"<td>{recruiter_cell}</td>"
            f"</tr>"
        )

    table_rows = "\n".join(rows)
    top5_block = _build_top5_email(jobs)
    return f"""\
<html><body style="font-family:Arial,sans-serif;font-size:13px">
<h2 style="color:#2c3e50">JobRadar – Daily Junior/Grad Jobs</h2>
<p>Adelaide &amp; Melbourne | {run_date} | <strong>{len(jobs)} new listings</strong></p>
{top5_block}
<h3 style="color:#2c3e50">All New Jobs</h3>
<table border="1" cellspacing="0" cellpadding="5" style="border-collapse:collapse;font-size:12px">
<thead style="background:#2c3e50;color:white">
  <tr>
    <th>Date</th><th>Source</th><th>Title</th><th>Company</th>
    <th>Location</th><th>Tags</th><th>Match</th><th>Skills</th>
    <th>Visa</th><th>Visa Reason</th><th>Find Contacts</th>
  </tr>
</thead>
<tbody>
{table_rows}
</tbody>
</table>
<p style="font-size:11px;color:#888">Sent by JobRadar – automated job aggregator</p>
</body></html>
"""


def send_email(
    jobs: List[JobListing],
    csv_path: Path,
    run_date: date | None = None,
) -> bool:
    """
    Send the daily summary email via SMTP.

    Requires these environment variables (from .env):
      EMAIL_ADDRESS  – sender address
      EMAIL_PASSWORD – app password (Gmail) or SMTP password
      EMAIL_TO       – recipient address
      SMTP_SERVER    – defaults to smtp.gmail.com
      SMTP_PORT      – defaults to 587
    """
    run_date = run_date or date.today()

    sender = os.environ.get("EMAIL_ADDRESS", "")
    password = os.environ.get("EMAIL_PASSWORD", "")
    recipient = os.environ.get("EMAIL_TO", sender)
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    if not sender or not password:
        print("[email] EMAIL_ADDRESS or EMAIL_PASSWORD not set – skipping send.")
        return False

    subject = f"Daily Junior/Grad Jobs – Adelaide & Melbourne – {run_date}"
    html_body = build_html_body(jobs, run_date)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Attach CSV
    if csv_path.exists():
        with open(csv_path, "rb") as fh:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(fh.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{csv_path.name}"',
        )
        msg.attach(part)

    raw = msg.as_string()

    def _try_starttls() -> None:
        """Port 587 with STARTTLS (standard)."""
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, [recipient], raw)

    def _try_ssl() -> None:
        """Port 465 with implicit SSL (fallback when 587 is blocked)."""
        with smtplib.SMTP_SSL(smtp_server, 465, timeout=15) as server:
            server.login(sender, password)
            server.sendmail(sender, [recipient], raw)

    def _record() -> None:
        try:
            from jobradar.api.recorder import record_outbound

            record_outbound(
                to_email=recipient,
                subject=subject,
                job_id=None,
            )
        except Exception as exc:
            print(f"[email] (recorder skipped: {exc})")

    try:
        _try_starttls()
        print(f"[email] Sent to {recipient} ✓")
        _record()
        return True
    except (TimeoutError, OSError):
        print("[email] Port 587 timed out — retrying on port 465/SSL …")
        try:
            _try_ssl()
            print(f"[email] Sent to {recipient} via SSL ✓")
            _record()
            return True
        except (TimeoutError, OSError):
            print(
                "[email] Both ports 587 and 465 timed out.\n"
                "[email] Your network/ISP is blocking outbound SMTP."
            )
        except Exception as exc:
            print(f"[email] Failed to send: {exc}")
    except Exception as exc:
        print(f"[email] Failed to send: {exc}")
    return False
