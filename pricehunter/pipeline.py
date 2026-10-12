"""Orchestrates a run: resolve -> search providers -> match -> landed cost -> restrictions -> rank."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from decimal import Decimal

import httpx

from .cache import PRICE_TTL, Cache
from .costs import CostTracker
from .landed_cost.engine import compute_landed, load_rules
from .landed_cost.fx import FxRates
from .llm import Llm
from .matching.matcher import llm_verify, score_all
from .models import Offer, Product, Report
from .providers.base import Provider
from .ranking import add_warnings, dedupe, rank, select_display
from .restrictions.checker import RestrictionChecker


async def run_search(
    product: Product,
    providers: list[Provider],
    *,
    fx: FxRates,
    dest: str = "IL",
    qty: int = 1,
    limit: int = 15,
    include_local: bool = True,
    include_global: bool = True,
    llm: Llm | None = None,
    cache: Cache | None = None,
    checker: RestrictionChecker | None = None,
    progress: Callable[[str], None] = lambda _msg: None,
    query: str = "",
    tracker: CostTracker | None = None,
    current_price_usd: float | None = None,
    ship_estimate_usd: float | None = None,
) -> Report:
    report = Report(query=query or product.query(), product=product, destination=dest)

    async def one(p: Provider) -> tuple[Provider, list[Offer], str]:
        key = f"offers:{p.name}:{dest}:{product.query()}"
        if cache and (hit := cache.get(key)):
            return p, [Offer.model_validate(o) for o in hit], "ok (cached)"
        offers, status = await p.safe_search(product, dest=dest, limit=limit)
        if cache and status.startswith("ok"):
            cache.set(key, [o.model_dump(mode="json") for o in offers], PRICE_TTL)
        return p, offers, status

    progress("searching providers...")
    results = await asyncio.gather(*(one(p) for p in providers))
    offers: list[Offer] = []
    for p, found, status in results:
        report.provider_status[p.name] = status
        offers.extend(found)

    offers = [o for o in offers if (o.local and include_local) or (not o.local and include_global)]
    if not offers:
        report.warnings.append("no offers found (check `pricehunter providers` for configuration)")

    progress("matching...")
    offers = dedupe(offers)
    offers = score_all(product, offers)
    offers.sort(key=lambda o: -o.confidence)
    if llm:
        report.provider_status["ai_match"] = await llm_verify(product, offers, llm)

    progress("computing landed cost...")
    rules = load_rules(dest)
    if ship_estimate_usd is not None:
        rules = rules.model_copy(update={"shipping_estimate_usd": Decimal(str(ship_estimate_usd))})
    await fx.load({o.currency for o in offers})
    for o in offers:
        o.landed = compute_landed(o, rules, fx, qty=qty, dest=dest, category=product.category)
    report.fx_note = fx.describe()
    if (w := rules.staleness_warning()) is not None:
        report.rules_note = w

    progress("checking restrictions...")
    checker = checker or RestrictionChecker()
    if llm:
        await checker.classify_product(product, llm)
    for o in offers:
        o.restrictions = checker.check(o, product, dest)

    add_warnings(offers)
    ranked, report.cheapest, report.fastest, report.best_value = rank(offers)
    report.offers = select_display(ranked, limit)
    if tracker is not None:
        tracker.add_serp(sum(p.paid_calls for p in providers))
        report.cost = tracker.summary(
            [o.landed.total_usd for o in ranked if o.landed],
            current_price_usd=current_price_usd,
            generic=not product.model,
            ils_per_usd=fx.ils_per_usd(),
        )
    return report


async def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=True)
