"""Prosple connector – Australian graduate/early-career jobs.

Prosple uses Next.js with server-side rendering. All job data is embedded
in a <script id="__NEXT_DATA__"> JSON block — no HTML scraping needed.

Australian endpoint: https://au.prosple.com/search-jobs/
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from jobradar.connectors.base import BaseConnector


_BASE_URL = "https://au.prosple.com/search-jobs/"

# Prosple location IDs for state filtering
_STATE_PARAMS: Dict[str, str] = {
    "Adelaide": "SA",
    "Melbourne": "VIC",
}

_TARGET_CITIES = {
    "Adelaide": ["adelaide", "south australia"],
    "Melbourne": ["melbourne", "victoria"],
}

_SEARCH_TERMS = [
    "graduate software",
    "junior developer",
    "graduate program technology",
    "software engineer graduate",
]


class ProspleConnector(BaseConnector):
    name = "Prosple"
    rate_limit_seconds = 2.5

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        jobs: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()

        for term in _SEARCH_TERMS:
            try:
                raw = self._fetch_page(term)
                # Filter to target locations client-side
                for job in raw:
                    if job["url"] in seen_urls:
                        continue
                    loc = job.get("location", "").lower()
                    if any(
                        city_kw in loc
                        for target in locations
                        for city_kw in _TARGET_CITIES.get(target, [target.lower()])
                    ):
                        seen_urls.add(job["url"])
                        jobs.append(job)
                print(f"[Prosple] '{term}' → {len(raw)} total, kept {len([j for j in raw if j['url'] in seen_urls])} in target cities")
            except Exception as exc:
                print(f"[Prosple] Error fetching '{term}': {exc}")
            self._sleep()

        return jobs

    def _fetch_page(self, search: str) -> List[Dict[str, Any]]:
        params = {"search": search}
        resp = requests.get(
            _BASE_URL, params=params, headers=self._HEADERS, timeout=15
        )
        resp.raise_for_status()
        return self._parse_next_data(resp.text)

    def _parse_next_data(self, html: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script:
            return []

        data = json.loads(script.string)
        opportunities = (
            data.get("props", {})
                .get("pageProps", {})
                .get("initialResult", {})
                .get("opportunities", [])
        )

        jobs = []
        for opp in opportunities:
            try:
                title = opp.get("title", "").strip()
                if not title:
                    continue

                # Employer
                employer = opp.get("parentEmployer") or {}
                company = employer.get("title", "").strip() or employer.get("advertiserName", "Unknown")

                # Location — extract all cities, prefer Adelaide/Melbourne
                geo = opp.get("geoAddresses") or []
                cities = list(dict.fromkeys(
                    g.get("locality", "") or g.get("region", "")
                    for g in geo
                    if g.get("locality") or g.get("region")
                ))
                # Show only the target cities if present, otherwise all
                target_match = [c for c in cities if c.lower() in ("adelaide", "melbourne")]
                location = ", ".join(target_match) if target_match else ", ".join(cities) if cities else "Australia"

                # URL
                detail = opp.get("detailPageURL", "") or ""
                url = f"https://au.prosple.com{detail}" if detail else ""
                if not url:
                    continue

                # Summary
                overview = opp.get("overview") or {}
                summary = overview.get("summary", "") if isinstance(overview, dict) else ""

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": url,
                    "summary": summary,
                })
            except Exception:
                continue

        return jobs
