"""Greenhouse ATS connector.

Polls the public Greenhouse job boards API for AU junior/grad tech roles.
No authentication required — boards-api.greenhouse.io is open to public reads.

API: GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Tuple

import requests
from bs4 import BeautifulSoup

from jobradar.connectors.base import BaseConnector

_API_BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# (display_name, board_slug)
# All slugs verified live against boards-api.greenhouse.io/<slug>/jobs.
# Add new entries only after confirming a 200 response from the API.
_GREENHOUSE_BOARDS: List[Tuple[str, str]] = [
    # AU-headquartered / AU-focused
    ("Thoughtworks",       "thoughtworks"),
    ("Culture Amp",        "cultureamp"),
    ("Buildkite",          "buildkite"),
    ("Quantium",           "quantium"),
    ("Block / Afterpay",   "block"),
    # Global SaaS/cloud with AU engineering presence
    ("GitLab",             "gitlab"),
    ("MongoDB",            "mongodb"),
    ("Cloudflare",         "cloudflare"),
    ("Datadog",            "datadog"),
    ("Twilio",             "twilio"),
    ("Okta",               "okta"),
    ("New Relic",          "newrelic"),
    ("PagerDuty",          "pagerduty"),
    ("Elastic",            "elastic"),
    ("Fastly",             "fastly"),
    ("Squarespace",        "squarespace"),
    ("Rubrik",             "rubrik"),
    ("HubSpot",            "hubspot"),
]

_AU_LOCATION = re.compile(
    r'\baustralia\b|\bmelbourne\b|\bsydney\b|\badelaide\b|\bbrisbane\b|'
    r'\bperth\b|\bcanberra\b|\bhobart\b|\bdarwin\b',
    re.I,
)

# "Remote" jobs are kept only if they don't have a non-AU country modifier
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


class GreenhouseConnector(BaseConnector):
    name = "Greenhouse"
    rate_limit_seconds = 1.5

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        all_jobs: List[Dict[str, Any]] = []
        for company_name, slug in _GREENHOUSE_BOARDS:
            try:
                jobs = self._fetch_board(company_name, slug)
                if jobs:
                    print(f"[Greenhouse] {company_name} → {len(jobs)} AU grad/junior jobs")
                all_jobs.extend(jobs)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in (404, 403):
                    pass  # board not found / private — skip silently
                else:
                    print(f"[Greenhouse] {company_name}: HTTP {exc}")
            except Exception as exc:
                print(f"[Greenhouse] {company_name}: {exc}")
            time.sleep(self.rate_limit_seconds)
        return all_jobs

    def _fetch_board(self, company_name: str, slug: str) -> List[Dict[str, Any]]:
        resp = requests.get(
            _API_BASE.format(slug=slug), headers=_HEADERS, timeout=15
        )
        resp.raise_for_status()
        return self._parse(resp.json().get("jobs", []), company_name, slug)

    def _parse(
        self, items: List[Dict], company_name: str, slug: str
    ) -> List[Dict[str, Any]]:
        jobs = []
        for item in items:
            title = (item.get("title") or "").strip()
            if not title:
                continue

            # Only grad/junior/entry-level titles
            if not _LEVEL_PATTERN.search(title):
                continue

            loc_obj = item.get("location") or {}
            location_raw = (loc_obj.get("name") or "").strip()

            # Offices list as secondary location source
            if not location_raw:
                offices = item.get("offices") or []
                if offices:
                    location_raw = (offices[0].get("location") or offices[0].get("name") or "").strip()

            # Skip if a non-AU location is explicitly stated.
            # Accept: AU cities/country, bare "Remote"/"Anywhere" (no country qualifier).
            # Reject: "Remote - US", "London", etc.
            if location_raw:
                is_au = _AU_LOCATION.search(location_raw)
                is_bare_remote = _REMOTE_ONLY.search(location_raw) and not _NON_AU_COUNTRY.search(location_raw)
                if not is_au and not is_bare_remote:
                    continue

            location = location_raw if location_raw else "Australia"
            job_id = item.get("id", "")
            url = (
                item.get("absolute_url")
                or f"https://boards.greenhouse.io/{slug}/jobs/{job_id}"
            )
            description_html = item.get("content") or ""
            summary = _strip_html(description_html)[:300]

            jobs.append({
                "title":   title,
                "company": company_name,
                "location": location,
                "url":     url,
                "summary": summary,
            })
        return jobs
