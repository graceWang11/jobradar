"""Recruiter contact lookup — named contacts via Google CSE, fallback to search URL.

Setup (one-time):
  1. Go to https://programmablesearchengine.google.com/ → New search engine
  2. Set "Search the entire web" = ON, note the Search engine ID (cx)
  3. Go to https://console.cloud.google.com/ → APIs & Services → Credentials
     → Create credentials → API key (restrict to Custom Search API)
  4. Add to .env:
       GOOGLE_CSE_ID=your_cx_value
       GOOGLE_CSE_API_KEY=your_api_key

Free tier: 100 queries/day. Each unique company = 1 query. Results cached for
cache_ttl_days (default 7) in data/recruiter_cache.json.
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


# ── Google CSE ────────────────────────────────────────────────────────────────

def _parse_linkedin_result(item: Dict) -> Optional[Dict[str, str]]:
    """Extract name/title from a Google CSE result for a LinkedIn /in/ profile."""
    link = item.get("link", "")
    if "linkedin.com/in/" not in link:
        return None
    page_title = item.get("title", "")
    # "First Last - Title at Company | LinkedIn"
    m = re.match(r'^([^|–\-]+?)(?:\s*[-–]\s*(.+?))?\s*\|\s*LinkedIn', page_title)
    if not m:
        return None
    name = m.group(1).strip()
    title = (m.group(2) or "").strip()
    if len(name.split()) < 2:
        return None
    # Must look like a recruiter/talent/HR role
    if title and not re.search(
        r'recruit|talent|hire|hiring|\bhr\b|human resource|people ops|staffing|acquisition',
        title, re.I,
    ):
        return None
    return {"name": name, "title": title, "linkedin_url": link}


def _query_google_cse(
    company: str, api_key: str, cx: str, max_contacts: int
) -> List[Dict[str, str]]:
    query = (
        f'site:linkedin.com/in/ "{company}" '
        f'("recruiter" OR "talent acquisition" OR "talent partner")'
    )
    params = {"key": api_key, "cx": cx, "q": query, "num": min(10, max_contacts * 3)}
    try:
        resp = requests.get(_CSE_ENDPOINT, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[recruiter] Google CSE error for '{company}': {exc}")
        return []

    contacts: List[Dict[str, str]] = []
    for item in data.get("items", []):
        contact = _parse_linkedin_result(item)
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


def find_contacts(company: str, cfg: dict) -> List[Dict[str, str]]:
    """Return up to max_contacts named recruiter dicts for *company*.

    Returns [] if CSE not configured — caller should fall back to search URL.
    """
    rec_cfg = cfg.get("recruiter_lookup", {})
    if not rec_cfg.get("enabled", True):
        return []

    api_key = os.environ.get("GOOGLE_CSE_API_KEY", "")
    cx = os.environ.get("GOOGLE_CSE_ID", "")
    if not api_key or not cx:
        return []

    ttl_days = int(rec_cfg.get("cache_ttl_days", 7))
    max_contacts = int(rec_cfg.get("max_contacts_per_company", 3))

    cache = _evict_expired(_load_cache(), ttl_days)

    if company in cache:
        return cache[company]["contacts"]

    contacts = _query_google_cse(company, api_key, cx, max_contacts)
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
    api_key = os.environ.get("GOOGLE_CSE_API_KEY", "")
    cx = os.environ.get("GOOGLE_CSE_ID", "")
    use_cse = bool(api_key and cx)

    if not use_cse:
        print("[recruiter] no GOOGLE_CSE_ID set — falling back to search-URL mode")

    # One lookup per unique company
    contacts_by_company: Dict[str, List[Dict[str, str]]] = {}
    for job in jobs:
        company = job.company
        if company in contacts_by_company:
            continue
        contacts_by_company[company] = find_contacts(company, cfg)
        if use_cse:
            time.sleep(0.2)  # stay well within 100 req/day

    for job in jobs:
        contacts = contacts_by_company.get(job.company, [])
        job.recruiter_contacts = contacts
        recruiter_name = contacts[0]["name"] if contacts else ""
        job.outreach_msg = generate_outreach_msg(job, recruiter_name)
        job.recruiter_url = recruiter_search_url(job.company)
