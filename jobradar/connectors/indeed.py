"""Indeed.com.au connector — HTML scraper with browser headers."""

from __future__ import annotations

import re
import time
from typing import List

import requests
from bs4 import BeautifulSoup

from jobradar.connectors.base import BaseConnector

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_BASE_URL = "https://au.indeed.com/jobs"

_QUERIES = [
    ("junior software engineer",    "{city}"),
    ("graduate developer",          "{city}"),
    ("associate software engineer", "{city}"),
    ("entry level software",        "{city}"),
    ("graduate technology program", "{city}"),
]


class IndeedConnector(BaseConnector):
    """Scrapes au.indeed.com for junior/grad tech roles."""

    rate_limit_seconds: float = 3.0

    def fetch(self, locations: list[str], keywords: list[str]) -> list[dict]:
        seen: set[str] = set()
        all_jobs: list[dict] = []

        for city in locations:
            for query_template, loc_template in _QUERIES:
                loc = loc_template.format(city=city)
                jobs = self._fetch_page(query_template, loc, seen)
                all_jobs.extend(jobs)
                time.sleep(self.rate_limit_seconds)

        print(f"[Indeed] Total → {len(all_jobs)} jobs")
        return all_jobs

    def _fetch_page(self, query: str, location: str, seen: set[str]) -> list[dict]:
        jobs: list[dict] = []
        try:
            resp = requests.get(
                _BASE_URL,
                params={
                    "q":       query,
                    "l":       location,
                    "fromage": 1,       # posted in last 1 day
                    "sort":    "date",
                },
                headers=_HEADERS,
                timeout=15,
            )
            if resp.status_code == 403:
                print(f"[Indeed] 403 blocked for '{query}' in {location} — skipping")
                return []
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.find_all("div", class_=re.compile(r"job_seen_beacon|jobsearch-SerpJobCard"))
            if not cards:
                # Try newer card structure
                cards = soup.find_all("li", class_=re.compile(r"css-.*jobcard|resultContent"))

            for card in cards:
                # Title
                title_tag = card.find("h2", class_=re.compile(r"jobTitle")) or card.find("a", {"data-jk": True})
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)

                # URL
                link = card.find("a", href=re.compile(r"/rc/clk|/pagead/clk"))
                if not link:
                    link = card.find("a", {"data-jk": True})
                href = link.get("href", "") if link else ""
                url  = f"https://au.indeed.com{href}" if href.startswith("/") else href
                job_id = re.search(r"jk=([a-f0-9]+)", url)
                uid = job_id.group(1) if job_id else url
                if not uid or uid in seen:
                    continue
                seen.add(uid)

                # Company
                company_tag = card.find("span", {"data-testid": "company-name"}) or \
                              card.find("span", class_=re.compile(r"companyName"))
                company = company_tag.get_text(strip=True) if company_tag else ""

                # Location
                loc_tag = card.find("div", {"data-testid": "text-location"}) or \
                          card.find("div", class_=re.compile(r"companyLocation"))
                loc = loc_tag.get_text(strip=True) if loc_tag else location

                # Summary
                snippet = card.find("div", class_=re.compile(r"job-snippet|summary"))
                summary = snippet.get_text(strip=True) if snippet else ""

                jobs.append({
                    "title":       title,
                    "company":     company,
                    "location":    loc,
                    "url":         url,
                    "summary":     summary,
                    "date_posted": "",
                    "source":      "Indeed",
                })

        except Exception as exc:
            print(f"[Indeed] Error '{query}' {location}: {exc}")

        return jobs
