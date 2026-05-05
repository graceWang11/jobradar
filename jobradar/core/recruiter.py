"""Recruiter contact lookup — named contacts via Brave Search (primary) or Google CSE.

Primary: Brave Search API (2,000 queries/month free)
  https://api.search.brave.com/app/keys → grab BRAVE_API_KEY
  Add to .env: BRAVE_API_KEY=your_key

Secondary: Google Programmable Search Engine (100 queries/day free)
  See README for the 6-step setup → GOOGLE_CSE_ID + GOOGLE_CSE_API_KEY in .env

Each unique company = 1 query. Results cached for cache_ttl_days (default 7)
in data/recruiter_cache.json regardless of provider.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import requests

from jobradar.core.models import JobListing

_CANDIDATE_NAME = "Laiya"
_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "recruiter_cache.json"
_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _load_cache() -> Dict[str, Any]:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _evict_expired(cache: Dict[str, Any], ttl_days: int) -> Dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    return {
        k: v for k, v in cache.items()
        if datetime.fromisoformat(v["fetched_at"]).replace(tzinfo=timezone.utc) > cutoff
    }


# ── LinkedIn result parsing (shared across providers) ─────────────────────────

def _parse_linkedin_result(
    page_title: str, link: str
) -> Optional[Dict[str, str]]:
    """Extract name/title from a search result pointing at a LinkedIn /in/ profile.

    LinkedIn profile titles follow "First Last - Title - Company | LinkedIn" or
    "First Last - Title at Company | LinkedIn".
    """
    if "linkedin.com/in/" not in link:
        return None
    if not page_title:
        return None
    m = re.match(r'^([^|–\-]+?)(?:\s*[-–]\s*(.+?))?\s*\|\s*LinkedIn', page_title)
    if not m:
        return None
    name = m.group(1).strip()
    title = (m.group(2) or "").strip()
    if len(name.split()) < 2:
        return None
    if title and not re.search(
        r'recruit|talent|hire|hiring|\bhr\b|human resource|people (?:ops|partner)|'
        r'staffing|acquisition',
        title, re.I,
    ):
        return None
    return {"name": name, "title": title, "linkedin_url": link}


def _build_query(company: str) -> str:
    return (
        f'site:linkedin.com/in/ "{company}" '
        f'("recruiter" OR "talent acquisition" OR "people partner")'
    )


# ── Brave Search (primary) ────────────────────────────────────────────────────

def brave_search(query: str, api_key: str, count: int = 10, country: str = "au") -> List[Dict]:
    """Wrap Brave Search API. Returns the raw `web.results` list (or [])."""
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": max(1, min(20, count)), "country": country}
    try:
        resp = requests.get(_BRAVE_ENDPOINT, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[recruiter] Brave Search error: {exc}")
        return []
    return (data.get("web") or {}).get("results", []) or []


def _query_brave(company: str, api_key: str, max_contacts: int) -> List[Dict[str, str]]:
    results = brave_search(_build_query(company), api_key, count=min(20, max_contacts * 4))
    contacts: List[Dict[str, str]] = []
    for r in results:
        contact = _parse_linkedin_result(r.get("title", ""), r.get("url", ""))
        if contact:
            contacts.append(contact)
        if len(contacts) >= max_contacts:
            break
    return contacts


# ── Google CSE (secondary) ────────────────────────────────────────────────────

def _query_google_cse(
    company: str, api_key: str, cx: str, max_contacts: int
) -> List[Dict[str, str]]:
    params = {
        "key": api_key, "cx": cx, "q": _build_query(company),
        "num": min(10, max_contacts * 3),
    }
    try:
        resp = requests.get(_CSE_ENDPOINT, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[recruiter] Google CSE error for '{company}': {exc}")
        return []

    contacts: List[Dict[str, str]] = []
    for item in data.get("items", []):
        contact = _parse_linkedin_result(item.get("title", ""), item.get("link", ""))
        if contact:
            contacts.append(contact)
        if len(contacts) >= max_contacts:
            break
    return contacts


# ── Public lookup ─────────────────────────────────────────────────────────────

def recruiter_search_url(company: str) -> str:
    """Fallback LinkedIn people-search URL for recruiters at *company*."""
    query = f'"{company}" recruiter OR "talent acquisition"'
    return (
        f"https://www.linkedin.com/search/results/people/"
        f"?keywords={quote_plus(query)}"
    )


def _resolve_provider(rec_cfg: dict) -> Optional[str]:
    """Pick provider based on config + available env keys. None = no lookup."""
    provider = (rec_cfg.get("provider") or "brave").lower()
    if provider == "brave" and os.environ.get("BRAVE_API_KEY"):
        return "brave"
    if provider == "google_cse" and (
        os.environ.get("GOOGLE_CSE_API_KEY") and os.environ.get("GOOGLE_CSE_ID")
    ):
        return "google_cse"
    if provider == "none":
        return None
    return None


def find_contacts(company: str, cfg: dict) -> List[Dict[str, str]]:
    """Return up to max_contacts named recruiter dicts for *company*.

    Returns [] if no provider is configured — caller should fall back to URL.
    """
    rec_cfg = cfg.get("recruiter_lookup", {})
    if not rec_cfg.get("enabled", True):
        return []

    provider = _resolve_provider(rec_cfg)
    if not provider:
        return []

    ttl_days = int(rec_cfg.get("cache_ttl_days", 7))
    max_contacts = int(rec_cfg.get("max_contacts_per_company", 3))

    cache = _evict_expired(_load_cache(), ttl_days)
    if company in cache:
        return cache[company]["contacts"]

    if provider == "brave":
        contacts = _query_brave(
            company, os.environ["BRAVE_API_KEY"], max_contacts,
        )
    else:  # google_cse
        contacts = _query_google_cse(
            company,
            os.environ["GOOGLE_CSE_API_KEY"],
            os.environ["GOOGLE_CSE_ID"],
            max_contacts,
        )

    cache[company] = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "contacts": contacts,
    }
    _save_cache(cache)
    return contacts


# ── Outreach message ──────────────────────────────────────────────────────────

def _first_name(full_name: str) -> str:
    return full_name.split()[0] if full_name else ""


def generate_outreach_msg(job: JobListing, recruiter_name: str = "") -> str:
    """Return a ≤300-char LinkedIn connection-request message for *job*."""
    skills_list = [s.strip() for s in job.match_skills.split(",") if s.strip()][:3]
    skills_str = ", ".join(skills_list) if skills_list else "software development"
    title = job.title if len(job.title) <= 55 else job.title[:52] + "…"
    company = job.company if len(job.company) <= 35 else job.company[:32] + "…"
    greeting = f"Hi {_first_name(recruiter_name)}" if recruiter_name else "Hi"
    msg = (
        f"{greeting}, I'm interested in the {title} role at {company}. "
        f"I have {skills_str} experience and hold a 485 graduate visa "
        f"(full AU work rights). Would love to connect! — {_CANDIDATE_NAME}"
    )
    return msg[:300]


# ── Pipeline entry point ──────────────────────────────────────────────────────

def enrich_all(jobs: List[JobListing], cfg: dict) -> None:
    """Attach recruiter contacts, search URL, and outreach msg to every job."""
    rec_cfg = cfg.get("recruiter_lookup", {})
    provider = _resolve_provider(rec_cfg)

    if not provider:
        configured = (rec_cfg.get("provider") or "brave").lower()
        env_var = "BRAVE_API_KEY" if configured == "brave" else "GOOGLE_CSE_ID"
        print(
            f"[recruiter] no {env_var} set "
            f"— falling back to search-URL mode"
        )
    else:
        print(f"[recruiter] provider: {provider}")

    # Brave free tier: ~1 query/sec. Google CSE: comfortable at 0.2s.
    sleep_s = 1.1 if provider == "brave" else (0.2 if provider == "google_cse" else 0)

    contacts_by_company: Dict[str, List[Dict[str, str]]] = {}
    for job in jobs:
        company = job.company
        if company in contacts_by_company:
            continue
        contacts_by_company[company] = find_contacts(company, cfg)
        if sleep_s:
            time.sleep(sleep_s)

    for job in jobs:
        contacts = contacts_by_company.get(job.company, [])
        job.recruiter_contacts = contacts
        recruiter_name = contacts[0]["name"] if contacts else ""
        job.outreach_msg = generate_outreach_msg(job, recruiter_name)
        job.recruiter_url = recruiter_search_url(job.company)

    if provider:
        hits = sum(1 for v in contacts_by_company.values() if v)
        total = len(contacts_by_company)
        print(f"[recruiter] named contacts found for {hits}/{total} unique companies")
