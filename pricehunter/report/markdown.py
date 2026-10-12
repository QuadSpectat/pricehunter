from __future__ import annotations

from ..models import Offer, Report


def _link(text: str, url: str) -> str:
    safe = url.replace(" ", "%20").replace("(", "%28").replace(")", "%29").replace("|", "%7C")
    return f"[{text.replace('|', '/')}]({safe})"


def _money(v: object) -> str:
    return f"{float(v):,.2f}"  # type: ignore[arg-type]


def _row(o: Offer) -> str:
    assert o.landed
    la = o.landed
    flag = "~" if la.estimated else ""
    restr = ", ".join(sorted({f"{r.severity.value}:{r.code}" for r in o.restrictions})) or "-"
    cond = "" if o.condition == "new" else f" **[{o.condition.upper()}]**"
    return (
        f"| {o.provider} | {(o.seller or '-').replace('|', '/')} | {_link(o.title[:60], o.url)}{cond} | {o.match.value} ({o.confidence:.0%}) "
        f"| {_money(la.item)} {o.currency} | {flag}{_money(la.shipping)} | {_money(la.vat + la.duty + la.fees)} "
        f"| **{flag}{_money(la.total_ils)} ILS** / {flag}{_money(la.total_usd)} USD | {restr} |"
    )


def to_markdown(r: Report) -> str:
    lines = [f"# PriceHunter: {r.product.title}", ""]
    lines.append(
        f"Destination: **{r.destination}** · Query: `{r.query}` · {r.created_at:%Y-%m-%d %H:%M} UTC"
    )
    if r.rules_note:
        lines += ["", f"> ⚠ {r.rules_note}"]
    for w in r.warnings:
        lines += ["", f"> ⚠ {w}"]
    if r.cost is not None:
        c = r.cost
        ils = f" (~{c.total_usd * c.ils_per_usd:.2f} ILS)" if c.ils_per_usd else ""
        lines += ["", "## Search cost"]
        lines.append(
            f"- This search: **${c.total_usd:.3f}**{ils} = SerpAPI {c.serp_calls} call(s) "
            f"${c.serpapi_usd:.3f} + Claude {c.tokens_in:,} in / {c.tokens_out:,} out tokens "
            f"${c.llm_usd:.3f}"
        )
        if c.potential_saving_usd is not None:
            lines.append(f"- Potential saving: ${c.potential_saving_usd:.2f} ({c.saving_basis})")
        lines.append(f"- **{c.verdict}**")
        if c.cumulative_searches:
            lines.append(
                f"- Running total: ${c.cumulative_cost_usd:.2f} over {c.cumulative_searches} search(es)"
            )
        lines.append("- Estimates from list prices; searches served from cache cost nothing.")
    if r.reference is not None and r.reference.landed is not None:
        ro, la = r.reference, r.reference.landed
        ship = (
            "shipping not visible (estimated)"
            if ro.shipping is None
            else (
                "free shipping"
                if not ro.shipping.price
                else f"shipping {_money(ro.shipping.price)} {ro.currency}"
            )
        )
        store = ro.seller or "unknown store"
        lines += ["", "## Your listing (from your screenshot)"]
        lines.append(
            f"- {store}: {_money(ro.price)} {ro.currency}, {ship} -> landed "
            f"**{'~' if la.estimated else ''}{_money(la.total_ils)} ILS** / {_money(la.total_usd)} USD"
        )
        lines.append("- This is the baseline the savings are measured against.")
    picks = [("Cheapest", r.cheapest), ("Fastest", r.fastest), ("Best value", r.best_value)]
    lines += ["", "## Picks"]
    for label, o in picks:
        if o and o.landed:
            lines.append(
                f"- **{label}:** {_link(o.title[:70], o.url)} ({o.provider}), {_money(o.landed.total_ils)} ILS"
            )
        else:
            lines.append(f"- **{label}:** n/a (no data)")
    lines += [
        "", "## Offers", "",
        "| Provider | Store | Listing | Match | Item | Shipping | Taxes/fees | Total | Restrictions |",
        "|---|---|---|---|---|---|---|---|---|",
    ]  # fmt: skip
    lines += [_row(o) for o in r.offers]
    lines += ["", "`~` = includes estimated values.", ""]
    for o in r.offers:
        notes = o.warnings + o.landed.notes if o.landed else o.warnings
        if notes or o.restrictions:
            lines.append(f"### {o.title[:70]} ({o.provider})")
            lines += [f"- {n}" for n in notes]
            lines += [f"- [{x.severity.value}] {x.reason}" for x in o.restrictions]
            lines.append("")
    lines += ["## Data notes", f"- FX: {r.fx_note or 'n/a'}"]
    lines += [f"- Provider {k}: {v}" for k, v in r.provider_status.items()]
    lines.append("- Tax and restriction information is indicative only: verify with customs.")
    return "\n".join(lines) + "\n"
