"""Pipeline filter functions for JobRadar.

All regex patterns and filter predicates live here so __main__.py stays
thin (orchestration only). Each public function takes a list of JobListings
and returns the filtered list, printing a one-line count summary.
"""

from __future__ import annotations

import re
from typing import List

from jobradar.core.models import JobListing

# ── Level / experience patterns ───────────────────────────────────────────────

_LEVEL_PATTERNS = [
    re.compile(r'\b' + re.escape(k) + r'\b', re.I)
    for k in [
        "graduate", "junior", "entry level", "entry-level",
        "associate", "early career", "cadet", "intern",
    ]
]

# "1–3 years experience" → entry-level, keep
_EXP_RANGE_PATTERN = re.compile(
    r'\b[0-3]\s*[-–]\s*[1-3]\s*\+?\s*years?\s+(?:of\s+)?(?:experience|exp)\b',
    re.I,
)

# 3+ years → overqualified, reject
_EXP_OVERQUALIFIED = re.compile(
    r'\b[3-9]\+\s*years?\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|work\s+)?(?:experience|exp)\b|'
    r'\b[3-9]\s*[-–]\s*\d+\s*years?\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+)?(?:experience|exp)\b|'
    r'\b[3-9]\s+to\s+\d+\s*years?\s+(?:of\s+)?(?:experience|exp)\b|'
    r'\b3\s+years?\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|work\s+)?(?:experience|exp)\b|'
    r'\bminimum\s+(?:of\s+)?[3-9]\s*\+?\s*years?\s*(?:of\s+)?(?:experience|exp)?\b|'
    r'\bat\s+least\s+[3-9]\s*years?\s*(?:of\s+)?(?:experience|exp)?\b|'
    r'\b[5-9]\s+years?\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+)?(?:experience|exp)\b|'
    r'\bthree\s+(?:or\s+more\s+)?years?\s+(?:of\s+)?(?:experience|exp)\b',
    re.I,
)

# ── IT role patterns ──────────────────────────────────────────────────────────

_TECH_ROLE_PATTERNS = [
    re.compile(r'\b' + re.escape(k) + r'\b', re.I)
    for k in [
        "software engineer", "software developer", "software engineering",
        "developer", "devops", "backend", "frontend", "full stack", "fullstack",
        "web developer", "mobile developer", "cloud engineer", "platform engineer",
        "data engineer", "data analyst", "data scientist", "data analytics",
        "cyber", "cybersecurity", "information security", "network engineer",
        "systems engineer", "computer science", "it graduate", "it program",
        # IT Architecture
        "solutions architect", "enterprise architect", "integration architect",
        "api architect", "cloud architect", "technical architect",
        "it architect", "software architect", "data architect",
        "security architect", "application architect", "infrastructure architect",
        "platform architect", "systems architect", "network architect",
        "solution architect",
        # IT / Technology Consulting
        "technology consultant", "it consultant", "solutions consultant",
        "technology consulting", "digital consultant", "consulting program",
        "technical consultant", "ict consultant", "associate consultant",
        "graduate consultant",
        # Integration / API / DevOps
        "integration developer", "integration engineer", "api developer",
        "api engineer", "platform engineer", "site reliability",
        "infrastructure engineer",
        # Cloud / DevOps
        "cloud", "cloud operations",
        # Domain / program signals
        "technology graduate", "tech graduate", "technology program",
        "technology internship", "tech internship",
        "software", "technology", "data", "analytics", "digital",
        "information technology", "information systems", "ict",
    ]
]

# ── Exclusion patterns ────────────────────────────────────────────────────────

