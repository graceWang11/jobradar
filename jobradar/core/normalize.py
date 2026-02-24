"""Normalize raw job data into JobListing objects and tag roles."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List

from jobradar.core.models import JobListing


# ── Location aliases ──────────────────────────────────────────────────────────

_LOCATION_MAP: Dict[str, str] = {
    "adelaide": "Adelaide",
    "sa": "Adelaide",
    "south australia": "Adelaide",
    "melbourne": "Melbourne",
    "vic": "Melbourne",
    "victoria": "Melbourne",
    "remote": "Remote",
    "hybrid": "Hybrid",
    "australia": "Australia",
}


def _normalize_location(raw: str) -> str:
    key = raw.strip().lower()
    for fragment, canonical in _LOCATION_MAP.items():
        if fragment in key:
            return canonical
    return raw.strip().title()


# ── Tagging ───────────────────────────────────────────────────────────────────

_LEVEL_KEYWORDS = {
    "Graduate": ["graduate", "grad "],
    "Junior": ["junior", "jr "],
    "Entry": ["entry", "entry-level", "entry level"],
    "Associate": ["associate"],
    "EarlyCareer": ["early career", "cadet"],
}

_ROLE_KEYWORDS = {
    "SWE": [
        "software engineer", "software developer", "backend", "frontend",
        "full stack", "fullstack", "web developer", "devops", "platform engineer",
    ],
    "Architecture": [
        "architect",
    ],
    "Program": [
        "graduate program", "graduate programme", "rotation program",
        "rotational", "internship", "cadet program",
    ],
}


def _tag_listing(title: str, summary: str) -> List[str]:
    combined = f"{title} {summary}".lower()
    tags: List[str] = []

    for tag, phrases in _LEVEL_KEYWORDS.items():
        if any(p in combined for p in phrases):
            tags.append(tag)

    for tag, phrases in _ROLE_KEYWORDS.items():
        if any(p in combined for p in phrases):
            tags.append(tag)

    return tags


# ── Public API ────────────────────────────────────────────────────────────────

def normalize(raw: Dict[str, Any], source: str) -> JobListing:
    """Convert a raw job dict (from any connector) to a JobListing."""
    title = _clean_text(raw.get("title", "Unknown"))
    company = _clean_text(raw.get("company", "Unknown"))
    location = _normalize_location(raw.get("location", ""))
    url = raw.get("url", "").strip()
    summary = _clean_text(raw.get("summary", ""))
    tags = _tag_listing(title, summary)

    return JobListing(
        source=source,
        title=title,
        company=company,
        location=location,
        url=url,
        date_found=date.today(),
        summary=summary[:500],
        tags=tags,
    )


def normalize_many(raws: List[Dict[str, Any]], source: str) -> List[JobListing]:
    results = []
    for r in raws:
        try:
            results.append(normalize(r, source))
        except Exception as exc:
            print(f"[normalize] Skipping bad record from {source}: {exc}")
    return results


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()
