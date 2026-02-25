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

from jobradar.config.loader import load_config, load_env, get_locations
from jobradar.connectors.adzuna import AdzunaConnector
from jobradar.connectors.company_careers import CompanyCareersConnector
from jobradar.connectors.email_alerts import EmailAlertsConnector
from jobradar.connectors.govt_careers import GovtCareersConnector
from jobradar.connectors.gradconnection import GradConnectionConnector
from jobradar.connectors.indeed import IndeedConnector
from jobradar.connectors.jora import JoraConnector
from jobradar.connectors.linkedin import LinkedInConnector
from jobradar.connectors.prosple import ProspleConnector
from jobradar.connectors.seek import SeekConnector
from jobradar.core.dedupe import deduplicate, reset_state
from jobradar.core.models import JobListing
from jobradar.core.normalize import normalize_many
from jobradar.core.output import save_csv, save_html, save_markdown
from jobradar.core.visa_scoring import score_all
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
            "architect",
            # Program / domain signals
            "technology graduate", "tech graduate", "technology program",
            "technology internship", "tech internship",
            "software",          # software alone is unambiguous
            "technology",        # "Graduate – Technology", "Technology Graduate Program"
            "data",              # "Data & Analytics Graduate Program"
            "analytics",         # "Data & Analytics"
            "digital",           # "Digital Graduate Program"
            "information technology", "information systems",
        ]
    ]

    # Non-IT exclusion: if title contains these words AND no strong IT signal,
    # it is likely a civil/mining/finance role — skip it.
    _NON_IT_TITLE_WORDS = _re.compile(
        r'\b(civil|mechanical|hydro|structural|geotechnical|mining|'
        r'chemical|electrical wiring|audit|accounting|actuari|'
        r'banking|finance|financial planning|wealth|insurance|legal|law|'
        r'nursing|medical|pharmacy|physiother|dental|clinical)\b',
        _re.I,
    )

    # Senior-level exclusion: always drop these regardless of tech role match.
    _SENIOR_TITLE_WORDS = _re.compile(
        r'\b(senior|sr\b|lead|principal|staff|manager|director|'
        r'head of|vp|vice president|chief|experienced|mid.?level)\b',
        _re.I,
    )

    # Strong standalone IT titles that pass without needing a level keyword.
    # These are unambiguous enough that any result from our junior/grad searches is worth showing.
    _STRONG_TECH_TITLES = _re.compile(
        r'\b(software engineer|software developer|full.?stack|fullstack|'
        r'devops|backend|frontend|web developer|mobile developer|'
        r'data engineer|data analyst|data scientist|cloud engineer|'
        r'platform engineer|machine learning engineer|ml engineer|'
        r'systems engineer|network engineer|cyber|cybersecurity|'
        r'developer|programmer)\b',
        _re.I,
    )

    def _is_relevant(j) -> bool:
        title      = j.title.lower()
        summary    = j.summary.lower()
        combined   = f"{title} {summary}"
        has_non_it = bool(_NON_IT_TITLE_WORDS.search(title))
        has_senior = bool(_SENIOR_TITLE_WORDS.search(title))
        if has_non_it or has_senior:
            return False
        # Company & govt career pages are pre-targeted — only need an IT role, no level keyword
        if j.source in ("CompanyCareers", "GovtCareers"):
            return any(p.search(combined) for p in _TECH_ROLE_PATTERNS)
        has_level   = any(p.search(combined) for p in _LEVEL_PATTERNS)
        has_role    = any(p.search(combined) for p in _TECH_ROLE_PATTERNS)
        strong_tech = bool(_STRONG_TECH_TITLES.search(title))
        return (has_role or strong_tech) and (has_level or strong_tech)

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

    # ── 5. Deduplicate ────────────────────────────────────────────────────────
    persist = not args.dry_run
    fresh = deduplicate(all_listings, persist=persist)

    if not fresh:
        print("[jobradar] No new listings after deduplication.")
        return

    # ── 4. Visa scoring ───────────────────────────────────────────────────────
    scored = score_all(fresh)
    # Sort: high visa score first, then alphabetically by title
    scored.sort(key=lambda j: (-j.visa_score, j.title.lower()))

    # ── 5. Output ─────────────────────────────────────────────────────────────
    csv_path = save_csv(scored, run_date)
    save_html(scored, run_date)
    if not args.no_markdown:
        save_markdown(scored, run_date)

    # ── 6. Email ──────────────────────────────────────────────────────────────
    skip_email = args.dry_run or args.no_email
    if not skip_email:
        send_email(scored, csv_path, run_date)
    else:
        print("[jobradar] Email skipped (--dry-run or --no-email).")

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
