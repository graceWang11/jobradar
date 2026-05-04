"""Recruiter contact recommendation helpers.

Generates a LinkedIn people-search URL (talent acquisition/recruiter at the
hiring company) and a ≤300-char connection-request message for each job.
"""

from __future__ import annotations

from typing import List
from urllib.parse import quote_plus

from jobradar.core.models import JobListing

_CANDIDATE_NAME = "Laiya"


def recruiter_search_url(company: str) -> str:
    """Return a LinkedIn people-search URL for recruiters at *company*."""
    query = f'"{company}" recruiter OR "talent acquisition"'
    return f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(query)}"


def generate_outreach_msg(job: JobListing) -> str:
    """Return a ≤300-char LinkedIn connection-request message for *job*."""
    skills_list = [s.strip() for s in job.match_skills.split(",") if s.strip()][:3]
    skills_str = ", ".join(skills_list) if skills_list else "software development"

    title = job.title if len(job.title) <= 55 else job.title[:52] + "…"
    company = job.company if len(job.company) <= 35 else job.company[:32] + "…"

    msg = (
        f"Hi, I'm interested in the {title} role at {company}. "
        f"I have {skills_str} experience and hold a 485 graduate visa "
        f"(full AU work rights). Would love to connect! — {_CANDIDATE_NAME}"
    )
    return msg[:300]


def enrich_all(jobs: List[JobListing]) -> None:
    """Attach recruiter_url and outreach_msg to every job in-place."""
    for job in jobs:
        job.recruiter_url = recruiter_search_url(job.company)
        job.outreach_msg = generate_outreach_msg(job)
