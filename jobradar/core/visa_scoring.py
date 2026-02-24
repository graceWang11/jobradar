"""Heuristic 485 visa friendliness scoring.

Score range: 0 – 5
  0–1  Negative signals present (citizen/PR required, clearance)
  2–3  No clear signals (neutral)
  4–5  Positive signals present (sponsorship, international candidates)
"""

from __future__ import annotations

from typing import List, Tuple

from jobradar.core.models import JobListing


# ── Signal tables ─────────────────────────────────────────────────────────────

_HARD_NEGATIVES: List[Tuple[str, int, str]] = [
    ("australian citizen", -4, "Australian citizen required"),
    ("must be a citizen", -4, "Australian citizen required"),
    ("citizen only", -4, "Citizen only"),
    ("citizenship required", -4, "Citizenship required"),
    ("nv1", -4, "NV1 clearance required"),
    ("nv2", -4, "NV2 clearance required"),
    ("top secret", -4, "Security clearance required"),
    ("secret clearance", -4, "Security clearance required"),
    ("baseline clearance", -3, "Baseline clearance required"),
    ("security clearance", -3, "Security clearance required"),
    ("pr only", -3, "Permanent residents only"),
    ("permanent resident only", -3, "Permanent residents only"),
    ("must hold permanent", -3, "Permanent residence required"),
]

_SOFT_NEGATIVES: List[Tuple[str, int, str]] = [
    ("full working rights", -1, "Full working rights mentioned (may exclude temporary visas)"),
    ("permanent work rights", -2, "Permanent work rights required"),
    ("must have full working rights", -2, "Full working rights required"),
]

_POSITIVES: List[Tuple[str, int, str]] = [
    ("visa sponsorship", +3, "Visa sponsorship available"),
    ("sponsorship available", +3, "Visa sponsorship available"),
    ("sponsor visa", +3, "Visa sponsorship available"),
    ("international candidates", +2, "International candidates welcome"),
    ("international students", +2, "International students welcome"),
    ("welcome international", +2, "International candidates welcome"),
    ("temporary visa", +2, "Temporary visa accepted"),
    ("temporary work visa", +2, "Temporary visa accepted"),
    ("work rights in australia", +1, "Work rights in Australia mentioned"),
    ("485", +2, "485 visa mentioned"),
    ("graduate visa", +2, "Graduate visa (485) mentioned"),
]


def score_job(job: JobListing) -> JobListing:
    """Compute and attach visa_score + visa_reason to a JobListing (in-place)."""
    text = f"{job.title} {job.summary}".lower()
    score = 2  # neutral starting point (mid of 0–5, slightly pessimistic)
    reasons: List[str] = []

    for phrase, delta, label in _HARD_NEGATIVES:
        if phrase in text:
            score += delta
            reasons.append(f"[-] {label}")

    for phrase, delta, label in _SOFT_NEGATIVES:
        if phrase in text:
            score += delta
            reasons.append(f"[-] {label}")

    for phrase, delta, label in _POSITIVES:
        if phrase in text:
            score += delta
            reasons.append(f"[+] {label}")

    job.visa_score = max(0, min(5, score))
    job.visa_reason = "; ".join(reasons) if reasons else "No specific signals found"
    return job


def score_all(jobs: List[JobListing]) -> List[JobListing]:
    return [score_job(job) for job in jobs]
