"""Resume-to-job skill match scoring.

Scores each job 0–10 based on how many of Laiya's technical skills appear
in the job text (title + summary + description).

At module load the scorer tries to parse Laiya_Wang_AWS.pdf via pdfplumber
and builds the skill list from the resume text. When the PDF is updated the
next run automatically picks up new skills — no manual regex edits required.

If pdfplumber is unavailable or the PDF can't be read the scorer falls back
to a hardcoded skill list that mirrors the current resume.

Skill weights:
  3 — core stack (daily tools, strongest claims on resume)
  2 — strong supporting skills
  1 — familiar / transferable skills

Normalisation: raw points capped at _FULL_MATCH_THRESHOLD → scaled 0–10.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from jobradar.core.models import JobListing
from jobradar.core.resume_parser import extract_skills_from_pdf

# ── Hardcoded fallback (mirrors current resume; used when PDF parse fails) ──────
_FALLBACK_SKILLS: List[Tuple[str, int, str]] = [
    # Core
    (r'(?<!\w)c#(?!\w)|c\s*sharp\b',                  3, "C#"),
    (r'\.net\b|dotnet\b|asp\.net\b',                 3, ".NET"),
    (r'\bpython\b',                                  3, "Python"),
    (r'\btypescript\b',                              3, "TypeScript"),
    (r'\breact\b',                                   3, "React"),
    (r'\bsql\b',                                     3, "SQL"),
    (r'\baws\b|amazon\s+web\s+services\b',            3, "AWS"),
    # Strong
    (r'\bazure\b',                                   2, "Azure"),
    (r'\bdocker\b',                                  2, "Docker"),
    (r'\bci[/\s\-]?cd\b|continuous\s+integration\b', 2, "CI/CD"),
    (r'\bdevops\b|dev\s*ops\b',                      2, "DevOps"),
    (r'\bnode\.?js\b|nodejs\b',                      2, "Node.js"),
    (r'\brest\s*(?:ful\s*)?api\b',                   2, "REST API"),
    (r'\bmicroservice',                              2, "Microservices"),
    (r'\bintegration\s+(?:developer|engineer|architect|specialist)\b', 2, "Integration Dev"),
    (r'\bkubernetes\b|\bk8s\b',                      2, "Kubernetes"),
    (r'\bpower\s+automate\b',                        2, "Power Automate"),
    (r'\boracle\b',                                  2, "Oracle"),
    (r'\bn8n\b',                                     2, "n8n"),
    # Familiar
    (r'\bgit\b|github\b|gitlab\b',                   1, "Git"),
    (r'\blinux\b|ubuntu\b|debian\b',                 1, "Linux"),
    (r'\bagile\b|\bscrum\b',                         1, "Agile"),
    (r'\bjavascript\b|\bjs\b',                       1, "JavaScript"),
    (r'\bcloud\b',                                   1, "Cloud"),
    (r'\bpostgres(?:ql)?\b',                         1, "PostgreSQL"),
    (r'\bhadoop\b',                                  1, "Hadoop"),
    (r'\bapi\b',                                     1, "API"),
    (r'\buml\b',                                     1, "UML"),
    (r'\bhtml\b',                                    1, "HTML"),
    (r'\bcss\b',                                     1, "CSS"),
    (r'\bdns\b',                                     1, "DNS"),
    (r'\bnginx\b',                                   1, "Nginx"),
]

# ── Load skills from PDF (auto-updates when resume changes) ─────────────────────
_parsed = extract_skills_from_pdf()
if _parsed:
    _SKILLS = _parsed
    print(f"[ResumeScorer] Loaded {len(_SKILLS)} skills from Laiya_Wang_AWS.pdf")
else:
    _SKILLS = _FALLBACK_SKILLS

_FULL_MATCH_THRESHOLD = 4 * 3 + 2 * 2 + 2 * 1  # = 18 → "very good match" raw score

_COMPILED = [(re.compile(pat, re.I), w, name) for pat, w, name in _SKILLS]


def score_match(job: JobListing) -> Tuple[int, str]:
    """Return (match_score 0–10, matched_skills_str) for a job."""
    text = f"{job.title} {job.summary} {job.description}"
    raw = 0
    matched: List[str] = []
    for pattern, weight, name in _COMPILED:
        if pattern.search(text):
            raw += weight
            matched.append(name)
    score = min(10, raw * 10 // _FULL_MATCH_THRESHOLD) if raw else 0
    skills_str = ", ".join(matched) if matched else "—"
    return score, skills_str


def score_all_matches(jobs: List[JobListing]) -> List[JobListing]:
    """Attach match_score and match_skills to every job in-place."""
    for job in jobs:
        job.match_score, job.match_skills = score_match(job)
    return jobs
