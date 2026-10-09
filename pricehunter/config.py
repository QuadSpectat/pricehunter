"""Settings loaded from environment / .env. Secrets are never logged."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = ""
    model: str = "claude-sonnet-5-5"
    serpapi_key: str = ""
    aliexpress_app_key: str = ""
    aliexpress_app_secret: str = ""
    ebay_client_id: str = ""
    ebay_client_secret: str = ""
    cache_path: Path = Path("cache.sqlite")

    def __repr__(self) -> str:  # never leak secrets
        return "Settings(<redacted>)"


def load_settings(env_file: Path | None = None) -> Settings:
    _load_dotenv(env_file or Path(".env"))
    g = os.environ.get
    return Settings(
        anthropic_api_key=g("ANTHROPIC_API_KEY", ""),
        model=g("PRICEHUNTER_MODEL", "claude-sonnet-5-5"),
        serpapi_key=g("SERPAPI_KEY", ""),
        aliexpress_app_key=g("ALIEXPRESS_APP_KEY", ""),
        aliexpress_app_secret=g("ALIEXPRESS_APP_SECRET", ""),
        ebay_client_id=g("EBAY_CLIENT_ID", ""),
        ebay_client_secret=g("EBAY_CLIENT_SECRET", ""),
        cache_path=Path(g("PRICEHUNTER_CACHE", "cache.sqlite")),
    )
