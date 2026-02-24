"""Jora connector – job aggregator with clean HTML listings.

Real page structure (verified):
  Cards  : div.job-card
  Title  : h2.job-title > a.job-link  (take first/desktop link)
  URL    : a.job-link href, strip query params
  Company: span.company  (or first [class*=company] span)
  Location: span.location (or first [class*=location] span)
  Summary: div.abstract  (or [class*=abstract])

Search URL: https://au.jora.com/jobs?q=<query>&l=<location>
"""

from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from jobradar.connectors.base import BaseConnector


_BASE_URL = "https://au.jora.com/jobs"

_LOCATION_QUERIES: Dict[str, str] = {
    "Adelaide": "Adelaide, SA",
    "Melbourne": "Melbourne, VIC",
}

_SEARCH_TERMS = [
    "junior software engineer",
    "graduate developer",
    "entry level software",
    "associate software engineer",
    "graduate software program",
]

_URL_PARAM_RE = re.compile(r"\?.*")


class JoraConnector(BaseConnector):
    name = "Jora"
    rate_limit_seconds = 2.0

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        jobs: List[Dict[str, Any]] = []

        for location in locations:
            loc_query = _LOCATION_QUERIES.get(location, location)
            for term in _SEARCH_TERMS:
                try:
                    results = self._fetch_page(term, loc_query, location)
                    jobs.extend(results)
                    print(f"[Jora] {location} / '{term}' → {len(results)} jobs")
                except Exception as exc:
                    print(f"[Jora] Error {location}/{term}: {exc}")
                self._sleep()

        return jobs

    def _fetch_page(
        self, query: str, location_query: str, location_label: str
    ) -> List[Dict[str, Any]]:
        params = {"q": query, "l": location_query}
        url = f"{_BASE_URL}?{urlencode(params)}"
        resp = requests.get(url, headers=self._HEADERS, timeout=15)
        resp.raise_for_status()
        return self._parse(resp.text, location_label)

    def _parse(self, html: str, location_label: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        cards = soup.select("div.job-card")

        for card in cards:
            try:
                # Title: first desktop link inside h2.job-title
                title_link = card.select_one("h2.job-title a.job-link")
                if not title_link:
                    title_link = card.select_one("h2.job-title a")
                if not title_link:
                    continue

                title = title_link.get_text(strip=True)
                if not title:
                    continue

                # URL: strip all tracking query params
                href = title_link.get("href", "")
                clean_href = _URL_PARAM_RE.sub("", href)
                url = (
                    clean_href
                    if clean_href.startswith("http")
                    else f"https://au.jora.com{clean_href}"
                )

                # Company
                company_tag = (
                    card.select_one("span.company")
                    or card.select_one("a.company-link")
                    or card.select_one("[class*=company]")
                )
                company = company_tag.get_text(strip=True) if company_tag else "Unknown"

                # Location
                loc_tag = (
                    card.select_one("span.location")
                    or card.select_one("[class*=location]")
                )
                raw_loc = loc_tag.get_text(strip=True) if loc_tag else location_label

                # Summary / abstract
                summary_tag = (
                    card.select_one("div.abstract")
                    or card.select_one("[class*=abstract]")
                    or card.select_one("[class*=snippet]")
                )
                summary = summary_tag.get_text(strip=True) if summary_tag else ""

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
