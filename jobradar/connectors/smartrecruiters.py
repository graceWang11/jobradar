"""SmartRecruiters ATS connector.

Polls the public SmartRecruiters postings API for AU junior/grad tech roles.
No authentication required — the v1 postings endpoint is fully public.

API: GET https://api.smartrecruiters.com/v1/companies/{slug}/postings
     ?limit=100&offset=0
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Tuple

import requests

from jobradar.connectors.base import BaseConnector

_API_BASE = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
_JOB_URL  = "https://jobs.smartrecruiters.com/{slug}/{job_id}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# (display_name, slug) — all verified to return totalFound > 0.
# Slug is case-insensitive on the API side; use the canonical casing shown here.
_SR_BOARDS: List[Tuple[str, str]] = [
    ("Canva",           "canva"),
    ("SEEK",            "SEEK"),
    ("Nearmap",         "Nearmap"),
    ("Carsales",        "carsales"),
    ("WiseTech Global", "WiseTechGlobal"),
    ("SiteMinder",      "Siteminder"),
    ("Versent",         "Versent"),
]

_AU_COUNTRY = re.compile(r'^au$', re.I)

_LEVEL_PATTERN = re.compile(
    r'\bgraduate\b|\bjunior\b|\bentry[\s\-]?level\b|\bassociate\b|\bgrad\b|'
    r'\bearly[\s\-]?career\b|\bcadet\b|\bintern(?:ship)?\b',
    re.I,
)

_PAGE_SIZE = 100


class SmartRecruitersConnector(BaseConnector):
    name = "SmartRecruiters"
    rate_limit_seconds = 1.5

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        all_jobs: List[Dict[str, Any]] = []
        for company_name, slug in _SR_BOARDS:
            try:
                jobs = self._fetch_company(company_name, slug)
                if jobs:
                    print(f"[SmartRecruiters] {company_name} → {len(jobs)} AU grad/junior jobs")
                all_jobs.extend(jobs)
            except Exception as exc:
                print(f"[SmartRecruiters] {company_name}: {exc}")
            time.sleep(self.rate_limit_seconds)
        return all_jobs

    def _fetch_company(self, company_name: str, slug: str) -> List[Dict[str, Any]]:
        url = _API_BASE.format(slug=slug)
        offset = 0
        collected: List[Dict[str, Any]] = []

        while True:
            resp = requests.get(
                url,
                headers=_HEADERS,
                params={"limit": _PAGE_SIZE, "offset": offset},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", [])
            if not content:
                break

            collected.extend(self._parse(content, company_name, slug))

            total = data.get("totalFound", 0)
            offset += _PAGE_SIZE
            if offset >= total:
                break

            time.sleep(0.5)  # inter-page delay

        return collected

    def _parse(
        self, items: List[Dict], company_name: str, slug: str
    ) -> List[Dict[str, Any]]:
        jobs = []
        for item in items:
            title = (item.get("name") or "").strip()
            if not title:
                continue

            # AU location only
            loc = item.get("location") or {}
            country = (loc.get("country") or "").strip()
            if not _AU_COUNTRY.match(country):
                continue

            # Only grad/junior/entry-level titles
            if not _LEVEL_PATTERN.search(title):
                continue

            city = (loc.get("city") or "").strip()
            location = f"{city}, Australia" if city else "Australia"

            job_id = item.get("id") or item.get("uuid") or ""
            url = _JOB_URL.format(slug=slug, job_id=job_id) if job_id else ""

            # releasedDate is ISO8601 e.g. "2026-05-01T09:45:03.001Z"
            released = (item.get("releasedDate") or "")[:10]

            exp_label = (item.get("experienceLevel") or {}).get("label") or ""
            fn_label  = (item.get("function") or {}).get("label") or ""
            summary = f"{fn_label} – {exp_label}".strip(" –")

            jobs.append({
                "title":    title,
                "company":  company_name,
                "location": location,
                "url":      url,
                "summary":  summary,
            })
        return jobs
