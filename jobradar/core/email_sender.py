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


def build_html_body(jobs: List[JobListing], run_date: date) -> str:
    """Inline HTML email body (compact table)."""
    rows = []
    for j in jobs:
        score_color = "green" if j.visa_score >= 4 else ("red" if j.visa_score <= 1 else "gray")
        rows.append(
            f"<tr>"
            f"<td>{j.date_found}</td>"
            f"<td>{j.source}</td>"
            f'<td><a href="{j.url}">{j.title}</a></td>'
            f"<td>{j.company}</td>"
            f"<td>{j.location}</td>"
            f"<td>{', '.join(j.tags)}</td>"
            f'<td style="color:{score_color};font-weight:bold">{j.visa_score if j.visa_score >= 0 else "–"}</td>'
            f"<td>{j.visa_reason}</td>"
            f"</tr>"
        )

    table_rows = "\n".join(rows)
    return f"""\
<html><body>
<h2>JobRadar – Daily Junior/Grad Jobs</h2>
<p>Adelaide &amp; Melbourne | {run_date} | <strong>{len(jobs)} new listings</strong></p>
<table border="1" cellspacing="0" cellpadding="5" style="border-collapse:collapse;font-size:12px">
<thead style="background:#2c3e50;color:white">
  <tr>
    <th>Date</th><th>Source</th><th>Title</th><th>Company</th>
    <th>Location</th><th>Tags</th><th>Visa</th><th>Visa Reason</th>
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
) -> None:
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
        return

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

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, [recipient], msg.as_string())
        print(f"[email] Sent to {recipient} ✓")
    except Exception as exc:
        print(f"[email] Failed to send: {exc}")
        raise
