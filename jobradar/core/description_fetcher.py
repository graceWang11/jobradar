"""Fetch full job description text from each job's URL.

Called after the initial pipeline filters have reduced the job count.
This lets us apply stricter content checks (3-year experience clauses,
citizenship requirements buried in the description body) before emailing.

Strategies by source:
  Seek        — SKIPPED (job pages return 403; teaser already in j.summary)
  LinkedIn    — SKIPPED (requires login)
  GradConnection — generic HTML extraction ✓
  Prosple     — generic HTML extraction ✓
  Amazon (CC) — generic HTML extraction ✓
  Adzuna      — generic HTML extraction ✓ (follows redirect to source)
  Others      — generic HTML extraction ✓

If fetch fails for any reason the job is kept (fail-open) — we never
discard a job purely because its description page was unreachable.
"""

from __future__ import annotations

import time
from typing import List

import requests
from bs4 import BeautifulSoup

from jobradar.core.models import JobListing

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

_MAX_CHARS = 8_000   # cap per description to keep memory sane


def _fetch_html(url: str) -> str:
    """GET a URL and return HTML text, or empty string on any error."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return ""


def _text_from_html(html: str) -> str:
    """Strip nav/script/style, return plain text (capped at _MAX_CHARS)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)[:_MAX_CHARS]



def fetch_description(job: JobListing) -> str:
    """Fetch full description for a single job. Returns empty string on failure."""
    if not job.url:
        return ""
    # LinkedIn requires login — skip
    if "linkedin.com" in job.url:
        return ""
    # Seek job detail pages return 403 (bot protection) and their detail API
    # endpoints 404 — skip to avoid wasting time on each job.
    # Seek teaser is already in j.summary and checked by the earlier filters.
    if "seek.com.au" in job.url:
        return ""

    html = _fetch_html(job.url)
    if not html:
        return ""

    return _text_from_html(html)


def fetch_descriptions(jobs: List[JobListing], delay: float = 1.5) -> None:
    """Fetch and store full description text for each job in-place.

    Jobs whose description page fails are kept with description="" so the
    pipeline treats them as pass-through (fail-open).
    """
    if not jobs:
        return

    print(f"\n[Fetcher] Fetching full descriptions for {len(jobs)} jobs…")
    for i, job in enumerate(jobs, 1):
        desc = fetch_description(job)
        job.description = desc
        source_tag = f"[{job.source}]"
        char_info = f"{len(desc):,} chars" if desc else "skipped/failed"
        print(f"[Fetcher] {i}/{len(jobs)} {source_tag} {job.title[:50]!r} → {char_info}")
        # Don't sleep for sources we immediately skip (no network request made)
        skipped_sources = ("seek.com.au", "linkedin.com")
        if delay > 0 and not any(s in job.url for s in skipped_sources):
            time.sleep(delay)
