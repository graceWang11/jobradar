"""Abstract base class for all job source connectors."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseConnector(ABC):
    """All connectors must implement fetch() and return raw job dicts."""

    name: str = "base"
    rate_limit_seconds: float = 2.0

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-AU,en;q=0.9",
    }

    @abstractmethod
    def fetch(self, locations: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Collect raw job dicts from the source.

        Each dict must contain at minimum:
            title, company, location, url, summary (optional)
        """
        ...

    def _sleep(self) -> None:
        time.sleep(self.rate_limit_seconds)
