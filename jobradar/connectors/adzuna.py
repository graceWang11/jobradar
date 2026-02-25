"""Adzuna job search API connector.

Adzuna is a free job aggregation API that pulls from Indeed, Jora,
and 50+ other job boards — solving the Indeed/Jora scraping block.

Free API key: https://developer.adzuna.com/signup
  - 250 requests/hour on the free tier
  - Add to .env:  ADZUNA_APP_ID=...  and  ADZUNA_APP_KEY=...
  - Add to GitHub Secrets: ADZUNA_APP_ID and ADZUNA_APP_KEY
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List

import requests

from jobradar.connectors.base import BaseConnector

_BASE_URL = "https://api.adzuna.com/v1/api/jobs/au/search/{page}"

_SEARCH_TERMS = [
    "junior software engineer",
    "graduate developer",
    "associate software engineer",
    "entry level software developer",
    "graduate technology program",
    "junior developer",
]


class AdzunaConnector(BaseConnector):
    """Fetches jobs via the Adzuna API (covers Indeed, Jora, + 50 other boards)."""

    rate_limit_seconds: float = 2.0

    def fetch(self, locations: list[str], keywords: list[str]) -> list[dict]:
        app_id  = os.environ.get("ADZUNA_APP_ID", "")
        app_key = os.environ.get("ADZUNA_APP_KEY", "")

        if not app_id or not app_key:
            print("[Adzuna] ADZUNA_APP_ID or ADZUNA_APP_KEY not set — skipping.")
            print("[Adzuna] Get a free key at https://developer.adzuna.com/signup")
            return []

        seen: set[str] = set()
        all_jobs: list[dict] = []

        for location in locations:
            for term in _SEARCH_TERMS:
                try:
                    jobs = self._search(app_id, app_key, term, location, seen)
                    all_jobs.extend(jobs)
                    print(f"[Adzuna] {location} / '{term}' → {len(jobs)} jobs")
                except Exception as exc:
                    print(f"[Adzuna] Error {location}/{term}: {exc}")
                time.sleep(self.rate_limit_seconds)

        return all_jobs

    def _search(
        self,
        app_id: str,
        app_key: str,
        query: str,
        location: str,
        seen: set[str],
    ) -> list[dict]:
        resp = requests.get(
            _BASE_URL.format(page=1),
            params={
                "app_id":           app_id,
                "app_key":          app_key,
                "what":             query,
                "where":            location,
                "results_per_page": 20,
                "sort_by":          "date",
                "max_days_old":     1,        # only last 24 hours
                "content-type":     "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        jobs: list[dict] = []
        for item in data.get("results", []):
            url = item.get("redirect_url", "")
            if not url or url in seen:
                continue
            seen.add(url)

            jobs.append({
                "title":       item.get("title", "").strip(),
                "company":     (item.get("company") or {}).get("display_name", ""),
                "location":    (item.get("location") or {}).get("display_name", location),
                "url":         url,
                "summary":     item.get("description", "")[:400],
                "date_posted": item.get("created", ""),
                "source":      "Adzuna",
            })

        return jobs
