"""One entry point used by both the CLI and the GUI: resolve -> search -> cost ledger."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx

from .cache import Cache
from .config import Settings
from .costs import record_run, tracker_from_settings
from .landed_cost.fx import FxRates
from .llm import Llm
from .models import Product, Report
from .pipeline import run_search
from .providers import build_providers
from .resolver import resolve


@dataclass
class SearchOptions:
    dest: str = "IL"
    max_results: int = 15
    include_local: bool = True
    include_global: bool = True
    qty: int = 1
    no_ai: bool = False
    current_price_usd: float | None = None
    ship_estimate_usd: float | None = None


async def execute_search(
    query: str,
    settings: Settings,
    options: SearchOptions | None = None,
    progress: Callable[[str], None] = lambda _msg: None,
    on_product: Callable[[Product], None] = lambda _p: None,
) -> Report:
    """Run a full search for a URL, image path or text and log its cost."""
    o = options or SearchOptions()
    s = settings
    cache = Cache(s.cache_path)
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            tracker = tracker_from_settings(
                s.model, s.price_in_per_mtok, s.price_out_per_mtok, s.serpapi_cost_per_search
            )
            llm = None
            if s.anthropic_api_key and not o.no_ai:
                llm = Llm(s.anthropic_api_key, s.model, tracker)
            progress("resolving product...")
            product = await resolve(query, client, llm)
            on_product(product)
            report = await run_search(
                product,
                build_providers(s, client),
                fx=FxRates(client, cache),
                dest=o.dest.upper(),
                qty=o.qty,
                limit=o.max_results,
                include_local=o.include_local,
                include_global=o.include_global,
                llm=llm,
                cache=cache,
                progress=progress,
                query=query,
                tracker=tracker,
                current_price_usd=o.current_price_usd,
                ship_estimate_usd=o.ship_estimate_usd,
            )
        if report.cost is not None:
            record_run(s.ledger_path, query, report.cost)
        return report
    finally:
        cache.close()
