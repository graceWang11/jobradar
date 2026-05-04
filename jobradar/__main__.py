"""JobRadar CLI – python -m jobradar run [options]

Usage:
    python -m jobradar run
    python -m jobradar run --city melbourne
    python -m jobradar run --since 24h
    python -m jobradar run --dry-run
    python -m jobradar run --no-email
    python -m jobradar run --reset
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import List

import subprocess

from jobradar.config.loader import load_config, load_env, get_locations
from jobradar.connectors.adzuna import AdzunaConnector
from jobradar.connectors.company_careers import CompanyCareersConnector
from jobradar.connectors.email_alerts import EmailAlertsConnector
from jobradar.connectors.govt_careers import GovtCareersConnector
from jobradar.connectors.gradconnection import GradConnectionConnector
from jobradar.connectors.greenhouse import GreenhouseConnector
from jobradar.connectors.indeed import IndeedConnector
from jobradar.connectors.jora import JoraConnector
from jobradar.connectors.lever import LeverConnector
from jobradar.connectors.linkedin import LinkedInConnector
from jobradar.connectors.prosple import ProspleConnector
from jobradar.connectors.seek import SeekConnector
from jobradar.core.dedupe import deduplicate, reset_state
from jobradar.core.description_fetcher import fetch_descriptions
from jobradar.core.models import JobListing
from jobradar.core.normalize import normalize_many
from jobradar.core.output import save_csv, save_html, save_markdown
from jobradar.core.visa_scoring import score_all
from jobradar.core.resume_scorer import score_all_matches
from jobradar.core.email_sender import send_email


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobradar",
        description="Junior/grad tech job aggregator – Adelaide & Melbourne",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Collect, process, and send jobs")
    run_parser.add_argument(
        "--since",
        default="24h",
        help="Recency filter (e.g. 24h, 7d) – informational for now",
    )
    run_parser.add_argument(
        "--city",
        default=None,
        help="Limit to one city: adelaide or melbourne",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline but skip email send and dedup persistence",
    )
    run_parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip email delivery",
    )
    run_parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear the dedupe state before running",
    )
    run_parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="Skip Markdown output",
    )

    subparsers.add_parser("export", help="Re-export last run's data (not yet implemented)")

    return parser


def run_pipeline(args: argparse.Namespace, cfg: dict) -> None:
    run_date = date.today()

    if args.reset:
        reset_state()

    # ── 1. Determine active locations ─────────────────────────────────────────
    all_locations = get_locations(cfg)
    if args.city:
        city_map = {"adelaide": "Adelaide", "melbourne": "Melbourne"}
        city = city_map.get(args.city.lower())
        if not city:
            print(f"[jobradar] Unknown city '{args.city}'. Use 'adelaide' or 'melbourne'.")
            sys.exit(1)
        locations = [city]
    else:
        locations = all_locations

    print(f"[jobradar] Starting run for: {', '.join(locations)}")

    # ── 2. Collect from each enabled source ───────────────────────────────────
    sources_cfg = cfg.get("sources", {})
    keywords: List[str] = []  # passed to connectors for future use

    raw_jobs: list[dict] = []
    all_listings: List[JobListing] = []

    if sources_cfg.get("prosple", {}).get("enabled", True):
        connector = ProspleConnector()
        connector.rate_limit_seconds = sources_cfg.get("prosple", {}).get("rate_limit_seconds", 2.5)
        raw = connector.fetch(locations, keywords)
        all_listings.extend(normalize_many(raw, "Prosple"))

    if sources_cfg.get("gradconnection", {}).get("enabled", True):
        connector = GradConnectionConnector()
        connector.rate_limit_seconds = sources_cfg.get("gradconnection", {}).get("rate_limit_seconds", 2.0)
        raw = connector.fetch(locations, keywords)
        all_listings.extend(normalize_many(raw, "GradConnection"))

    if sources_cfg.get("seek", {}).get("enabled", True):
        connector = SeekConnector()
        connector.rate_limit_seconds = sources_cfg.get("seek", {}).get("rate_limit_seconds", 2.0)
        raw = connector.fetch(locations, keywords)
        all_listings.extend(normalize_many(raw, "Seek"))

    if sources_cfg.get("linkedin", {}).get("enabled", True):
        connector = LinkedInConnector()
        connector.rate_limit_seconds = sources_cfg.get("linkedin", {}).get("rate_limit_seconds", 3.0)
        raw = connector.fetch(locations, keywords)
        all_listings.extend(normalize_many(raw, "LinkedIn"))

    if sources_cfg.get("adzuna", {}).get("enabled", True):
        # Adzuna aggregates Indeed, Jora + 50 other boards via free API
        connector = AdzunaConnector()
        connector.rate_limit_seconds = sources_cfg.get("adzuna", {}).get("rate_limit_seconds", 2.0)
        raw = connector.fetch(locations, keywords)
        all_listings.extend(normalize_many(raw, "Adzuna"))

    if sources_cfg.get("company_careers", {}).get("enabled", True):
        connector = CompanyCareersConnector()
        connector.rate_limit_seconds = sources_cfg.get("company_careers", {}).get("rate_limit_seconds", 2.0)
        raw = connector.fetch(locations, keywords)
        all_listings.extend(normalize_many(raw, "CompanyCareers"))

    if sources_cfg.get("govt_careers", {}).get("enabled", True):
        connector = GovtCareersConnector()
        connector.rate_limit_seconds = sources_cfg.get("govt_careers", {}).get("rate_limit_seconds", 2.0)
        raw = connector.fetch(locations, keywords)
        all_listings.extend(normalize_many(raw, "GovtCareers"))

    if sources_cfg.get("jora", {}).get("enabled", False):
        connector = JoraConnector()
        connector.rate_limit_seconds = sources_cfg.get("jora", {}).get("rate_limit_seconds", 2.0)
        raw = connector.fetch(locations, keywords)
        all_listings.extend(normalize_many(raw, "Jora"))

    if sources_cfg.get("greenhouse", {}).get("enabled", True):
        connector = GreenhouseConnector()
        connector.rate_limit_seconds = sources_cfg.get("greenhouse", {}).get("rate_limit_seconds", 1.5)
        raw = connector.fetch(locations, keywords)
        all_listings.extend(normalize_many(raw, "Greenhouse"))

    if sources_cfg.get("lever", {}).get("enabled", True):
        connector = LeverConnector()
        connector.rate_limit_seconds = sources_cfg.get("lever", {}).get("rate_limit_seconds", 1.5)
        raw = connector.fetch(locations, keywords)
        all_listings.extend(normalize_many(raw, "Lever"))

    if sources_cfg.get("email_alerts", {}).get("enabled", False):
        connector = EmailAlertsConnector()
        raw = connector.fetch(locations, keywords)
        all_listings.extend(normalize_many(raw, "EmailAlerts"))

    print(f"\n[jobradar] Total collected: {len(all_listings)} listings")

    if not all_listings:
        print("[jobradar] No listings found. Check connectors or try again later.")
        return

    # ── 3. Location filter ────────────────────────────────────────────────────
    # Keep jobs whose location matches a target city.
    # GradConnection cannot determine location at list level — its jobs are
    # marked "Australia" and pass through (they get IT-filtered instead).
    include_remote = cfg.get("filters", {}).get("include_remote", False)
    location_lower = {loc.lower() for loc in locations}
    if include_remote:
        location_lower.update({"remote", "hybrid"})

    before_filter = len(all_listings)
    all_listings = [
        j for j in all_listings
        if (
            j.location.lower() in ("australia",)          # no location data → pass through
            or any(loc in j.location.lower() for loc in location_lower)
        )
    ]
    print(
        f"[jobradar] After location filter: {len(all_listings)} "
        f"(removed {before_filter - len(all_listings)} off-target)"
    )

    if not all_listings:
        print("[jobradar] No listings remain after location filter.")
        return

    # ── 4b. Role relevance filter ─────────────────────────────────────────────
    # Require BOTH:
    #   (a) a level keyword as a whole word (junior/graduate/entry/associate…)
    #       — word-boundary matching prevents "undergraduate" matching "graduate"
    #   (b) a specific IT role phrase in the title or summary
    import re as _re

    _LEVEL_PATTERNS = [
        _re.compile(r'\b' + _re.escape(k) + r'\b', _re.I)
        for k in ["graduate", "junior", "entry level", "entry-level",
                  "associate", "early career", "cadet", "intern"]
    ]

    # Descriptions saying "1-3 years experience" (or 0-2, 0-3, 1-2) count as entry-level
    _EXP_RANGE_PATTERN = _re.compile(
        r'\b[0-3]\s*[-–]\s*[1-3]\s*\+?\s*years?\s+(?:of\s+)?(?:experience|exp)\b',
        _re.I,
    )

    # Hard-exclude: job requires 3+ years experience — not suitable for Laiya.
    # Catches both the teaser and (later) the full description.
    _EXP_OVERQUALIFIED = _re.compile(
        # "3+ years experience", "3-5 years experience", "3 to 5 years"
        r'\b[3-9]\+\s*years?\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|work\s+)?(?:experience|exp)\b|'
        r'\b[3-9]\s*[-–]\s*\d+\s*years?\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+)?(?:experience|exp)\b|'
        r'\b[3-9]\s+to\s+\d+\s*years?\s+(?:of\s+)?(?:experience|exp)\b|'
        # plain "3 years experience" (no plus sign)
        r'\b3\s+years?\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|work\s+)?(?:experience|exp)\b|'
        # "minimum 3 years", "at least 3 years"
        r'\bminimum\s+(?:of\s+)?[3-9]\s*\+?\s*years?\s*(?:of\s+)?(?:experience|exp)?\b|'
        r'\bat\s+least\s+[3-9]\s*years?\s*(?:of\s+)?(?:experience|exp)?\b|'
        # "5 years of experience" (no plus)
        r'\b[5-9]\s+years?\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+)?(?:experience|exp)\b|'
        # "three or more years"
        r'\bthree\s+(?:or\s+more\s+)?years?\s+(?:of\s+)?(?:experience|exp)\b',
        _re.I,
    )

    # IT-domain phrases — word-boundary matched so "engineer" alone doesn't
    # catch "civil engineer", but "software" / "technology" etc. are fine.
    _TECH_ROLE_PATTERNS = [
        _re.compile(r'\b' + _re.escape(k) + r'\b', _re.I)
        for k in [
            # Explicit role titles
            "software engineer", "software developer", "software engineering",
            "developer", "devops", "backend", "frontend", "full stack", "fullstack",
            "web developer", "mobile developer", "cloud engineer", "platform engineer",
            "data engineer", "data analyst", "data scientist", "data analytics",
            "cyber", "cybersecurity", "information security", "network engineer",
            "systems engineer", "computer science", "it graduate", "it program",
            # IT Architecture (Laiya's core strength)
            # NOTE: bare "architect" intentionally EXCLUDED — too broad (catches building/landscape architects).
            # All forms below require an IT qualifier in the phrase itself.
            "solutions architect", "enterprise architect", "integration architect",
            "api architect", "cloud architect", "technical architect",
            "it architect", "software architect", "data architect",
            "security architect", "application architect", "infrastructure architect",
            "platform architect", "systems architect", "network architect",
            "solution architect",  # singular variant
            # IT / Technology Consulting (Laiya's current role)
            "technology consultant", "it consultant", "solutions consultant",
            "technology consulting", "digital consultant", "consulting program",
            "technical consultant", "ict consultant", "associate consultant",
            "graduate consultant",
            # Integration / API / DevOps
            "integration developer", "integration engineer", "api developer",
            "api engineer", "platform engineer", "site reliability",
            "infrastructure engineer",
            # Cloud / DevOps / Platform extensions
            "cloud", "cloud operations", "cloud architect", "cloud engineer",
            # Program / domain signals
            "technology graduate", "tech graduate", "technology program",
            "technology internship", "tech internship",
            "software",          # software alone is unambiguous
            "technology",        # "Graduate – Technology", "Technology Graduate Program"
            "data",              # "Data & Analytics Graduate Program"
            "analytics",         # "Data & Analytics"
            "digital",           # "Digital Graduate Program"
            "information technology", "information systems",
            "ict",               # ICT Graduate Program
        ]
    ]

    # Non-IT exclusion: title contains these → skip.
    # Catches civil/mining/finance AND non-software roles that slip through.
    _NON_IT_TITLE_WORDS = _re.compile(
        r'\b(civil|mechanical|hydro|structural|geotechnical|mining|'
        r'chemical|electrical wiring|audit|accounting|actuari|'
        r'banking|finance|financial planning|wealth|insurance|legal|law|'
        r'nursing|medical|pharmacy|physiother|dental|clinical|'
        r'tax\b|taxation\b|graphic design|graphic designer|'
        # Non-IT architecture (building/construction/design disciplines)
        r'landscape architect|interior architect|urban architect|'
        r'building architect|heritage architect|urban designer|'
        # Sales — always exclude, regardless of "technology" modifier
        r'sales representative|sales associate|account executive|'
        r'business development representative|'
        r'sales consultant|sales engineer|pre.?sales|inside sales|'
        r'business administrator|'
        r'compliance assistant|compliance officer|'
        r'content developer|content writer|copywriter|'
        # HR / recruitment
        r'recruiter|talent acquisition|human resources\b|'
        # Non-IT consulting / strategy
        r'management consultant|strategy consultant|'
        r'strategy.*operations|consumer strategy|'
        # Marketing
        r'marketing coordinator|marketing assistant|digital marketing|'
        # Finance / quant (not software development)
        r'investment quant|quant analyst|quant developer|'
        # Physical / engineering disciplines that are NOT software
        r'mechatronics|control systems engineer|drilling engineer|'
        r'hardware engineer|product hardware|'
        r'apparel|fashion|textile|'
        r'supply chain\b|logistics coordinator|'
        # Research roles outside IT
        r'sheep production|agricultural research|grant.?funded research|'
        # Physical / trades / non-tech industries in title
        r'construction|golf course|site administrator|landscap|'
        r'plumb|electri(?:cian)|carpenter|cabinet maker|'
        r'warehouse)\b',
        _re.I,
    )

    # Senior-level exclusion: always drop these regardless of tech role match.
    _SENIOR_TITLE_WORDS = _re.compile(
        r'\b(senior|sr\b|lead|principal|staff|manager|director|'
        r'head of|vp|vice president|chief|experienced|mid.?level)\b',
        _re.I,
    )

    # Designated/identified roles — not eligible for Laiya
    _DESIGNATED_ROLE_PATTERN = _re.compile(
        r'\b(designated indigenous|indigenous identified|'
        r'first nations identified|aboriginal and torres strait|'
        r'indigenous role|identified position)\b',
        _re.I,
    )

    def _is_relevant(j) -> bool:
        title    = j.title.lower()
        summary  = j.summary.lower()
        combined = f"{title} {summary}"

        if bool(_NON_IT_TITLE_WORDS.search(title)):
            return False
        if bool(_SENIOR_TITLE_WORDS.search(title)):
            return False
        if bool(_DESIGNATED_ROLE_PATTERN.search(combined)):
            return False
        # Explicitly overqualified experience requirement in teaser
        if bool(_EXP_OVERQUALIFIED.search(combined)):
            return False

        has_role  = any(p.search(combined) for p in _TECH_ROLE_PATTERNS)
        has_level = (
            any(p.search(combined) for p in _LEVEL_PATTERNS)
            or bool(_EXP_RANGE_PATTERN.search(combined))
        )

        # Company & govt career pages are pre-targeted — only need an IT role
        if j.source in ("CompanyCareers", "GovtCareers"):
            return has_role

        # All other sources (Seek, LinkedIn, Prosple, GradConnection, Adzuna):
        # require BOTH a level keyword AND an IT role.
        # Removed the "strong_tech" bypass — it was letting through senior roles
        # (e.g. "Agentic Data Engineer", "Cloud Architect") from company-targeted searches.
        return has_role and has_level

    before_rel = len(all_listings)
    all_listings = [j for j in all_listings if j.title and _is_relevant(j)]
    print(
        f"[jobradar] After relevance filter: {len(all_listings)} "
        f"(removed {before_rel - len(all_listings)} non-tech)"
    )

    if not all_listings:
        print("[jobradar] No listings remain after relevance filter.")
        return

    # ── 4c. Resume fit filter ─────────────────────────────────────────────────
    # Hard-exclude roles that require specific tech outside Laiya's stack.
    # Skills: C#/.NET, Python, TypeScript/React, AWS/Azure/Docker, SQL, CI/CD, DevOps.
    # Hard excludes — always blocked, no override
    _RESUME_HARD_EXCLUDE = _re.compile(
        r'\b(ios\b|swift\b|objective.?c|ruby on rails|laravel|php\b|'
        r'mulesoft|salesforce|zoho|deluge|objectstar|cobol|abap|mainframe|'
        r'flutter|dart\b|kotlin\b|embedded|firmware|fpga|vhdl|verilog|'
        r'sap\b|servicenow|pega\b|mendix|outsystems)\b',
        _re.I,
    )

    def _fits_resume(j) -> bool:
        combined = f"{j.title} {j.summary}".lower()
        return not bool(_RESUME_HARD_EXCLUDE.search(combined))

    before_resume = len(all_listings)
    all_listings = [j for j in all_listings if _fits_resume(j)]
    print(
        f"[jobradar] After resume fit filter: {len(all_listings)} "
        f"(removed {before_resume - len(all_listings)} outside Laiya's stack)"
    )

    if not all_listings:
        print("[jobradar] No listings remain after resume fit filter.")
        return

    # ── 4d. Visa eligibility filter ───────────────────────────────────────────
    # Three layers: (1) explicit text patterns, (2) security clearances,
    # (3) known defence/federal-govt employers that always require citizenship.

    # Layer 1 – explicit citizenship/PR phrases in title or teaser
    _VISA_RESTRICT_PATTERN = _re.compile(
        # Explicit citizenship
        r'must be (an? )?australian citizen|'
        r'australian citizen(ship)? (is )?required|'
        r'must hold (an? )?australian citizenship|'
        r'holds? (an? )?australian citizenship|'
        r'hold(ing)? australian citizenship|'
        # Permanent residency
        r'requires? (permanent residency|permanent resident)|'
        r'must hold permanent residency|'
        r'holds? permanent residency|'
        r'must be (an? )?(australian )?permanent resident|'
        r'(permanent resident|pr holder)s? only|'
        # Citizen OR/AND resident combined
        r'(citizen|citizenship) and (permanent )?resident|'
        r'citizen or permanent resident|'
        r'citizens? and permanent residents?|'
        r'(australian )?citizen(ship)? or (permanent )?resident|'
        r'must be (a |an )?(citizen|resident).{0,30}(or|and).{0,30}(citizen|resident)|'
        # "citizens only" / "open to Australian citizens [only]"
        r'australian citizens?\s+only|'
        # Restrictive phrasing: "open to citizens [only/and PRs]" but NOT
        # "open to Australian citizens and international candidates" (inclusive).
        # Lookahead stops at "and international" to avoid that false positive.
        r'open to (australian )?citizens?\b(?!\s+and\s+international\b)|'
        # "must/should/need to be a citizen of Australia"
        r'be\s+a\s+citizen\s+of\s+australia|'
        # Structured field formats used in govt/defence JDs
        r'citizenship\s*:\s*australian|'
        r'eligibility\s*:\s*(must\s+be\s+)?(an?\s+)?(australian\s+)?citizen|'
        # "Australian citizenship is/are mandatory/required/essential/compulsory"
        r'australian citizenship\s+(is\s+|are\s+)?(required|mandatory|necessary|essential|compulsory|a must)|'
        # "applicants/candidates must be (Australian) citizens"
        r'(applicant|candidate)s?\s+must\s+(be|hold)\s+(an?\s+)?(australian\s+)?citizen|'
        # "only open to / restricted to / available to"
        r'only (open|available) to (australian )?(citizen|permanent resident)|'
        r'restricted to (australian )?(citizens?|permanent residents?)|'
        r'(open only|available only) to (australian )?(citizens?|permanent residents?)|'
        # Permanent work rights
        r'permanent work rights required|'
        r'must have permanent.*work rights|'
        r'must hold permanent (work )?rights|'
        r'work rights? must be permanent|'
        r'require(s)? permanent (work )?rights|'
        r'full permanent (work |working )?rights',
        _re.I,
    )

    # Layer 2 – security clearance requirements (require citizenship in Australia)
    _CLEARANCE_RESTRICT_PATTERN = _re.compile(
        r'\b('
        r'nv1|nv2|'
        r'positive vetting|pv clearance|pv cleared|pv-cleared|'
        r'top secret clearance|'
        r'baseline clearance required|baseline clearance is required|'
        r'clearance required|must hold.{0,20}clearance|'
        r'requires?.{0,15}security clearance'
        r')\b',
        _re.I,
    )

    # Layer 3a – Australian federal government jobs require citizenship by law
    # APS level designations (APS1–APS6, EL1, EL2) = federal public service
    _FED_GOV_CITIZENSHIP_PATTERN = _re.compile(
        r'\b('
        r'aps\s*[1-6]\b|el\s*[12]\b|'
        r'australian government graduate program|aggp|'
        r'australian public service\b'
        r')\b',
        _re.I,
    )

    # Layer 3b – Known defence/intelligence companies where citizenship is
    # a near-certain requirement even when not stated in the teaser.
    # Uses word-boundary match (not anchors) to catch "Boeing Defence Australia", etc.
    _DEFENCE_COMPANIES = _re.compile(
        r'\b('
        r'saab|sypaq|aurizn|kinexus|anduril|'
        r'lockheed\s+martin|bae\s+systems|thales\s+australia|raytheon|'
        r'northrop\s+grumman|boeing|leidos|l3harris|frequentis|'
        r'defence\s+science\s+and\s+technology'
        r')\b',
        _re.I,
    )

    # Layer 3d – Job title explicitly says "Defence [Graduate] Program" or similar
    # → citizenship required regardless of company shown.
    _DEFENCE_TITLE_PATTERN = _re.compile(
        r'\bdefence\s+(graduate|digital|data|technology|cyber|engineering|program)\b',
        _re.I,
    )

    # Layer 3c – Known federal government agencies requiring citizenship
    _FED_GOV_COMPANIES = _re.compile(
        r'^('
        r'australian taxation office|'
        r'public service commission|'
        r'australian bureau of statistics|'
        r'department of home affairs|'
        r'australian signals directorate|'
        r'australian security intelligence organisation|'
        r'australian secret intelligence service|'  # ASIS
        r'australian federal police|'
        r'department of defence'
        r')$',
        _re.I,
    )

    _POLICE_CHECK_PATTERN = _re.compile(
        r'\bnational\s+police\s+(check|clearance)\b', _re.I
    )

    # Citizenship mentioned IN the job title itself → hard requirement (e.g. "Junior X | Australian citizen")
    _CITIZEN_IN_TITLE_PATTERN = _re.compile(
        r'australian\s+citizen(?:ship)?|citizen(?:ship)?\s+required',
        _re.I,
    )

    def _passes_visa(j) -> bool:
        combined = f"{j.title} {j.summary}"
        company  = j.company.strip()

        # National police check → explicitly 485-friendly, always keep
        if _POLICE_CHECK_PATTERN.search(combined):
            return True
        # Citizenship explicitly in job title → hard requirement
        if _CITIZEN_IN_TITLE_PATTERN.search(j.title):
            return False
        # Security clearance in title/teaser → citizenship required
        if _CLEARANCE_RESTRICT_PATTERN.search(combined):
            return False
        # Federal government APS/AGGP roles → citizenship required
        if _FED_GOV_CITIZENSHIP_PATTERN.search(combined):
            return False
        # "Defence Graduate Program / Defence Digital Pathway" in title → citizenship required
        if _DEFENCE_TITLE_PATTERN.search(j.title):
            return False
        # Known defence companies → citizenship almost certain
        if _DEFENCE_COMPANIES.search(company):
            return False
        # Known federal government employers → citizenship required
        if _FED_GOV_COMPANIES.search(company):
            return False
        # Explicit citizenship/PR restriction in text
        if _VISA_RESTRICT_PATTERN.search(combined):
            return False
        return True

    before_visa = len(all_listings)
    all_listings = [j for j in all_listings if _passes_visa(j)]
    print(
        f"[jobradar] After visa eligibility filter: {len(all_listings)} "
        f"(removed {before_visa - len(all_listings)} citizen/PR-only or clearance roles)"
    )

    if not all_listings:
        print("[jobradar] No listings remain after visa eligibility filter.")
        return

    # ── 5. Deduplicate ────────────────────────────────────────────────────────
    persist = not args.dry_run
    fresh = deduplicate(all_listings, persist=persist)

    if not fresh:
        print("[jobradar] No new listings after deduplication.")
        return

    # ── 5b. Fetch full descriptions & apply deep content filters ──────────────
    # Only run for new jobs (post-dedupe) to avoid hundreds of HTTP requests.
    # Fail-open: if a description cannot be fetched, the job is kept.
    fetch_descriptions(fresh, delay=1.5)

    # Pattern: any mention of "3 years" in an experience context → exclude.
    # Checks BOTH the teaser/title (already checked above) AND the full
    # description body, catching clauses like "Requirements: 3 years experience".
    _EXP_THREE_YEARS_FULL = _re.compile(
        r'\b3\s*\+?\s*years?\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|work\s+)?'
        r'(?:experience|exp)\b|'
        r'\b3\s*[-–]\s*\d+\s*years?\s+(?:of\s+)?(?:experience|exp)\b|'
        r'\b3\s+to\s+\d+\s*years?\s+(?:of\s+)?(?:experience|exp)\b|'
        r'\bminimum\s+(?:of\s+)?3\s*\+?\s*years?\b|'
        r'\bat\s+least\s+3\s*years?\b|'
        r'\bthree\s+(?:or\s+more\s+)?years?\s+(?:of\s+)?(?:experience|exp)\b|'
        r'\b[3-9]\+?\s*years?\s+experience\b',
        _re.I,
    )

    # Sources where description fetch is intentionally skipped — no inference possible.
    # For these, the title+teaser visa check is the only signal we have; the description
    # check passes through silently (not fail-open, just no-op).
    _SKIP_DESCRIPTION_SOURCES = {"seek.com.au", "linkedin.com"}

    def _passes_description_check(j) -> bool:
        desc = j.description

        # Intentionally skipped sources: description will never be available.
        # The full visa check already ran on title+teaser in _passes_visa.
        if not desc and any(s in j.url for s in _SKIP_DESCRIPTION_SOURCES):
            return True

        # Genuine fetch failure or very short response → fail-open (keep the job)
        if not desc or len(desc) < 100:
            return True

        # ── experience gating ────────────────────────────────────────────────
        if _EXP_THREE_YEARS_FULL.search(desc):
            print(f"[DescFilter] REMOVED (3yr exp in desc): {j.title!r} @ {j.company}")
            return False
        if _EXP_OVERQUALIFIED.search(desc):
            print(f"[DescFilter] REMOVED (overqualified exp in desc): {j.title!r} @ {j.company}")
            return False

        # ── full visa eligibility re-check against description body ──────────
        # Catches requirements buried in the JD that weren't in the teaser.
        if _VISA_RESTRICT_PATTERN.search(desc):
            print(f"[DescFilter] REMOVED (citizen/PR in desc): {j.title!r} @ {j.company}")
            return False
        if _CITIZEN_IN_TITLE_PATTERN.search(desc):
            print(f"[DescFilter] REMOVED (citizenship phrase in desc): {j.title!r} @ {j.company}")
            return False
        if _CLEARANCE_RESTRICT_PATTERN.search(desc):
            print(f"[DescFilter] REMOVED (clearance in desc): {j.title!r} @ {j.company}")
            return False
        if _FED_GOV_CITIZENSHIP_PATTERN.search(desc):
            print(f"[DescFilter] REMOVED (APS/fed-gov level in desc): {j.title!r} @ {j.company}")
            return False
        if _DEFENCE_TITLE_PATTERN.search(desc):
            print(f"[DescFilter] REMOVED (defence program in desc): {j.title!r} @ {j.company}")
            return False

        return True

    before_desc = len(fresh)
    fresh = [j for j in fresh if _passes_description_check(j)]
    print(
        f"[jobradar] After description content filter: {len(fresh)} "
        f"(removed {before_desc - len(fresh)} with 3yr-exp or citizen/PR clauses in body)"
    )

    if not fresh:
        print("[jobradar] No listings remain after description content filter.")
        return

    # ── 4. Visa scoring + resume match scoring ────────────────────────────────
    scored = score_all(fresh)
    score_all_matches(scored)

    # LinkedIn job descriptions are never fetchable (login required).
    # Flag these so the daily email shows they need a manual visa check.
    for j in scored:
        if "linkedin.com" in j.url and not j.description:
            j.visa_reason = (j.visa_reason + " [!] LinkedIn: body unverified — check manually").strip()

    # Sort: combined priority (match × 2 + visa), then title
    scored.sort(key=lambda j: (-(j.match_score * 2 + j.visa_score), j.title.lower()))

    # ── 5. Output ─────────────────────────────────────────────────────────────
    csv_path = save_csv(scored, run_date)
    html_path = save_html(scored, run_date)
    if not args.no_markdown:
        save_markdown(scored, run_date)

    # ── 6. Email / browser fallback ───────────────────────────────────────────
    email_sent = False
    skip_email = args.dry_run or args.no_email
    if not skip_email:
        email_sent = send_email(scored, csv_path, run_date)
    else:
        print("[jobradar] Email skipped (--dry-run or --no-email).")

    # Auto-open HTML report in browser if email wasn't sent
    if not email_sent and not args.dry_run and html_path and html_path.exists():
        print(f"[jobradar] Opening report in browser: {html_path}")
        subprocess.run(["open", str(html_path)], check=False)

    print(f"\n[jobradar] Done. {len(scored)} new jobs saved to output/")


def main() -> None:
    load_env()
    cfg = load_config()

    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        # Normalise --dry-run attribute name
        if not hasattr(args, "dry_run"):
            args.dry_run = False
        run_pipeline(args, cfg)
    elif args.command == "export":
        print("[jobradar] Export command not yet implemented.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
