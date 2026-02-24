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

        return jobs

    def _search(
        self, keywords: str, where: str, location_label: str
    ) -> List[Dict[str, Any]]:
        params = {
            "siteKey": "AU-Main",
            "sourcesystem": "houston",
            "where": where,
            "page": 1,
            "pageSize": 20,
            "keywords": keywords,
            "include": "seodata",
            "locale": "en-AU",
            "sortMode": "ListedDate",   # newest first
        }
        resp = requests.get(
            _API_URL, params=params, headers=_BASE_HEADERS, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        return self._parse(data.get("data", []), location_label)

    def _parse(
        self, items: List[Dict], location_label: str
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

                # Location: Seek returns a locations list
                locs = item.get("locations") or []
                if locs:
                    loc_label = locs[0].get("label", location_label)
                else:
                    loc_label = location_label

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
