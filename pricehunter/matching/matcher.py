"""Matching: title similarity + variant checks (+ optional LLM verification of top candidates)."""

from __future__ import annotations

import re

from ..llm import Llm
from ..models import MatchLevel, Offer, Product

_STOP = {
    "the",
    "a",
    "an",
    "for",
    "with",
    "and",
    "of",
    "in",
    "new",
    "pcs",
    "pc",
    "set",
    "free",
    "shipping",
}
_COLORS = {
    "black", "white", "red", "blue", "green", "yellow", "pink", "purple", "orange",
    "gray", "grey", "silver", "gold", "brown", "beige",
}  # fmt: skip
_PLUGS = {"eu", "us", "uk", "au"}
# Words that mark an accessory for the product rather than the product itself.
ACCESSORY_WORDS = {
    "case", "cases", "cover", "covers", "shell", "bag", "pouch", "sleeve", "protector",
    "protective", "skin", "holder", "strap", "lanyard", "sticker", "film", "silicone",
    "carrying", "storage", "base", "dock",
}  # fmt: skip


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP and len(t) > 1}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def variant_conflicts(product: Product, title: str) -> list[str]:
    """Reasons the offer clearly differs in a variant (color / plug)."""
    t = tokens(title)
    out: list[str] = []
    want_color = (product.variants.get("color") or "").lower()
    if want_color and want_color not in t:
        others = (t & _COLORS) - {want_color}
        if others and want_color in _COLORS:
            out.append(f"color differs ({', '.join(sorted(others))} vs {want_color})")
    want_plug = (product.variants.get("plug") or "").lower()
    if want_plug and want_plug in _PLUGS and want_plug not in t and (t & _PLUGS):
        out.append(f"plug type differs ({', '.join(sorted(t & _PLUGS))} vs {want_plug})")
    return out


def accessory_words(product: Product, title: str) -> set[str]:
    """Accessory words in the title that the user did not ask for."""
    asked = tokens(product.query() + " " + product.title)
    if asked & ACCESSORY_WORDS:  # the user is shopping for an accessory: don't filter
        return set()
    return tokens(title) & ACCESSORY_WORDS


def score_offer(product: Product, offer: Offer) -> Offer:
    want = tokens(product.query())
    have = tokens(offer.title)
    acc = accessory_words(product, offer.title)
    if acc:
        offer.match, offer.confidence = MatchLevel.REJECTED, 0.05
        offer.match_reason = f"looks like an accessory ({', '.join(sorted(acc))})"
        return offer
    coverage = len(want & have) / len(want) if want else 0.0
    model_hit = bool(product.model) and _norm(product.model or "") in _norm(offer.title)
    brand_hit = bool(product.brand) and (product.brand or "").lower() in offer.title.lower()

    conflicts = variant_conflicts(product, offer.title)
    if conflicts:
        offer.match, offer.confidence, offer.match_reason = (
            MatchLevel.REJECTED,
            0.1,
            "; ".join(conflicts),
        )
        return offer

    if model_hit and (brand_hit or not product.brand):
        offer.match, offer.confidence = MatchLevel.EXACT, min(0.95, 0.75 + 0.2 * coverage)
        offer.match_reason = f"model '{product.model}' found in title"
    elif coverage >= 0.75 or (model_hit and coverage >= 0.4):
        offer.match, offer.confidence = MatchLevel.LIKELY, round(0.4 + 0.4 * coverage, 2)
        offer.match_reason = f"{coverage:.0%} of product terms in title"
    elif coverage >= 0.4:
        offer.match, offer.confidence = MatchLevel.SIMILAR, round(0.2 + 0.4 * coverage, 2)
        offer.match_reason = f"only {coverage:.0%} of product terms in title"
    else:
        offer.match, offer.confidence = MatchLevel.REJECTED, round(coverage / 2, 2)
        offer.match_reason = f"title overlap too low ({coverage:.0%})"
    return offer


def score_all(product: Product, offers: list[Offer]) -> list[Offer]:
    return [score_offer(product, o) for o in offers]


async def llm_verify(product: Product, offers: list[Offer], llm: Llm, top: int = 12) -> str:
    """Ask the LLM to confirm/reject the best heuristic candidates. Mutates offers in place.

    Returns a status string for the report ("ok (n checked)" or "error: ...").
    """
    cands = [o for o in offers if o.match is not MatchLevel.REJECTED][:top]
    if not cands:
        return "skipped (no candidates)"
    listing = "\n".join(
        f"{i}. {o.title} | {o.price} {o.currency} | {o.seller}" for i, o in enumerate(cands)
    )
    try:
        result = await llm.complete_json(
            "You verify whether shop listings are the SAME product as the target. Compare brand, model, "
            "specs and variants (color/size/capacity/voltage/plug). Return a JSON list of "
            '{"i": int, "verdict": "exact|likely|similar|rejected", "reason": str}.',
            f"Target: {product.model_dump_json()}\nListings:\n{listing}",
        )
    except Exception as e:  # heuristics stand, but say so
        return f"error: {type(e).__name__}: {str(e)[:120]}"
    if not isinstance(result, list):
        return "error: unexpected AI response"
    checked = 0
    for r in result:
        try:
            o = cands[int(r["i"])]
            level = MatchLevel(r["verdict"])
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        checked += 1
        o.match = level
        o.match_reason = f"AI check: {r.get('reason', '')}"
        if level is MatchLevel.REJECTED:
            o.confidence = min(o.confidence, 0.1)
        elif level is MatchLevel.EXACT:
            o.confidence = max(o.confidence, 0.9)
    return f"ok ({checked}/{len(cands)} checked)"
