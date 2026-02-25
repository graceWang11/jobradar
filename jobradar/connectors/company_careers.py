"""Direct company career page scrapers.

Currently working:
  - Amazon/AWS  (amazon.jobs public JSON API)

Others (Deloitte, KPMG, PwC, EY, Accenture, Canva) are covered via
targeted Seek searches in seek.py since their own portals are JS-rendered
and have no public API.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import requests

from jobradar.connectors.base import BaseConnector

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
    "Accept-Language": "en-AU,en;q=0.9",
}

_GRAD_QUERIES = [
    "graduate software engineer",
    "junior software developer",
    "associate software engineer",
    "technology graduate",
    "graduate technology program",
]


class CompanyCareersConnector(BaseConnector):
    """Fetches junior/grad roles directly from target company career sites."""

    rate_limit_seconds: float = 2.0

    def fetch(self, locations: list[str], keywords: list[str]) -> list[dict]:
        jobs = self._fetch_amazon()
        return jobs

    def _fetch_amazon(self) -> list[dict]:
        """Amazon Jobs public JSON API — covers both Amazon and AWS roles."""
        url = "https://www.amazon.jobs/en/search.json"
        seen: set[str] = set()
        jobs: list[dict] = []

        for q in _GRAD_QUERIES:
            try:
                resp = requests.get(
                    url,
                    params={
                        "base_query": q,
                        "loc_query":  "Australia",
                        "job_count":  20,
                        "result_limit": 20,
                    },
                    headers=_HEADERS,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
                for job in data.get("jobs", []):
                    job_id = str(job.get("id_icims") or job.get("job_id") or "")
                    if not job_id or job_id in seen:
                        continue
                    seen.add(job_id)
                    cat = (job.get("business_category") or "").lower()
                    company = "Amazon Web Services (AWS)" if ("aws" in cat or "cloud" in cat) else "Amazon"
                    jobs.append({
                        "title":       job.get("title", ""),
                        "company":     company,
                        "location":    job.get("normalized_location", "Australia"),
                        "url":         f"https://www.amazon.jobs/en/jobs/{job_id}",
                        "summary":     job.get("description_short", ""),
                        "date_posted": job.get("posted_date", ""),
                        "source":      "CompanyCareers",
                    })
                time.sleep(1.5)
            except Exception as exc:
                print(f"[CompanyCareers] Amazon query '{q}': {exc}")

        print(f"[CompanyCareers] Amazon/AWS → {len(jobs)} jobs")
        return jobs
