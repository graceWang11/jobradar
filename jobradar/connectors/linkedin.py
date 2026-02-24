"""LinkedIn connector – public job search (no login required).

LinkedIn renders job cards server-side for public search pages.
No authentication needed for the first page of results (~60 jobs).

Card structure (verified):
  Container : div.base-card  (also has class base-search-card job-search-card)
  Title     : h3.base-search-card__title
  Company   : h4.base-search-card__subtitle  (text or nested <a>)
  Location  : span.job-search-card__location
  Date      : time.job-search-card__listdate  [datetime attribute]
  URL       : a.base-card__full-link  href  (strip tracking params)

Search URL:
  https://www.linkedin.com/jobs/search/?keywords=<query>&location=<loc>&f_TPR=r86400
  f_TPR=r86400  → posted in the last 24 hours
"""

from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from jobradar.connectors.base import BaseConnector


_BASE_URL = "https://www.linkedin.com/jobs/search/"

_LOCATION_QUERIES: Dict[str, str] = {
    "Adelaide": "Adelaide, South Australia, Australia",
    "Melbourne": "Melbourne, Victoria, Australia",
}

_SEARCH_TERMS = [
    "junior software engineer",
    "graduate developer",
    "graduate software engineer",
    "junior developer",
    "associate software engineer",
    "entry level software developer",
    "graduate program technology",
]

_TRACKING_PARAM_RE = re.compile(r"\?.*")


class LinkedInConnector(BaseConnector):
    name = "LinkedIn"
    rate_limit_seconds = 3.0   # be polite to LinkedIn

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        jobs: List[Dict[str, Any]] = []

        for location in locations:
            loc_query = _LOCATION_QUERIES.get(location, location)
            for term in _SEARCH_TERMS:
                try:
                    results = self._fetch_page(term, loc_query, location)
                    jobs.extend(results)
                    print(f"[LinkedIn] {location} / '{term}' → {len(results)} jobs")
                except Exception as exc:
                    print(f"[LinkedIn] Error {location}/{term}: {exc}")
                self._sleep()

        return jobs

    def _fetch_page(
        self, keywords: str, location_query: str, location_label: str
    ) -> List[Dict[str, Any]]:
        params = {
            "keywords": keywords,
            "location": location_query,
            "f_TPR": "r86400",      # last 24 hours
            "f_JT": "F,C,T,P",     # Full-time, Contract, Temporary, Part-time
        }
        url = f"{_BASE_URL}?{urlencode(params)}"
        resp = requests.get(url, headers=self._HEADERS, timeout=15)
        resp.raise_for_status()
        return self._parse(resp.text, location_label)

    def _parse(self, html: str, location_label: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        cards = soup.find_all("div", class_="base-card")

        for card in cards:
            try:
                # Title
                title_tag = card.select_one("h3.base-search-card__title")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)

                # URL — strip all tracking query params
                link = card.select_one("a.base-card__full-link")
                href = link.get("href", "") if link else ""
                url = _TRACKING_PARAM_RE.sub("", href) if href else ""

                # Company
                company_tag = card.select_one("h4.base-search-card__subtitle")
                company = company_tag.get_text(strip=True) if company_tag else "Unknown"

                # Location
                loc_tag = card.select_one("span.job-search-card__location")
                raw_loc = loc_tag.get_text(strip=True) if loc_tag else location_label

                # Date posted (as summary placeholder — no snippet on public cards)
                date_tag = card.select_one("time.job-search-card__listdate")
                date_str = date_tag.get("datetime", "") if date_tag else ""
                summary = f"Posted: {date_str}" if date_str else ""

                if not title or not url:
                    continue

                jobs.append(
                    {
                        "title": title,
                        "company": company,
                        "location": raw_loc or location_label,
                        "url": url,
                        "summary": summary,
                    }
                )
            except Exception:
                continue

        return jobs
