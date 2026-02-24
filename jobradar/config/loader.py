"""Config and environment loading."""

import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Load .env from project root (silently skips if missing)."""
    env_path = _ROOT / ".env"
    load_dotenv(env_path)


def load_config(config_path: Path | None = None) -> Dict[str, Any]:
    """Load config.yaml from the project root (or a custom path)."""
    path = config_path or (_ROOT / "config.yaml")
    if not path.exists():
        raise FileNotFoundError(f"config.yaml not found at {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_all_keywords(cfg: Dict[str, Any]) -> list[str]:
    """Flatten all role keywords into a single list."""
    roles = cfg.get("keywords", {}).get("roles", {})
    keywords = []
    for category in roles.values():
        keywords.extend(category)
    return keywords


def get_locations(cfg: Dict[str, Any]) -> list[str]:
    return cfg.get("locations", {}).get("primary", [])
