from __future__ import annotations

from ..models import Offer, Report


def _money(v: object) -> str:
    return f"{float(v):,.2f}"  # type: ignore[arg-type]


def _row(o: Offer) -> str:
    assert o.landed
    la = o.landed
    flag = "~" if la.estimated else ""
    restr = ", ".join(sorted({f"{r.severity.value}:{r.code}" for r in o.restrictions})) or "-"
    return (
        f"| {o.provider} | [{o.title[:60]}]({o.url}) | {o.match.value} ({o.confidence:.0%}) "
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
    picks = [("Cheapest", r.cheapest), ("Fastest", r.fastest), ("Best value", r.best_value)]
    lines += ["", "## Picks"]
    for label, o in picks:
        if o and o.landed:
            lines.append(
                f"- **{label}:** [{o.title[:70]}]({o.url}) ({o.provider}), {_money(o.landed.total_ils)} ILS"
            )
        else:
            lines.append(f"- **{label}:** n/a (no data)")
    lines += [
        "", "## Offers", "",
        "| Provider | Listing | Match | Item | Shipping | Taxes/fees | Total | Restrictions |",
        "|---|---|---|---|---|---|---|---|",
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
