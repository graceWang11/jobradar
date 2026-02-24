"""GradConnection (now SEEK Grad) connector.

IMPORTANT constraints discovered from real HTML:
  - Location and discipline URL parameters are JavaScript-driven and IGNORED
    by the server — we get the same 20 server-rendered cards regardless.
  - Cards contain NO location data — the box-demographics div is empty.
  - We take what is visible, apply strict title-level IT relevance filtering,
    and mark location as "Australia" since location is unknown.

Card structure (verified):
  Container : div.campaign-box
  Title link : a.box-header-title  (href + h3 text)
  Company    : p.box-header-para inside div.box-employer-name
  Location   : NOT available — set to "Australia"
  Summary    : div.box-description p (first paragraph)
"""

from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from jobradar.connectors.base import BaseConnector


_BASE_URL = "https://au.gradconnection.com/jobs/"

# These keywords in the title signal an IT-relevant role.
# Used to pre-filter at connector level so only relevant cards are returned.
_IT_TITLE_KEYWORDS = [
    "software", "developer", "engineer", "engineering",
    "data", "cyber", "security", "network", "cloud",
    "devops", "platform", "backend", "frontend", "full stack",
    "fullstack", "web", "mobile", "app", "technology", "tech",
    "it ", " it", "information technology",
    "computer", "systems", "graduate program", "technology graduate",
    "internship", "cadet", "rotational", "rotation",
    "architect",
]

_SEARCH_TERMS = [
    "software",
    "technology graduate",
    "junior developer",
]


class GradConnectionConnector(BaseConnector):
    name = "GradConnection"
    rate_limit_seconds = 2.0

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        jobs: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()

        for term in _SEARCH_TERMS:
            try:
                raw = self._fetch_page(term)
                for job in raw:
                    if job["url"] not in seen_urls:
                        seen_urls.add(job["url"])
                        jobs.append(job)
                print(f"[GradConnection] '{term}' → {len(raw)} parsed, {len(seen_urls)} unique so far")
            except Exception as exc:
                print(f"[GradConnection] Error fetching '{term}': {exc}")
            self._sleep()

        print(f"[GradConnection] Total unique: {len(jobs)} (location=Australia, filter at pipeline)")
        return jobs

    def _fetch_page(self, keyword: str) -> List[Dict[str, Any]]:
        params = {"keyword": keyword}
        url = f"{_BASE_URL}?{urlencode(params)}"
        resp = requests.get(url, headers=self._HEADERS, timeout=15)
        resp.raise_for_status()
        return self._parse(resp.text)

    def _parse(self, html: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        cards = soup.find_all("div", class_="campaign-box")

        for card in cards:
            try:
                # Title and URL
                title_a = card.select_one("a.box-header-title")
                if not title_a:
                    continue
                title = title_a.get_text(strip=True)
                href = title_a.get("href", "")
                url = (
                    href
                    if href.startswith("http")
                    else f"https://au.gradconnection.com{href}"
                )

                # Pre-filter: only keep IT-relevant titles at this stage
                title_lower = title.lower()
                if not any(kw in title_lower for kw in _IT_TITLE_KEYWORDS):
                    continue

                # Company
                company_p = card.select_one("div.box-employer-name p.box-header-para")
                company = company_p.get_text(strip=True) if company_p else "Unknown"

                # Summary (inside box-description if available)
                desc_div = card.select_one("div.job-description, div.box-description")
                summary = desc_div.get_text(strip=True)[:300] if desc_div else ""

                # Location: NOT available in HTML — mark explicitly
                jobs.append(
                    {
                        "title": title,
                        "company": company,
                        "location": "Australia",   # real location unknown at list level
                        "url": url,
                        "summary": summary,
                    }
                )
            except Exception:
                continue

        return jobs
