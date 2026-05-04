"""Built In Melbourne connector.

Scrapes builtinmelbourne.com job listings — a curated tech-company job board
covering Melbourne startups and scale-ups (Xero, Square, Canva, etc.).

No public API; uses standard HTML pagination. Built In Sydney is defunct
(redirects to /lander), so Melbourne is the only AU edition available.

URL pattern: https://builtinmelbourne.com/jobs?page={n}
Card selector: [data-id="job-card"]
Level filter: span.font-barlow.text-gray-04 — [work_type, city, level] order.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

from jobradar.connectors.base import BaseConnector

_BASE_URL = "https://builtinmelbourne.com/jobs"
_JOB_BASE = "https://builtinmelbourne.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-AU,en;q=0.9",
}

# Levels that indicate grad/entry-level — the card's third font-barlow span
_JUNIOR_LEVELS = re.compile(
    r'\b(junior|graduate|entry[\s\-]?level|associate|intern(?:ship)?|cadet|'
    r'early[\s\-]?career|new\s+grad|recent\s+grad)\b',
    re.I,
)

_MAX_PAGES = 10  # safety cap; Built In Melbourne rarely exceeds 5 pages


class BuiltInConnector(BaseConnector):
    name = "BuiltIn"
    rate_limit_seconds = 2.0

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        all_jobs: List[Dict[str, Any]] = []
        for page in range(1, _MAX_PAGES + 1):
            params = {} if page == 1 else {"page": page}
            try:
                resp = requests.get(
                    _BASE_URL, headers=_HEADERS, params=params, timeout=15
                )
                resp.raise_for_status()
            except Exception as exc:
                print(f"[BuiltIn] page {page}: {exc}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select('[data-id="job-card"]')
            if not cards:
                break

            jobs = self._parse(cards)
            all_jobs.extend(jobs)

            # Stop if this page returned fewer cards than a full page (last page)
            if len(cards) < 10:
                break

            time.sleep(self.rate_limit_seconds)

        if all_jobs:
            print(f"[BuiltIn] Melbourne → {len(all_jobs)} AU grad/junior jobs")
        return all_jobs

    def _parse(self, cards) -> List[Dict[str, Any]]:
        jobs = []
        for card in cards:
            # Title + URL
            title_el = card.select_one('[data-id="job-card-title"]')
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href") or title_el.get("data-alias") or ""
            url = f"{_JOB_BASE}{href}" if href.startswith("/") else href

            # Company
            company_el = card.select_one('[data-id="company-title"] span')
            company = company_el.get_text(strip=True) if company_el else ""

            # Built In spans: [work_type, city, level, level_repeat]
            info_spans = [
                el.get_text(strip=True)
                for el in card.select("span.font-barlow.text-gray-04")
            ]
            # info_spans[0] = "Hybrid"/"Remote"/"In-Office"
            # info_spans[1] = "Melbourne"
            # info_spans[2] = "Mid level" / "Junior level" / etc.
            work_type = info_spans[0] if len(info_spans) > 0 else ""
            city      = info_spans[1] if len(info_spans) > 1 else "Melbourne"
            level     = info_spans[2] if len(info_spans) > 2 else ""

            # Pre-filter: only grad/junior/entry-level titles OR level span
            if not (
                _JUNIOR_LEVELS.search(title) or _JUNIOR_LEVELS.search(level)
            ):
                continue

            location = f"{city}, Australia" if city else "Melbourne, Australia"
            if work_type and work_type.lower() != "in-office":
                location = f"{work_type} – {location}"

            # Summary: top skills if available
            skills_el = card.select_one('[class*="d-md-inline"]')
            summary = skills_el.get_text(strip=True) if skills_el else ""

            if not title or not url:
                continue

            jobs.append({
                "title":    title,
                "company":  company,
                "location": location,
                "url":      url,
                "summary":  summary,
            })
        return jobs
