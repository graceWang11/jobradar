"""Seek connector – uses Seek's public JSON search API (no login required).

Seek exposes the same API its own website uses:
  GET https://www.seek.com.au/api/jobsearch/v5/search

This returns structured JSON data directly — no HTML parsing needed.
"""

from __future__ import annotations

from typing import Any, Dict, List

import requests

from jobradar.connectors.base import BaseConnector


_API_URL = "https://www.seek.com.au/api/jobsearch/v5/search"

_LOCATION_QUERIES: Dict[str, str] = {
    "Adelaide": "Adelaide SA 5000",
    "Melbourne": "Melbourne VIC 3000",
}

_SEARCH_TERMS = [
    "junior software engineer",
    "graduate developer",
    "entry level software developer",
    "associate software engineer",
    "graduate software program",
    "junior developer",
]

# Targeted company/government searches – run without city restriction (Australia-wide)
# so we catch roles at these specific employers regardless of office location.
_COMPANY_SEARCHES = [
    # Big 4 + Accenture
    "Deloitte graduate technology",
    "KPMG technology graduate",
    "PwC graduate program technology",
    "EY technology graduate",
    "Accenture associate developer",
    "Accenture graduate technology",
    # Tech companies
    "Canva software engineer",
    "Canva graduate developer",
    # Government
    "SA government software developer",
    "SA government ICT graduate",
    "VIC government software developer",
    "VIC government ICT graduate",
    "APS graduate ICT",
    "Australian government graduate technology",
    "Department of software developer Australia",
]

_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://www.seek.com.au/",
    "Origin": "https://www.seek.com.au",
}


class SeekConnector(BaseConnector):
    name = "Seek"
    rate_limit_seconds = 2.0

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        jobs: List[Dict[str, Any]] = []

        # Standard location-based searches
        for location in locations:
            where = _LOCATION_QUERIES.get(location, location)
            for term in _SEARCH_TERMS:
                try:
                    results = self._search(term, where, location)
                    jobs.extend(results)
                    print(f"[Seek] {location} / '{term}' → {len(results)} jobs")
                except Exception as exc:
                    print(f"[Seek] Error {location}/{term}: {exc}")
                self._sleep()

        # Targeted company/government searches (Australia-wide, no city filter)
        # location_override="Australia" makes them pass the pipeline's location filter
        for term in _COMPANY_SEARCHES:
            try:
                results = self._search(term, None, "Australia", location_override="Australia")
                jobs.extend(results)
                print(f"[Seek] Company/Gov / '{term}' → {len(results)} jobs")
            except Exception as exc:
                print(f"[Seek] Error company/{term}: {exc}")
            self._sleep()

        return jobs

    def _search(
        self, keywords: str, where: str | None, location_label: str,
        location_override: str | None = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "siteKey": "AU-Main",
            "sourcesystem": "houston",
            "page": 1,
            "pageSize": 20,
            "keywords": keywords,
            "include": "seodata",
            "locale": "en-AU",
            "sortMode": "ListedDate",   # newest first
        }
        if where:
            params["where"] = where
        resp = requests.get(
            _API_URL, params=params, headers=_BASE_HEADERS, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        return self._parse(data.get("data", []), location_label, location_override)

    def _parse(
        self, items: List[Dict], location_label: str,
        location_override: str | None = None,
    ) -> List[Dict[str, Any]]:
        jobs = []
        for item in items:
            try:
                title = item.get("title", "").strip()
                if not title:
                    continue

                company = (
                    item.get("companyName")
                    or item.get("advertiser", {}).get("description", "Unknown")
                )

                # Location: use override (for company/govt searches) or Seek's value
                if location_override:
                    loc_label = location_override
                else:
                    locs = item.get("locations") or []
                    loc_label = locs[0].get("label", location_label) if locs else location_label

                # URL: build from job id
                job_id = item.get("id") or item.get("roleId", "")
                url = f"https://www.seek.com.au/job/{job_id}" if job_id else ""

                summary = item.get("teaser", "") or ""

                jobs.append(
                    {
                        "title": title,
                        "company": company,
                        "location": loc_label,
                        "url": url,
                        "summary": summary,
                    }
                )
            except Exception:
                continue
        return jobs