_NON_IT_TITLE_WORDS = re.compile(
    r'\b(civil|mechanical|hydro|structural|geotechnical|mining|'
    r'chemical|electrical wiring|audit|accounting|actuari|'
    r'banking|finance|financial planning|wealth|insurance|legal|law|'
    r'nursing|medical|pharmacy|physiother|dental|clinical|'
    r'tax\b|taxation\b|graphic design|graphic designer|'
    r'landscape architect|interior architect|urban architect|'
    r'building architect|heritage architect|urban designer|'
    r'sales representative|sales associate|account executive|'
    r'business development representative|'
    r'sales consultant|sales engineer|pre.?sales|inside sales|'
    r'business administrator|'
    r'compliance assistant|compliance officer|'
    r'content developer|content writer|copywriter|'
    r'recruiter|talent acquisition|human resources\b|'
    r'management consultant|strategy consultant|'
    r'strategy.*operations|consumer strategy|'
    r'marketing coordinator|marketing assistant|digital marketing|'
    r'investment quant|quant analyst|quant developer|'
    r'mechatronics|control systems engineer|drilling engineer|'
    r'hardware engineer|product hardware|'
    r'apparel|fashion|textile|'
    r'supply chain\b|logistics coordinator|'
    r'sheep production|agricultural research|grant.?funded research|'
    r'construction|golf course|site administrator|landscap|'
    r'plumb|electri(?:cian)|carpenter|cabinet maker|'
    r'warehouse)\b',
    re.I,
)

_SENIOR_TITLE_WORDS = re.compile(
    r'\b(senior|sr\b|lead|principal|staff|manager|director|'
    r'head of|vp|vice president|chief|experienced|mid.?level)\b',
    re.I,
)

_DESIGNATED_ROLE_PATTERN = re.compile(
    r'\b(designated indigenous|indigenous identified|'
    r'first nations identified|aboriginal and torres strait|'
    r'indigenous role|identified position)\b',
    re.I,
)

_RESUME_HARD_EXCLUDE = re.compile(
    r'\b(ios\b|swift\b|objective.?c|ruby on rails|laravel|php\b|'
    r'mulesoft|salesforce|zoho|deluge|objectstar|cobol|abap|mainframe|'
    r'flutter|dart\b|kotlin\b|embedded|firmware|fpga|vhdl|verilog|'
    r'sap\b|servicenow|pega\b|mendix|outsystems)\b',
    re.I,
)

# ── Visa eligibility patterns ─────────────────────────────────────────────────

VISA_RESTRICT_PATTERN = re.compile(
    r'must be (an? )?australian citizen|'
    r'australian citizen(ship)? (is )?required|'
    r'must hold (an? )?australian citizenship|'
    r'holds? (an? )?australian citizenship|'
    r'hold(ing)? australian citizenship|'
    r'requires? (permanent residency|permanent resident)|'
    r'must hold permanent residency|'
    r'holds? permanent residency|'
    r'must be (an? )?(australian )?permanent resident|'
    r'(permanent resident|pr holder)s? only|'
    r'(citizen|citizenship) and (permanent )?resident|'
    r'citizen or permanent resident|'
    r'citizens? and permanent residents?|'
    r'(australian )?citizen(ship)? or (permanent )?resident|'
    r'must be (a |an )?(citizen|resident).{0,30}(or|and).{0,30}(citizen|resident)|'
    r'australian citizens?\s+only|'
    r'open to (australian )?citizens?\b(?!\s+and\s+international\b)|'
    r'be\s+a\s+citizen\s+of\s+australia|'
    r'citizenship\s*:\s*australian|'
    r'eligibility\s*:\s*(must\s+be\s+)?(an?\s+)?(australian\s+)?citizen|'
    r'australian citizenship\s+(is\s+|are\s+)?(required|mandatory|necessary|essential|compulsory|a must)|'
    r'(applicant|candidate)s?\s+must\s+(be|hold)\s+(an?\s+)?(australian\s+)?citizen|'
    r'only (open|available) to (australian )?(citizen|permanent resident)|'
    r'restricted to (australian )?(citizens?|permanent residents?)|'
    r'(open only|available only) to (australian )?(citizens?|permanent residents?)|'
    r'permanent work rights required|'
    r'must have permanent.*work rights|'
    r'must hold permanent (work )?rights|'
    r'work rights? must be permanent|'
    r'require(s)? permanent (work )?rights|'
    r'full permanent (work |working )?rights',
    re.I,
)

