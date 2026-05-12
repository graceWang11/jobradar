"""Maps the pipeline's CSV output into the frontend Job contract.

The HTTP layer never triggers the live aggregator — its multi-connector fetch
takes minutes per run. Instead the CLI pipeline (run on cron) drops a CSV under
output/jobs_YYYY-MM-DD.csv, and POST /api/jobs/match reads + filters the most
recent one. ?refresh=1 re-checks the CSV mtime and recomputes.

Salaries are reported in AUD as found in the listing; no FX. Most AU listings
have no salary field, so (0, 0) is the common case.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, time, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from jobradar.api.schemas import Job, UserPreferences
from jobradar.core.models import JobListing

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"

_REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)
_HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)
_INTERN_RE = re.compile(r"\bintern(?:ship)?\b", re.IGNORECASE)
_LEAD_RE = re.compile(r"\b(?:lead|principal|staff)\b", re.IGNORECASE)
_SENIOR_RE = re.compile(r"\bsenior\b", re.IGNORECASE)
_MID_RE = re.compile(r"\b(?:mid[- ]level|experienced)\b", re.IGNORECASE)
_JUNIOR_RE = re.compile(
    r"\b(?:graduate|grad|junior|entry[- ]level|associate)\b", re.IGNORECASE
)

_SALARY_K_RE = re.compile(
    r"\$?\s*(\d{2,3})\s*k\s*(?:-|–|to)\s*\$?\s*(\d{2,3})\s*k", re.IGNORECASE
)
_SALARY_FULL_RE = re.compile(
    r"\$\s*(\d{2,3})[,]?(\d{3})\s*(?:-|–|to)\s*\$?\s*(\d{2,3})[,]?(\d{3})",
    re.IGNORECASE,
)

_SOURCE_ENUM = {
    "linkedin": "LinkedIn",
    "indeed": "Indeed",
    "greenhouse": "Greenhouse",
    "lever": "Lever",
}


def latest_csv() -> Optional[Path]:
    files = sorted(OUTPUT_DIR.glob("jobs_*.csv"), reverse=True)
    return files[0] if files else None


def csv_mtime(path: Path) -> float:
    return path.stat().st_mtime


def load_listings(path: Path) -> List[JobListing]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return [JobListing.from_dict(row) for row in df.to_dict(orient="records")]


def _classify_type(text: str) -> str:
    if _REMOTE_RE.search(text):
        return "remote"
    if _HYBRID_RE.search(text):
        return "hybrid"
    return "onsite"


def _classify_experience(text: str) -> str:
    if _INTERN_RE.search(text):
        return "intern"
    if _LEAD_RE.search(text):
        return "lead"
    if _SENIOR_RE.search(text):
        return "senior"
    if _MID_RE.search(text):
        return "mid"
    return "entry"  # pipeline already filters for junior/grad


def _extract_salary_aud(text: str) -> Tuple[int, int]:
    """AUD-only salary parse. Returns (0, 0) when nothing matches."""
    if not text:
        return 0, 0
    m = _SALARY_K_RE.search(text)
    if m:
        lo, hi = int(m.group(1)) * 1000, int(m.group(2)) * 1000
        if 20_000 <= lo <= hi:
            return lo, hi
    m = _SALARY_FULL_RE.search(text)
    if m:
        lo = int(m.group(1) + m.group(2))
        hi = int(m.group(3) + m.group(4))
        if 20_000 <= lo <= hi:
            return lo, hi
    return 0, 0


def _classify_source(source: str) -> str:
    return _SOURCE_ENUM.get(source.lower(), "Direct")


def to_job(j: JobListing) -> Job:
    # Classify from short, high-signal strings only. Scanning full descriptions
    # produced false positives (e.g. an Associate role with "lead the team" in
    # the body got tagged experience=lead).
    type_signal = f"{j.title} {j.location}"
    exp_signal = j.title

    salary_min, salary_max = _extract_salary_aud(
        (j.summary or "") + " " + (j.description or "")
    )
    raw_match = max(0, j.match_score) * 8 + max(0, j.visa_score) * 4
    score = max(0, min(100, raw_match))
    posted_at = datetime.combine(j.date_found, time.min, tzinfo=timezone.utc)
    return Job(
        id=j.hash_id,
        title=j.title,
        company=j.company,
        companyEmoji="",
        location=j.location,
        type=_classify_type(type_signal),  # type: ignore[arg-type]
        salaryMin=salary_min,
        salaryMax=salary_max,
        postedAt=posted_at,
        description=j.description or j.summary or "",
        tags=list(j.tags or []),
        visaSponsorship=j.visa_score >= 3,
        experience=_classify_experience(exp_signal),  # type: ignore[arg-type]
        matchScore=score,
        source=_classify_source(j.source),  # type: ignore[arg-type]
    )


def _location_matches(job_location: str, wanted: List[str]) -> bool:
    if not wanted:
        return True
    loc = job_location.lower()
    if "australia" in loc:
        # GradConnection marks everything Australia-wide
        return True
    return any(p.lower() in loc for p in wanted if p)


def filter_and_score(
    jobs: List[Job],
    prefs: UserPreferences,
    resume_skills: List[str],
) -> List[Job]:
    out: List[Job] = []
    skills_lc = [s.lower() for s in (resume_skills or []) if s]
    kw_patterns = [p.lower() for p in (prefs.keywords + prefs.desiredRoles) if p]

    for job in jobs:
        # Location: remote always passes; otherwise must match a preferred city
        if job.type != "remote" and not _location_matches(job.location, prefs.locations):
            continue
        if prefs.remoteOnly and job.type != "remote":
            continue
        if prefs.jobTypes and job.type not in prefs.jobTypes:
            continue
        # NOTE: prefs.visaSponsorship is intentionally NOT a hard filter. The
        # CLI pipeline already drops citizenship-only and security-cleared
        # roles upstream (jobradar/core/filters.py:apply_visa_filter), so
        # anything that reaches this CSV is at least visa-feasible. Filtering
        # again on visa_score >= 3 would exclude most surviving listings —
        # most companies just don't mention sponsorship explicitly. The
        # visa_score still feeds matchScore so explicit sponsors rank higher.
        # Experience: enforce only when the job has a clearly different level.
        # intern overlaps with entry — keep both visible if the user picked entry.
        if (
            prefs.experienceLevel
            and job.experience != prefs.experienceLevel
            and not (prefs.experienceLevel == "entry" and job.experience == "intern")
        ):
            continue
        # Salary: only filter when both sides have numbers
        if (
            job.salaryMin > 0
            and prefs.maxSalary > 0
            and job.salaryMin > prefs.maxSalary
        ):
            continue
        if (
            job.salaryMax > 0
            and prefs.minSalary > 0
            and job.salaryMax < prefs.minSalary
        ):
            continue
        # Keywords/desiredRoles: at least one hit in title+description
        if kw_patterns:
            hay = (job.title + " " + (job.description or "")).lower()
            if not any(p in hay for p in kw_patterns):
                continue
        # Soft boost from resumeSkills overlap
        if skills_lc:
            hay = (job.title + " " + (job.description or "")).lower()
            bumps = sum(1 for s in skills_lc if s in hay)
            job.matchScore = min(100, job.matchScore + bumps * 3)
        out.append(job)

    out.sort(key=lambda j: -j.matchScore)
    return out


def cache_key(prefs: UserPreferences, resume_skills: List[str], mtime: float) -> str:
    payload = {
        "prefs": prefs.model_dump(),
        "skills": sorted({s.lower() for s in (resume_skills or []) if s}),
        "mtime": round(mtime, 3),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()
