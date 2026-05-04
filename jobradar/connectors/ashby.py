"""Ashby ATS connector.

Polls the public Ashby job-board API for AU junior/grad tech roles.
No authentication required — the posting-api endpoint is fully public.

API: GET https://api.ashbyhq.com/posting-api/job-board/{slug}
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Tuple

import requests
from bs4 import BeautifulSoup

from jobradar.connectors.base import BaseConnector

_API_BASE = "https://api.ashbyhq.com/posting-api/job-board/{slug}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# (display_name, board_slug) — all verified to return HTTP 200 from the API.
# Boards with 0 postings today will yield results when roles open.
_ASHBY_BOARDS: List[Tuple[str, str]] = [
    ("Airwallex",    "airwallex"),
    ("Xero",         "xero"),
    ("Zip Co",       "zip"),
    ("Rokt",         "rokt"),
    ("Dovetail",     "dovetail"),
    ("Airtasker",    "airtasker"),
    ("Morse Micro",  "morse-micro"),
    ("Ignition",     "ignition"),
]

_AU_LOCATION = re.compile(
    r'\baustralia\b|\badelaide\b|\bmelbourne\b|\bsydney\b|\bbrisbane\b|'
    r'\bperth\b|\bcanberra\b|\bhobart\b|\bdarwin\b',
    re.I,
)

_REMOTE_ONLY = re.compile(r'^\s*remote\s*$|\banywhere\b|\bglobal\b', re.I)

_LEVEL_PATTERN = re.compile(
    r'\bgraduate\b|\bjunior\b|\bentry[\s\-]?level\b|\bassociate\b|\bgrad\b|'
    r'\bearly[\s\-]?career\b|\bcadet\b|\bintern(?:ship)?\b',
    re.I,
)


def _strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)[:2000]


class AshbyConnector(BaseConnector):
    name = "Ashby"
    rate_limit_seconds = 1.5

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        all_jobs: List[Dict[str, Any]] = []
        for company_name, slug in _ASHBY_BOARDS:
            try:
                jobs = self._fetch_board(company_name, slug)
                if jobs:
                    print(f"[Ashby] {company_name} → {len(jobs)} AU grad/junior jobs")
                all_jobs.extend(jobs)
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else "?"
                if code not in (404, 403):
                    print(f"[Ashby] {company_name}: HTTP {code}")
            except Exception as exc:
                print(f"[Ashby] {company_name}: {exc}")
            time.sleep(self.rate_limit_seconds)
        return all_jobs

    def _fetch_board(self, company_name: str, slug: str) -> List[Dict[str, Any]]:
        resp = requests.get(_API_BASE.format(slug=slug), headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        return self._parse(resp.json().get("jobPostings", []), company_name, slug)

    def _parse(
        self, items: List[Dict], company_name: str, slug: str
    ) -> List[Dict[str, Any]]:
        jobs = []
        for item in items:
            if not item.get("isListed", True):
                continue

            title = (item.get("title") or "").strip()
            if not title:
                continue

            if not _LEVEL_PATTERN.search(title):
                continue

            location_raw = (item.get("locationName") or "").strip()

            # Accept: AU cities/country, bare "Remote"/"Anywhere"/"Global".
            # Reject: "Remote - US", "London", blank (unknown).
            if location_raw:
                is_au = _AU_LOCATION.search(location_raw)
                is_remote = _REMOTE_ONLY.search(location_raw)
                if not is_au and not is_remote:
                    continue
            # blank locationName → keep (listed role, no location info)

            location = location_raw if location_raw else "Australia"

            # Prefer jobUrl / applyUrl from the posting
            url = (
                item.get("jobUrl")
                or item.get("applyUrl")
                or f"https://jobs.ashbyhq.com/{slug}/{item.get('id', '')}"
            )

            description_html = item.get("descriptionHtml") or ""
            summary = _strip_html(description_html)[:300]

            team = (item.get("teamName") or "").strip()
            if team and not summary:
                summary = team

            jobs.append({
                "title":    title,
                "company":  company_name,
                "location": location,
                "url":      url,
                "summary":  summary,
            })
        return jobs
