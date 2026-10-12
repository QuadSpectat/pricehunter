"""Ranking: cheapest / fastest / best value, plus suspicious-price and trust warnings."""

from __future__ import annotations

import re
from decimal import Decimal
from statistics import median

from .models import MatchLevel, Offer, Severity


def eta_days(o: Offer) -> int | None:
    s = o.shipping
    if s is None:
        return None
    return s.eta_days_max if s.eta_days_max is not None else s.eta_days_min


def add_warnings(offers: list[Offer]) -> None:
    usd = [o.landed.total_usd for o in offers if o.landed and o.match is not MatchLevel.REJECTED]
    med = Decimal(str(median(usd))) if len(usd) >= 3 else None
    for o in offers:
        if med and o.landed and o.landed.total_usd < med * Decimal("0.35"):
            o.warnings.append(
                "suspiciously cheap vs. other offers: possible fake or different product"
            )
        if o.landed and o.landed.estimated:
            o.warnings.append("total includes estimated values (shipping/taxes)")
        if o.confidence < 0.4 and o.match is not MatchLevel.REJECTED:
            o.warnings.append("low-confidence match")
        if o.rating is not None and o.rating < 3.5:
            o.warnings.append(f"low seller rating ({o.rating})")
        if any(r.severity is Severity.BLOCKED for r in o.restrictions):
            o.warnings.append("likely restricted into destination - verify with customs")


def _total(o: Offer) -> Decimal:
    assert o.landed
    return o.landed.total_usd


def _value_score(o: Offer, cheapest: Decimal) -> float:
    assert o.landed
    price_part = float(cheapest / o.landed.total_usd) if o.landed.total_usd else 0.0
    eta = eta_days(o)
    speed_part = 0.5 if eta is None else max(0.0, 1 - eta / 45)
    trust_part = 0.5 if o.rating is None else o.rating / 5
    penalty = 0.5 if any(r.severity is Severity.BLOCKED for r in o.restrictions) else 1.0
    return (0.5 * price_part + 0.2 * speed_part + 0.15 * trust_part + 0.15 * o.confidence) * penalty


def rank(
    offers: list[Offer], *, min_confidence: float = 0.0
) -> tuple[list[Offer], Offer | None, Offer | None, Offer | None]:
    """Return (sorted offers, cheapest, fastest, best_value). Rejected/unpriced offers are dropped."""
    ok = [
        o for o in offers
        if o.landed and o.match is not MatchLevel.REJECTED and o.confidence >= min_confidence
    ]  # fmt: skip
    if not ok:
        return [], None, None, None
    ok.sort(key=_total)
    cheapest = ok[0]
    with_eta = [o for o in ok if eta_days(o) is not None]
    fastest = min(with_eta, key=lambda o: (eta_days(o) or 0, _total(o))) if with_eta else None
    base = _total(cheapest)
    best = max(ok, key=lambda o: _value_score(o, base))
    return ok, cheapest, fastest, best


def dedupe(offers: list[Offer]) -> list[Offer]:
    """Drop repeated listings (same normalized title, price, currency and seller)."""
    seen: set[tuple[str, str, str, str | None]] = set()
    out: list[Offer] = []
    for o in offers:
        key = (re.sub(r"[^a-z0-9]", "", o.title.lower()), str(o.price), o.currency, o.seller)
        if key not in seen:
            seen.add(key)
            out.append(o)
    return out


def select_display(ranked: list[Offer], limit: int) -> list[Offer]:
    """Pick up to `limit` offers so one provider cannot crowd out the others.

    Each provider gets an equal share first; leftover slots go to the cheapest remaining.
    """
    providers = list(dict.fromkeys(o.provider for o in ranked))
    if not providers:
        return []
    share = max(1, limit // len(providers))
    counts: dict[str, int] = {}
    chosen: list[Offer] = []
    rest: list[Offer] = []
    for o in ranked:
        if counts.get(o.provider, 0) < share:
            counts[o.provider] = counts.get(o.provider, 0) + 1
            chosen.append(o)
        else:
            rest.append(o)
    chosen += rest[: max(0, limit - len(chosen))]
    chosen.sort(key=_total)
    return chosen[:limit]
