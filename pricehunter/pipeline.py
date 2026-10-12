"""Orchestrates a run: resolve -> search providers -> match -> landed cost -> restrictions -> rank."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from decimal import Decimal

import httpx

from .cache import PRICE_TTL, Cache
from .costs import CostTracker
from .landed_cost.engine import compute_landed, load_rules
from .landed_cost.fx import FxRates
from .llm import Llm
from .matching.matcher import llm_verify, score_all
from .models import MatchLevel, Offer, Product, Report, ShippingOption
from .providers.base import Provider
from .ranking import add_warnings, dedupe, rank, select_display
from .restrictions.checker import RestrictionChecker


def _store_key(name: str | None) -> str:
    return re.sub(r"trader|[^a-z0-9]", "", (name or "").lower())


def same_store(a: str | None, b: str | None) -> bool:
    """True when two seller names clearly refer to the same shop (ignores case, punctuation)."""
    ka, kb = _store_key(a), _store_key(b)
    return len(ka) >= 6 and len(kb) >= 6 and (ka in kb or kb in ka)


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
    include_used: bool = False,
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
    if not include_used:
        hidden = sum(1 for o in offers if o.condition != "new")
        offers = [o for o in offers if o.condition == "new"]
        if hidden:
            report.provider_status["condition_filter"] = (
                f"hid {hidden} second-hand/refurbished listing(s); tick the box to include them"
            )
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
    ref = product.reference
    await fx.load({o.currency for o in offers} | ({ref.currency} if ref and ref.price else set()))
    for o in offers:
        o.landed = compute_landed(o, rules, fx, qty=qty, dest=dest, category=product.category)
    report.fx_note = fx.describe()
    if ref is not None and ref.price is not None:
        ship = None
        if ref.shipping is not None:
            ship = ShippingOption(price=ref.shipping, currency=ref.currency)
        ref_offer = Offer(
            provider="your_listing",
            title=product.title,
            url=product.source_url or "",
            seller=ref.store,
            price=ref.price,
            currency=ref.currency,
            shipping=ship,
            ship_from=None,
            match=MatchLevel.EXACT,
            confidence=1.0,
            match_reason="the listing in your screenshot",
        )
        ref_offer.landed = compute_landed(
            ref_offer, rules, fx, qty=qty, dest=dest, category=product.category
        )
        report.reference = ref_offer
        same = [o for o in offers if same_store(o.seller, ref.store)]
        if (
            same
        ):  # AliExpress shows its lowest-variant price: not a real alternative to your listing
            offers = [o for o in offers if all(o is not s for s in same)]
            report.provider_status["your_store"] = (
                f"skipped {len(same)} listing(s) from your own store ({ref.store}): their API price "
                "is the cheapest variant, not the one in your screenshot"
            )
        if current_price_usd is None:
            current_price_usd = float(ref_offer.landed.total_usd)
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
            cheapest_estimated=bool(
                report.cheapest and report.cheapest.landed and report.cheapest.landed.estimated
            ),
            ils_per_usd=fx.ils_per_usd(),
        )
    return report


async def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=True)