CLEARANCE_RESTRICT_PATTERN = re.compile(
    r'\b('
    r'nv1|nv2|'
    r'positive vetting|pv clearance|pv cleared|pv-cleared|'
    r'top secret clearance|'
    r'baseline clearance required|baseline clearance is required|'
    r'clearance required|must hold.{0,20}clearance|'
    r'requires?.{0,15}security clearance'
    r')\b',
    re.I,
)

FED_GOV_CITIZENSHIP_PATTERN = re.compile(
    r'\b('
    r'aps\s*[1-6]\b|el\s*[12]\b|'
    r'australian government graduate program|aggp|'
    r'australian public service\b'
    r')\b',
    re.I,
)

DEFENCE_COMPANIES = re.compile(
    r'\b('
    r'saab|sypaq|aurizn|kinexus|anduril|'
    r'lockheed\s+martin|bae\s+systems|thales\s+australia|raytheon|'
    r'northrop\s+grumman|boeing|leidos|l3harris|frequentis|'
    r'defence\s+science\s+and\s+technology'
    r')\b',
    re.I,
)

DEFENCE_TITLE_PATTERN = re.compile(
    r'\bdefence\s+(graduate|digital|data|technology|cyber|engineering|program)\b',
    re.I,
)

FED_GOV_COMPANIES = re.compile(
    r'^('
    r'australian taxation office|'
    r'public service commission|'
    r'australian bureau of statistics|'
    r'department of home affairs|'
    r'australian signals directorate|'
    r'australian security intelligence organisation|'
    r'australian secret intelligence service|'
    r'australian federal police|'
    r'department of defence'
    r')$',
    re.I,
)

_POLICE_CHECK_PATTERN = re.compile(
    r'\bnational\s+police\s+(check|clearance)\b', re.I
)

CITIZEN_IN_TITLE_PATTERN = re.compile(
    r'australian\s+citizen(?:ship)?|citizen(?:ship)?\s+required',
    re.I,
)

# ── Description content filter patterns ───────────────────────────────────────

_EXP_THREE_YEARS_FULL = re.compile(
    r'\b3\s*\+?\s*years?\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|work\s+)?'
    r'(?:experience|exp)\b|'
    r'\b3\s*[-–]\s*\d+\s*years?\s+(?:of\s+)?(?:experience|exp)\b|'
    r'\b3\s+to\s+\d+\s*years?\s+(?:of\s+)?(?:experience|exp)\b|'
    r'\bminimum\s+(?:of\s+)?3\s*\+?\s*years?\b|'
    r'\bat\s+least\s+3\s*years?\b|'
    r'\bthree\s+(?:or\s+more\s+)?years?\s+(?:of\s+)?(?:experience|exp)\b|'
    r'\b[3-9]\+?\s*years?\s+experience\b',
    re.I,
)

# URL fragments for sources where description fetch is intentionally skipped
_SKIP_DESCRIPTION_SOURCES = {"seek.com.au", "linkedin.com"}


# ── Public filter functions ───────────────────────────────────────────────────

def apply_location_filter(
    jobs: List[JobListing],
    locations: List[str],
    include_remote: bool = False,
) -> List[JobListing]:
    location_lower = {loc.lower() for loc in locations}
    if include_remote:
        location_lower.update({"remote", "hybrid"})

    result = [
        j for j in jobs
        if (
            j.location.lower() in ("australia",)
            or any(loc in j.location.lower() for loc in location_lower)
        )
    ]
    removed = len(jobs) - len(result)
    print(f"[jobradar] After location filter: {len(result)} (removed {removed} off-target)")
    return result


def _is_relevant(j: JobListing) -> bool:
    title    = j.title.lower()
    summary  = j.summary.lower()
    combined = f"{title} {summary}"

    if _NON_IT_TITLE_WORDS.search(title):
        return False
    if _SENIOR_TITLE_WORDS.search(title):
        return False
    if _DESIGNATED_ROLE_PATTERN.search(combined):
        return False
    if _EXP_OVERQUALIFIED.search(combined):
        return False

    has_role  = any(p.search(combined) for p in _TECH_ROLE_PATTERNS)
    has_level = (
        any(p.search(combined) for p in _LEVEL_PATTERNS)
        or bool(_EXP_RANGE_PATTERN.search(combined))
    )

    # Pre-targeted sources only need an IT role match (level already filtered upstream)
    if j.source in ("CompanyCareers", "GovtCareers", "Greenhouse", "Ashby",
                    "SmartRecruiters", "Workday"):
        return has_role

    # BuiltIn pre-filters by level in the connector, but still needs both
    # checks to prevent broad patterns (data/technology) matching non-IT summaries

    return has_role and has_level


