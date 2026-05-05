"""Workday ATS connector.

Polls Workday career sites for AU junior/grad tech roles via the internal
CXS JSON API that each company's career page uses in the browser.

API: POST https://{subdomain}.wd{version}.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs
Body: {"appliedFacets": {}, "limit": 50, "offset": 0, "searchText": ""}
No auth required for external (public) job boards.

Note: each company's tenant name and board identifier must be verified manually
by checking their career site URL. Companies that return 422 use a different
Workday version or board configuration that hasn't been confirmed yet.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

from jobradar.connectors.base import BaseConnector

_BASELINE_FILE = Path(__file__).resolve().parents[2] / "data" / "workday_baseline.json"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# (display_name, subdomain, wd_version, tenant, board)
# All entries verified to return HTTP 200 from the CXS API.
# Add new entries only after live-testing: POST returns {"total": N, "jobPostings": [...]}
_WORKDAY_BOARDS: List[Tuple[str, str, str, str, str]] = [
    ("NAB",       "nab",      "3", "nab",      "NAB_Careers"),
    ("Telstra",   "telstra",  "3", "telstra",  "Telstra_Careers"),
    ("REA Group", "reagroup", "3", "reagroup", "reacareers"),
    # ANZ, CBA, BHP, AGL return 422 — board paths not yet confirmed.
    # Uncomment after verifying the correct board path from their career site.
    # ("ANZ",     "anz",     "3", "anz",     "???"),
    # ("CBA",     "cba",     "3", "cba",     "???"),
    # ("BHP",     "bhp",     "3", "bhp",     "???"),
    # ("AGL",     "agl",     "3", "agl",     "???"),
]

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

_PAGE_SIZE = 20  # Workday CXS rejects limit > 20 with HTTP 400


def _load_baseline() -> Dict[str, int]:
    if not _BASELINE_FILE.exists():
        return {}
    try:
        return json.loads(_BASELINE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_baseline(baseline: Dict[str, int]) -> None:
    try:
        _BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _BASELINE_FILE.write_text(json.dumps(baseline, indent=2, sort_keys=True))
    except OSError as exc:
        print(f"[Workday] baseline write failed: {exc}")


def _verify_tenants_alive() -> None:
    """Ping each tenant with a tiny POST and warn on persistent 4xx — surfaces
    silently-broken tenants like NAB/Telstra before they disappear from output
    for weeks unnoticed."""
    for company_name, subdomain, wd_ver, tenant, board in _WORKDAY_BOARDS:
        url = (
            f"https://{subdomain}.wd{wd_ver}.myworkdayjobs.com"
            f"/wday/cxs/{tenant}/{board}/jobs"
        )
        try:
            resp = requests.post(
                url, headers=_HEADERS,
                json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
                timeout=10,
            )
            if 400 <= resp.status_code < 500:
                print(f"[Workday] WARNING: {company_name} tenant probe HTTP {resp.status_code} — config may be stale")
        except requests.RequestException as exc:
            print(f"[Workday] WARNING: {company_name} tenant probe failed: {exc}")


class WorkdayConnector(BaseConnector):
    name = "Workday"
    rate_limit_seconds = 2.0

    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        _verify_tenants_alive()
        baseline = _load_baseline()
        all_jobs: List[Dict[str, Any]] = []
        for company_name, subdomain, wd_ver, tenant, board in _WORKDAY_BOARDS:
            try:
                jobs = self._fetch_board(company_name, subdomain, wd_ver, tenant, board)
                if jobs:
                    print(f"[Workday] {company_name} → {len(jobs)} AU grad/junior jobs")
                all_jobs.extend(jobs)

                prior = baseline.get(company_name, 0)
                if prior >= 10 and len(jobs) == 0:
                    print(f"[Workday] WARNING: {company_name} returned 0 jobs (baseline {prior}) — check tenant config")
                baseline[company_name] = max(prior, len(jobs))
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else "?"
                print(f"[Workday] {company_name}: HTTP {code}")
            except Exception as exc:
                print(f"[Workday] {company_name}: {exc}")
            time.sleep(self.rate_limit_seconds)

        _save_baseline(baseline)
        return all_jobs

    def _fetch_board(
        self,
        company_name: str,
        subdomain: str,
        wd_ver: str,
        tenant: str,
        board: str,
    ) -> List[Dict[str, Any]]:
        base_url = (
            f"https://{subdomain}.wd{wd_ver}.myworkdayjobs.com"
            f"/wday/cxs/{tenant}/{board}/jobs"
        )
        job_base = f"https://{subdomain}.wd{wd_ver}.myworkdayjobs.com"

        offset = 0
        collected: List[Dict[str, Any]] = []

        while True:
            resp = requests.post(
                base_url,
                headers=_HEADERS,
                json={"appliedFacets": {}, "limit": _PAGE_SIZE, "offset": offset, "searchText": ""},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            postings = data.get("jobPostings", [])
            if not postings:
                break

            collected.extend(
                self._parse(postings, company_name, job_base)
            )

            total = data.get("total", 0)
            offset += _PAGE_SIZE
            if offset >= total:
                break

            time.sleep(1.0)

        return collected

    def _parse(
        self, items: List[Dict], company_name: str, job_base: str
    ) -> List[Dict[str, Any]]:
        jobs = []
        for item in items:
            title = (item.get("title") or "").strip()
            if not title:
                continue

            location_raw = (item.get("locationsText") or "").strip()

            # AU jobs only
            if not _AU_LOCATION.search(location_raw):
                continue

            # Grad/junior titles only
            if not _LEVEL_PATTERN.search(title):
                continue

            external_path = (item.get("externalPath") or "").strip()
            url = f"{job_base}{external_path}" if external_path else ""

            posted = (item.get("postedOn") or "").strip()
            summary = f"{location_raw} · {posted}".strip(" ·")

            jobs.append({
                "title":    title,
                "company":  company_name,
                "location": location_raw or "Australia",
                "url":      url,
                "summary":  summary,
            })
        return jobs
