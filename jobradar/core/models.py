"""Core data model for a normalised job listing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import List


@dataclass
class JobListing:
    """A single normalised job listing from any source."""

    source: str
    title: str
    company: str
    location: str
    url: str
    date_found: date
    summary: str = ""
    tags: List[str] = field(default_factory=list)
    visa_score: int = -1       # -1 = not yet scored; 0–5 once scored
    visa_reason: str = ""
    hash_id: str = ""

    def __post_init__(self) -> None:
        if not self.hash_id:
            self.hash_id = self._compute_hash()

    def _compute_hash(self) -> str:
        """Stable identifier based on URL (primary) + title/company/location (fallback)."""
        key = self.url.strip().lower() or f"{self.title}|{self.company}|{self.location}".lower()
        return hashlib.md5(key.encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
            "date_found": self.date_found.isoformat(),
            "summary": self.summary,
            "tags": "|".join(self.tags),
            "visa_score": self.visa_score,
            "visa_reason": self.visa_reason,
            "hash_id": self.hash_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JobListing":
        tags = d.get("tags", "") or ""
        if isinstance(tags, str):
            tags = [t for t in tags.split("|") if t]
        elif not isinstance(tags, list):
            tags = []
        return cls(
            source=d["source"],
            title=d["title"],
            company=d["company"],
            location=d["location"],
            url=d["url"],
            date_found=date.fromisoformat(d["date_found"]),
            summary=d.get("summary", ""),
            tags=tags,
            visa_score=int(d.get("visa_score", -1)),
            visa_reason=d.get("visa_reason", ""),
            hash_id=d.get("hash_id", ""),
        )
