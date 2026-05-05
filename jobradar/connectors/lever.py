"""Lever ATS connector.

Polls the public Lever postings API for AU junior/grad tech roles.
No authentication required.

API: GET https://api.lever.co/v0/postings/{company}?mode=json
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Tuple

import requests
from bs4 import BeautifulSoup

from jobradar.connectors.base import BaseConnector

_API_BASE = "https://api.lever.co/v0/postings/{company}?mode=json"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# (display_name, company_slug)
_LEVER_COMPANIES: List[Tuple[str, str]] = [
    ("Airwallex",          "airwallex"),
    ("Rokt",               "rokt"),
    ("Dovetail",           "dovetail"),
    ("Prospa",             "prospa"),
    ("Judo Bank",          "judo-bank"),
    ("Finder",             "finder"),
    ("Assembly Payments",  "assembly"),
    ("Lendi",              "lendi"),
    ("Employment Hero",    "employmenthero"),
    ("Eucalyptus",         "eucalyptusvc"),
    ("Flare HR",           "flarehr"),
    ("Linktree",           "linktree"),
    ("Siteminder",         "siteminder"),
    ("Campaign Monitor",   "campaignmonitor"),
    ("Intellicheck",       "intellicheck"),
    ("Deputy",             "deputy"),
    ("SafetyCulture",      "safetyculture-2"),
]

_AU_LOCATION = re.compile(
    r'\baustralia\b|\bmelbourne\b|\bsydney\b|\badelaide\b|\bbrisbane\b|'
    r'\bperth\b|\bcanberra\b|\bhobart\b|\bdarwin\b',
    re.I,
)
_REMOTE_ONLY = re.compile(r'^\s*remote\s*$|\banywhere\b', re.I)
_NON_AU_COUNTRY = re.compile(
    r'\b(us|usa|united\s+states|uk|united\s+kingdom|canada|india|'
    r'singapore|germany|france|netherlands|ireland|poland)\b',
    re.I,
)

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


class LeverConnector(BaseConnector):
    name = "Lever"
    rate_limit_seconds = 1.5

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        all_jobs: List[Dict[str, Any]] = []
        for company_name, slug in _LEVER_COMPANIES:
            try:
                jobs = self._fetch_company(company_name, slug)
                if jobs:
                    print(f"[Lever] {company_name} → {len(jobs)} AU grad/junior jobs")
                all_jobs.extend(jobs)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in (404, 403):
                    pass
                else:
                    print(f"[Lever] {company_name}: HTTP {exc}")
            except Exception as exc:
                print(f"[Lever] {company_name}: {exc}")
            time.sleep(self.rate_limit_seconds)
        return all_jobs

    def _fetch_company(self, company_name: str, slug: str) -> List[Dict[str, Any]]:
        resp = requests.get(
            _API_BASE.format(company=slug), headers=_HEADERS, timeout=15
        )
        resp.raise_for_status()
        items = resp.json()
        if not isinstance(items, list):
            return []
        return self._parse(items, company_name)

    def _parse(self, items: List[Dict], company_name: str) -> List[Dict[str, Any]]:
        jobs = []
        for item in items:
            title = (item.get("text") or "").strip()
            if not title:
                continue

            if not _LEVEL_PATTERN.search(title):
                continue

            categories = item.get("categories") or {}
            location_raw = (
                categories.get("location")
                or categories.get("allLocations", [""])[0]
                if isinstance(categories.get("allLocations"), list)
                else categories.get("allLocations") or ""
            ).strip()

            if location_raw:
                is_au = _AU_LOCATION.search(location_raw)
                is_bare_remote = _REMOTE_ONLY.search(location_raw) and not _NON_AU_COUNTRY.search(location_raw)
                if not is_au and not is_bare_remote:
                    continue

            location = location_raw if location_raw else "Australia"
            url = item.get("hostedUrl") or item.get("applyUrl") or ""

            # Lever description is HTML — combine main body + lists
            description_html = (item.get("description") or "") + " ".join(
                lst.get("content", "") for lst in (item.get("lists") or [])
            )
            summary = _strip_html(description_html)[:300]

            jobs.append({
                "title":    title,
                "company":  company_name,
                "location": location,
                "url":      url,
                "summary":  summary,
            })
        return jobs
