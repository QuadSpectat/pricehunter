"""Landed-cost engine. All tax parameters come from rules YAML, never hardcoded."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from ..models import LandedCost, Offer
from .fx import FxRates

RULES_DIR = Path(__file__).parent / "rules"
STALE_DAYS = 90


class TaxRules(BaseModel):
    country: str
    currency: str
    last_verified: date
    verified_against: str = "unknown"
    sources: list[str] = Field(default_factory=list)
    vat_rate: Decimal
    de_minimis_usd: Decimal
    threshold_basis: Literal["goods", "cif"] = "goods"
    vat_includes_shipping: bool = True
    duty_free_up_to_usd: Decimal
    default_duty_rate: Decimal = Decimal(0)
    duty_by_category: dict[str, Decimal] = Field(default_factory=dict)
    handling_fee_usd: Decimal = Decimal(0)
    shipping_estimate_usd: Decimal = Decimal(10)
    local_prices_include_vat: bool = True

    def staleness_warning(self, today: date | None = None) -> str | None:
        today = today or date.today()
        if self.country == "GENERIC":
            return "No tax rules for this destination: import taxes were NOT computed."
        if today - self.last_verified > timedelta(days=STALE_DAYS):
            return (
                f"verify: {self.country} tax rules last verified {self.last_verified} "
                f"(older than {STALE_DAYS} days)"
            )
        if self.verified_against != "gov.il":
            return (
                f"verify: {self.country} tax rules come from '{self.verified_against}', "
                "not an official source - confirm before relying on them"
            )
        return None


def load_rules(dest: str, rules_dir: Path = RULES_DIR) -> TaxRules:
    path = rules_dir / f"{dest.lower()}.yaml"
    if dest.upper() == "IL":
        path = rules_dir / "israel.yaml"
    if not path.is_file():
        path = rules_dir / "generic.yaml"
    return TaxRules.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def compute_landed(
    offer: Offer,
    rules: TaxRules,
    fx: FxRates,
    *,
    qty: int = 1,
    dest: str = "IL",
    category: str | None = None,
) -> LandedCost:
    """Compute landed cost for `qty` units of the offer, in the offer's currency and USD/ILS."""
    cur = offer.currency
    notes: list[str] = []
    estimated = False

    item = offer.price * qty
    if qty > 1:
        notes.append(f"shipping assumed unchanged for {qty} units (verify)")

    if offer.shipping is not None and offer.shipping.price is not None:
        ship = fx.from_usd(fx.to_usd(offer.shipping.price, offer.shipping.currency), cur)
        estimated = estimated or offer.shipping.estimated
    elif offer.local:
        ship = Decimal(0)
        notes.append("shipping not listed for local store; assumed 0 (verify at checkout)")
        estimated = True
    else:
        ship = fx.from_usd(rules.shipping_estimate_usd, cur)
        notes.append("shipping unknown: ESTIMATED from rules file")
        estimated = True

    vat = duty = fees = Decimal(0)
    is_import = not offer.local and (offer.ship_from or "").upper() != dest.upper()
    if is_import:
        goods_usd = fx.to_usd(item, cur)
        ship_usd = fx.to_usd(ship, cur)
        basis_usd = goods_usd + (ship_usd if rules.threshold_basis == "cif" else Decimal(0))
        if basis_usd <= rules.de_minimis_usd:
            notes.append(f"under {rules.de_minimis_usd} USD exemption: no import taxes")
        else:
            if goods_usd > rules.duty_free_up_to_usd:
                rate = rules.duty_by_category.get(category or "", rules.default_duty_rate)
                duty = item * rate
                notes.append(f"duty at {rate:.0%} (rate from rules file; verify HS code)")
            vat_base = item + duty + (ship if rules.vat_includes_shipping else Decimal(0))
            vat = vat_base * rules.vat_rate
            fees = fx.from_usd(rules.handling_fee_usd, cur)
            notes.append(f"VAT {rules.vat_rate:.0%} applied (above exemption)")
    elif offer.local and rules.local_prices_include_vat:
        notes.append("local price assumed to include VAT")

    total = item + ship + vat + duty + fees
    return LandedCost(
        item=item,
        shipping=ship,
        vat=vat,
        duty=duty,
        fees=fees,
        total=total,
        total_usd=fx.to_usd(total, cur),
        total_ils=fx.to_ils(total, cur),
        currency_note=cur,
        estimated=estimated,
        notes=notes,
    )
