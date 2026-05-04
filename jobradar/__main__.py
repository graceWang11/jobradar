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
import subprocess
import sys
from datetime import date
from typing import List

from jobradar.config.loader import load_config, load_env, get_locations
from jobradar.connectors.adzuna import AdzunaConnector
from jobradar.connectors.ashby import AshbyConnector
from jobradar.connectors.builtin import BuiltInConnector
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
from jobradar.connectors.smartrecruiters import SmartRecruitersConnector
from jobradar.connectors.workday import WorkdayConnector
from jobradar.core.dedupe import deduplicate, reset_state
from jobradar.core.description_fetcher import fetch_descriptions
from jobradar.core.email_sender import send_email
from jobradar.core.filters import (
    apply_description_filter,
    apply_location_filter,
    apply_relevance_filter,
    apply_resume_filter,
    apply_visa_filter,
)
from jobradar.core.models import JobListing
from jobradar.core.normalize import normalize_many
from jobradar.core.output import save_csv, save_html, save_markdown
from jobradar.core.recruiter import enrich_all
from jobradar.core.resume_scorer import score_all_matches
from jobradar.core.visa_scoring import score_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobradar",
        description="Junior/grad tech job aggregator – Adelaide & Melbourne",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Collect, process, and send jobs")
    run_parser.add_argument("--since", default="24h",
                            help="Recency filter (e.g. 24h, 7d) – informational for now")
    run_parser.add_argument("--city", default=None,
                            help="Limit to one city: adelaide or melbourne")
    run_parser.add_argument("--dry-run", action="store_true",
                            help="Run pipeline but skip email send and dedup persistence")
    run_parser.add_argument("--no-email", action="store_true",
                            help="Skip email delivery")
    run_parser.add_argument("--reset", action="store_true",
                            help="Clear the dedupe state before running")
    run_parser.add_argument("--no-markdown", action="store_true",
                            help="Skip Markdown output")

    subparsers.add_parser("export", help="Re-export last run's data (not yet implemented)")
    return parser


def _collect(cfg: dict, locations: List[str]) -> List[JobListing]:
    """Run all enabled connectors and return combined raw listings."""
    sources = cfg.get("sources", {})
    keywords: List[str] = []
    all_listings: List[JobListing] = []

    def _run(key: str, connector_cls, default_enabled: bool = True):
        src_cfg = sources.get(key, {})
        if not src_cfg.get("enabled", default_enabled):
            return
        connector = connector_cls()
        connector.rate_limit_seconds = src_cfg.get(
            "rate_limit_seconds", connector.rate_limit_seconds
        )
        raw = connector.fetch(locations, keywords)
        all_listings.extend(normalize_many(raw, connector.name))

    _run("prosple",          ProspleConnector)
    _run("gradconnection",   GradConnectionConnector)
    _run("seek",             SeekConnector)
    _run("linkedin",         LinkedInConnector)
    _run("adzuna",           AdzunaConnector)
    _run("company_careers",  CompanyCareersConnector)
    _run("govt_careers",     GovtCareersConnector)
    _run("greenhouse",       GreenhouseConnector)
    _run("ashby",            AshbyConnector)
    _run("smartrecruiters",  SmartRecruitersConnector)
    _run("workday",          WorkdayConnector)
    _run("builtin",          BuiltInConnector)
    _run("jora",             JoraConnector,          default_enabled=False)
    _run("lever",            LeverConnector,         default_enabled=False)
    _run("email_alerts",     EmailAlertsConnector,   default_enabled=False)

    print(f"\n[jobradar] Total collected: {len(all_listings)} listings")
    return all_listings


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

    # ── 2. Collect ────────────────────────────────────────────────────────────
    all_listings = _collect(cfg, locations)
    if not all_listings:
        print("[jobradar] No listings found. Check connectors or try again later.")
        return

    # ── 3. Pipeline filters ───────────────────────────────────────────────────
    include_remote = cfg.get("filters", {}).get("include_remote", False)

    all_listings = apply_location_filter(all_listings, locations, include_remote)
    if not all_listings:
        print("[jobradar] No listings remain after location filter.")
        return

    all_listings = apply_relevance_filter(all_listings)
    if not all_listings:
        print("[jobradar] No listings remain after relevance filter.")
        return

    all_listings = apply_resume_filter(all_listings)
    if not all_listings:
        print("[jobradar] No listings remain after resume fit filter.")
        return

    all_listings = apply_visa_filter(all_listings)
    if not all_listings:
        print("[jobradar] No listings remain after visa eligibility filter.")
        return

    # ── 4. Deduplicate ────────────────────────────────────────────────────────
    fresh = deduplicate(all_listings, persist=not args.dry_run)
    if not fresh:
        print("[jobradar] No new listings after deduplication.")
        return

    # ── 5. Fetch descriptions + deep content filter ───────────────────────────
    fetch_descriptions(fresh, delay=1.5)
    fresh = apply_description_filter(fresh)
    if not fresh:
        print("[jobradar] No listings remain after description content filter.")
        return

    # ── 6. Score + enrich ─────────────────────────────────────────────────────
    scored = score_all(fresh)
    score_all_matches(scored)
    enrich_all(scored)

    # LinkedIn body-unverified flag (login required — can't fetch description)
    for j in scored:
        if "linkedin.com" in j.url and not j.description:
            j.visa_reason = (
                j.visa_reason + " [!] LinkedIn: body unverified — check manually"
            ).strip()

    # Sort: combined priority (match × 2 + visa), then title
    scored.sort(key=lambda j: (-(j.match_score * 2 + j.visa_score), j.title.lower()))

    # ── 7. Output ─────────────────────────────────────────────────────────────
    csv_path = save_csv(scored, run_date)
    html_path = save_html(scored, run_date)
    if not args.no_markdown:
        save_markdown(scored, run_date)

    # ── 8. Email / browser fallback ───────────────────────────────────────────
    email_sent = False
    if not (args.dry_run or args.no_email):
        email_sent = send_email(scored, csv_path, run_date)
    else:
        print("[jobradar] Email skipped (--dry-run or --no-email).")

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
        if not hasattr(args, "dry_run"):
            args.dry_run = False
        run_pipeline(args, cfg)
    elif args.command == "export":
        print("[jobradar] Export command not yet implemented.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
