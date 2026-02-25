"""Government careers connector.

SA Government, VIC Government, and Federal (APS) jobs are covered via
targeted Seek searches in seek.py — government portals use JS-rendered
pages with no public API.

This module is kept as a stub so the import in __main__.py doesn't break.
It returns 0 results (all work is done by SeekConnector._COMPANY_SEARCHES).
"""

from __future__ import annotations

from jobradar.connectors.base import BaseConnector


class GovtCareersConnector(BaseConnector):
    """Stub — government jobs sourced via Seek targeted searches."""

    rate_limit_seconds: float = 0.0

    def fetch(self, locations: list[str], keywords: list[str]) -> list[dict]:
        print("[GovtCareers] Using Seek targeted searches for government jobs.")
        return []
