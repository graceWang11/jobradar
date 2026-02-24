"""Deduplication engine with persistent state (JSON file)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from jobradar.core.models import JobListing

_STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "seen_jobs.json"


def _load_seen() -> set[str]:
    if _STATE_FILE.exists():
        try:
            return set(json.loads(_STATE_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def _save_seen(seen: set[str]) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")


def deduplicate(listings: List[JobListing], persist: bool = True) -> List[JobListing]:
    """
    Remove duplicates from *listings* against each other and against the
    persisted state file.  New unique jobs are added to state.

    Args:
        listings: Raw collected listings (may contain duplicates).
        persist:  Whether to update the state file with newly seen hashes.

    Returns:
        List of unique, previously-unseen listings.
    """
    seen = _load_seen()
    fresh: List[JobListing] = []
    session_seen: set[str] = set()

    for job in listings:
        key = job.hash_id
        if key in seen or key in session_seen:
            continue
        session_seen.add(key)
        fresh.append(job)

    if persist and session_seen:
        seen.update(session_seen)
        _save_seen(seen)

    print(
        f"[dedupe] {len(listings)} collected → {len(fresh)} new "
        f"(filtered {len(listings) - len(fresh)} duplicates)"
    )
    return fresh


def reset_state() -> None:
    """Clear the persistent dedup state (use with --reset flag)."""
    if _STATE_FILE.exists():
        _STATE_FILE.unlink()
        print("[dedupe] State file cleared.")
