"""Atlassian careers connector.

Atlassian's all-jobs page is a SPA that hydrates from a custom JSON proxy
endpoint backed by their iCIMS instance. The endpoint is unauthenticated and
returns the full job list in a single GET, so we don't need to scrape HTML
or hit iCIMS directly.

API: GET https://www.atlassian.com/endpoint/careers/listings
Returns: list of job dicts with title, locations, category, applyUrl, and a
nested portalJobPost.portalUrl (the canonical iCIMS posting URL).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

import requests

from jobradar.connectors.base import BaseConnector

_ENDPOINT = "https://www.atlassian.com/endpoint/careers/listings"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_AU_LOCATION = re.compile(
    r'\baustralia\b|\badelaide\b|\bmelbourne\b|\bsydney\b|\bbrisbane\b|'
    r'\bperth\b|\bcanberra\b|\bhobart\b|\bdarwin\b|\bACT\b|\bNSW\b|\bVIC\b|'
    r'\bQLD\b|\bSA\b|\bWA\b|\bNT\b|\bTAS\b',
    re.I,
)

_LEVEL_PATTERN = re.compile(
    r'\bgraduate\b|\bjunior\b|\bentry[\s\-]?level\b|\bassociate\b|\bgrad\b|'
    r'\bearly[\s\-]?career\b|\bcadet\b|\bintern(?:ship)?\b',
    re.I,
)


class AtlassianConnector(BaseConnector):
    name = "Atlassian"
    rate_limit_seconds = 2.0

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        try:
            resp = requests.get(_ENDPOINT, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            items = resp.json()
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "?"
            print(f"[Atlassian] HTTP {code}")
            return []
        except Exception as exc:
            print(f"[Atlassian] {exc}")
            return []

        if not isinstance(items, list):
            print(f"[Atlassian] WARNING: unexpected response shape ({type(items).__name__})")
            return []

        jobs = self._parse(items)
        if jobs:
            print(f"[Atlassian] → {len(jobs)} AU grad/junior jobs")
        elif len(items) >= 50:
            print(f"[Atlassian] {len(items)} total postings, 0 matched AU+junior filters")
        return jobs

    def _parse(self, items: List[Dict]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for item in items:
            title = (item.get("title") or "").strip()
            if not title or not _LEVEL_PATTERN.search(title):
                continue

            loc_list = item.get("locations") or []
            location = ", ".join(l for l in loc_list if l) if loc_list else ""
            if not _AU_LOCATION.search(location):
                continue

            url = (item.get("applyUrl") or "").strip()
            if not url:
                portal = item.get("portalJobPost") or {}
                url = (portal.get("portalUrl") or "").strip()

            out.append({
                "title":    title,
                "company":  "Atlassian",
                "location": location or "Australia",
                "url":      url,
                "summary":  (item.get("category") or "").strip(),
            })
        return out
