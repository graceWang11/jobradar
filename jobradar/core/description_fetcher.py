"""Fetch full job description text from each job's URL.

Called after the initial pipeline filters have reduced the job count.
This lets us apply stricter content checks (3-year experience clauses,
citizenship requirements buried in the description body) before emailing.

Strategies by source:
  Seek        — Playwright + stealth (headless Chromium; falls back to "" if not installed)
  LinkedIn    — SKIPPED (requires login; teaser is the only available signal)
  GradConnection — generic HTML extraction ✓
  Prosple     — generic HTML extraction ✓
  Amazon (CC) — generic HTML extraction ✓
  Adzuna      — generic HTML extraction ✓ (follows redirect to source)
  Greenhouse  — description already stored in summary at connector level
  Others      — generic HTML extraction ✓

If fetch fails for any reason the job is kept (fail-open) — we never
discard a job purely because its description page was unreachable.

For Seek and LinkedIn, description="" is intentional (not a failure):
  • Seek  — Playwright fetch attempted; empty string means bot protection blocked it
  • LinkedIn — always skipped; teaser is all we have
The pipeline treats both as "no additional description signal available" and
relies on the title+teaser visa check that already ran in _passes_visa.
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
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

_MAX_CHARS = 8_000


def _fetch_html(url: str) -> str:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return ""


def _text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)[:_MAX_CHARS]


# ── Playwright-based Seek fetcher ─────────────────────────────────────────────

def _seek_text_from_page(page) -> str:  # type: ignore[no-untyped-def]
    """Extract job description text from an already-loaded Seek page."""
    # Primary: the jobAdDetails data-automation attribute
    elem = page.query_selector('[data-automation="jobAdDetails"]')
    if elem:
        return elem.inner_text()[:_MAX_CHARS]
    # Fallback: parse full page HTML
    return _text_from_html(page.content())


def _fetch_seek_descriptions(jobs: List[JobListing], delay: float = 1.0) -> None:
    """Fetch descriptions for all Seek jobs using Playwright (stealth headless Chromium).

    Requires: pip install playwright playwright-stealth && playwright install chromium
    Silently skips if Playwright is not installed — leaves description="" which
    the pipeline treats as "no additional signal" (fail-open for Seek).
    """
    seek_jobs = [j for j in jobs if "seek.com.au" in j.url and not j.description]
    if not seek_jobs:
        return

    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
    except ImportError:
        print(
            f"[Fetcher] playwright / playwright-stealth not installed — "
            f"skipping {len(seek_jobs)} Seek descriptions. "
            f"Run: pip install playwright playwright-stealth && playwright install chromium"
        )
        return

    print(f"[Fetcher] Playwright: fetching {len(seek_jobs)} Seek descriptions…")
    stealth = Stealth()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-AU",
            timezone_id="Australia/Melbourne",
            viewport={"width": 1280, "height": 900},
        )

        for i, job in enumerate(seek_jobs, 1):
            try:
                page = ctx.new_page()
                stealth.apply_stealth_sync(page)
                page.goto(job.url, wait_until="networkidle", timeout=30_000)
                text = _seek_text_from_page(page)
                page.close()

                if text:
                    job.description = text
                    print(
                        f"[Fetcher] Seek {i}/{len(seek_jobs)} "
                        f"{job.title[:45]!r} → {len(text):,} chars"
                    )
                else:
                    print(
                        f"[Fetcher] Seek {i}/{len(seek_jobs)} "
                        f"{job.title[:45]!r} → no content (bot block?)"
                    )
            except Exception as exc:
                print(
                    f"[Fetcher] Seek {i}/{len(seek_jobs)} "
                    f"{job.title[:45]!r} → {exc}"
                )
            time.sleep(delay)

        browser.close()


# ── Generic HTTP fetcher ───────────────────────────────────────────────────────

def fetch_description(job: JobListing) -> str:
    """Fetch full description for a single job via plain HTTP. Returns "" on failure."""
    if not job.url:
        return ""
    # LinkedIn requires login — skip (teaser is the only available signal)
    if "linkedin.com" in job.url:
        return ""
    # Seek is handled separately via Playwright
    if "seek.com.au" in job.url:
        return ""
    html = _fetch_html(job.url)
    return _text_from_html(html) if html else ""


def fetch_descriptions(jobs: List[JobListing], delay: float = 1.5) -> None:
    """Fetch and store full description text for each job in-place.

    • Seek jobs are fetched in a single Playwright browser session (stealth).
    • LinkedIn jobs are skipped — login required, teaser is final signal.
    • All other sources use plain HTTP with rate-limiting delay.
    • Fail-open: jobs whose description can't be fetched are kept with description="".
    """
    if not jobs:
        return

    # ── Seek: batch Playwright fetch ─────────────────────────────────────────
    _fetch_seek_descriptions(jobs, delay=1.0)

    # ── Everything else: plain HTTP ───────────────────────────────────────────
    non_seek_non_li = [
        j for j in jobs
        if "seek.com.au" not in j.url and "linkedin.com" not in j.url
    ]
    skipped_sources = {"seek.com.au", "linkedin.com"}

    if non_seek_non_li:
        print(f"[Fetcher] HTTP fetch for {len(non_seek_non_li)} non-Seek/LinkedIn jobs…")

    for i, job in enumerate(non_seek_non_li, 1):
        desc = fetch_description(job)
        job.description = desc
        source_tag = f"[{job.source}]"
        char_info = f"{len(desc):,} chars" if desc else "skipped/failed"
        print(f"[Fetcher] {i}/{len(non_seek_non_li)} {source_tag} {job.title[:50]!r} → {char_info}")
        if delay > 0 and not any(s in job.url for s in skipped_sources):
            time.sleep(delay)
