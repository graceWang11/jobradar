"""Heuristic 485 visa friendliness scoring.

Score range: 0 – 5
  0–1  Negative signals present (citizen/PR required, clearance)
  2–3  No clear signals (neutral)
  4–5  Positive signals present (sponsorship, international candidates)
"""

from __future__ import annotations

import re
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

# Companies with a demonstrated history of sponsoring visas in Australia.
# Large multinationals and Big-4 consulting firms routinely sponsor 482/485 holders.
# Jobs at these employers get +1 even when the JD says nothing explicit — moving
# them from neutral (2) to mildly positive (3) so they sort above true unknowns.
_KNOWN_SPONSORS = re.compile(
    r'\b('
    # Big 4 + Accenture consulting
    r'deloitte|kpmg|pricewaterhousecoopers|pwc\b|ernst\s*&\s*young|\bey\b|accenture|'
    # Global IT services
    r'ibm\b|capgemini|cognizant|infosys|wipro\b|tata\s+consultancy|\btcs\b|dxc\b|'
    r'thoughtworks|ntt\s+data|'
    # Big tech with AU presence
    r'google\b|microsoft\b|amazon\b|\baws\b|salesforce|oracle\b|sap\b|'
    r'servicenow|atlassian|canva\b|xero\b|'
    # Major AU banks — all sponsor
    r'national\s+australia\s+bank|\bnab\b|\banz\b|westpac|commonwealth\s+bank|macquarie\b|'
    # Big AU tech / scale-ups
    r'rea\s+group|realestate\.com|cultureamp|culture\s+amp|deputy\b|buildkite|'
    r'airwallex|afterpay|\bblock\b'
    r')\b',
    re.I,
)

_POSITIVES: List[Tuple[str, int, str]] = [
    ("visa sponsorship", +3, "Visa sponsorship available"),
    ("sponsorship available", +3, "Visa sponsorship available"),
    ("sponsor visa", +3, "Visa sponsorship available"),
    ("we sponsor", +3, "Visa sponsorship available"),
    ("international candidates", +2, "International candidates welcome"),
    ("international students", +2, "International students welcome"),
    ("welcome international", +2, "International candidates welcome"),
    ("open to international", +2, "International candidates welcome"),
    ("all nationalities", +2, "All nationalities welcome"),
    ("diverse background", +1, "Diversity-inclusive employer"),
    ("temporary visa", +2, "Temporary visa accepted"),
    ("temporary work visa", +2, "Temporary visa accepted"),
    ("all visa types", +3, "All visa types accepted"),
    ("work rights in australia", +1, "Work rights in Australia mentioned"),
    ("485", +2, "485 visa mentioned"),
    ("graduate visa", +2, "Graduate visa (485) mentioned"),
    ("subclass 485", +3, "485 visa explicitly mentioned"),
    ("working holiday", +1, "Working holiday visa mentioned (open employer)"),
]


def score_job(job: JobListing) -> JobListing:
    """Compute and attach visa_score + visa_reason to a JobListing (in-place)."""
    # Include description when available — many positive signals (sponsorship, diversity
    # statements) only appear in the full JD body, not the teaser.
    text = f"{job.title} {job.summary} {job.description}".lower()
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

    # Known sponsor employer → nudge from neutral (2) to mildly positive (3)
    if _KNOWN_SPONSORS.search(job.company):
        score += 1
        reasons.append("[+] Known visa-sponsoring employer")

    job.visa_score = max(0, min(5, score))
    job.visa_reason = "; ".join(reasons) if reasons else "No specific signals found"
    return job


def score_all(jobs: List[JobListing]) -> List[JobListing]:
    return [score_job(job) for job in jobs]