def apply_relevance_filter(jobs: List[JobListing]) -> List[JobListing]:
    result = [j for j in jobs if j.title and _is_relevant(j)]
    removed = len(jobs) - len(result)
    print(f"[jobradar] After relevance filter: {len(result)} (removed {removed} non-tech)")
    return result


def apply_resume_filter(jobs: List[JobListing]) -> List[JobListing]:
    result = [j for j in jobs if not _RESUME_HARD_EXCLUDE.search(f"{j.title} {j.summary}".lower())]
    removed = len(jobs) - len(result)
    print(f"[jobradar] After resume fit filter: {len(result)} (removed {removed} outside Laiya's stack)")
    return result


def _passes_visa(j: JobListing) -> bool:
    combined = f"{j.title} {j.summary}"
    company  = j.company.strip()

    if _POLICE_CHECK_PATTERN.search(combined):
        return True
    if CITIZEN_IN_TITLE_PATTERN.search(j.title):
        return False
    if CLEARANCE_RESTRICT_PATTERN.search(combined):
        return False
    if FED_GOV_CITIZENSHIP_PATTERN.search(combined):
        return False
    if DEFENCE_TITLE_PATTERN.search(j.title):
        return False
    if DEFENCE_COMPANIES.search(company):
        return False
    if FED_GOV_COMPANIES.search(company):
        return False
    if VISA_RESTRICT_PATTERN.search(combined):
        return False
    return True


def apply_visa_filter(jobs: List[JobListing]) -> List[JobListing]:
    result = [j for j in jobs if _passes_visa(j)]
    removed = len(jobs) - len(result)
    print(
        f"[jobradar] After visa eligibility filter: {len(result)} "
        f"(removed {removed} citizen/PR-only or clearance roles)"
    )
    return result


def _passes_description_check(j: JobListing) -> bool:
    desc = j.description

    if not desc and any(s in j.url for s in _SKIP_DESCRIPTION_SOURCES):
        return True
    if not desc or len(desc) < 100:
        return True

    if _EXP_THREE_YEARS_FULL.search(desc):
        print(f"[DescFilter] REMOVED (3yr exp in desc): {j.title!r} @ {j.company}")
        return False
    if _EXP_OVERQUALIFIED.search(desc):
        print(f"[DescFilter] REMOVED (overqualified exp in desc): {j.title!r} @ {j.company}")
        return False
    if VISA_RESTRICT_PATTERN.search(desc):
        print(f"[DescFilter] REMOVED (citizen/PR in desc): {j.title!r} @ {j.company}")
        return False
    if CITIZEN_IN_TITLE_PATTERN.search(desc):
        print(f"[DescFilter] REMOVED (citizenship phrase in desc): {j.title!r} @ {j.company}")
        return False
    if CLEARANCE_RESTRICT_PATTERN.search(desc):
        print(f"[DescFilter] REMOVED (clearance in desc): {j.title!r} @ {j.company}")
        return False
    if FED_GOV_CITIZENSHIP_PATTERN.search(desc):
        print(f"[DescFilter] REMOVED (APS/fed-gov level in desc): {j.title!r} @ {j.company}")
        return False
    if DEFENCE_TITLE_PATTERN.search(desc):
        print(f"[DescFilter] REMOVED (defence program in desc): {j.title!r} @ {j.company}")
        return False

    return True


def apply_description_filter(jobs: List[JobListing]) -> List[JobListing]:
    result = [j for j in jobs if _passes_description_check(j)]
    removed = len(jobs) - len(result)
    print(
        f"[jobradar] After description content filter: {len(result)} "
        f"(removed {removed} with 3yr-exp or citizen/PR clauses in body)"
    )
    return result
