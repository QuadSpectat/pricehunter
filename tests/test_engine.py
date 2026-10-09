from datetime import date
from decimal import Decimal

from pricehunter.landed_cost.engine import compute_landed, load_rules
from pricehunter.landed_cost.fx import StaticFx, parse_boi_xml
from pricehunter.models import Offer, ShippingOption

from .fixtures import BOI_XML

FX = StaticFx({"USD": Decimal("4.0"), "EUR": Decimal("4.4")})
RULES = load_rules("IL")


def offer(price: str, ship: str | None = "5", local: bool = False, cur: str = "USD") -> Offer:
    return Offer(
        provider="t",
        title="t",
        url="u",
        price=Decimal(price),
        currency=cur,
        local=local,
        ship_from="IL" if local else "CN",
        shipping=ShippingOption(price=Decimal(ship), currency=cur) if ship is not None else None,
    )


def test_boi_parse_takes_latest() -> None:
    assert parse_boi_xml(BOI_XML) == (Decimal("3.65"), "2026-10-08")


def test_under_threshold_no_tax() -> None:
    lc = compute_landed(offer("75"), RULES, FX)  # exactly at threshold -> exempt
    assert lc.vat == 0 and lc.total == Decimal("80")


def test_just_over_threshold_pays_vat_on_item_plus_shipping() -> None:
    lc = compute_landed(offer("75.01"), RULES, FX)
    assert lc.vat == (Decimal("75.01") + 5) * Decimal("0.18")
    assert lc.duty == 0


def test_above_duty_free_cap_applies_duty_rate() -> None:
    rules = RULES.model_copy(update={"default_duty_rate": Decimal("0.1")})
    lc = compute_landed(offer("600"), rules, FX)
    assert lc.duty == Decimal("60")
    assert lc.vat == (Decimal("600") + 60 + 5) * Decimal("0.18")


def test_unknown_shipping_is_estimated_and_flagged() -> None:
    lc = compute_landed(offer("50", ship=None), RULES, FX)
    assert lc.estimated and lc.shipping == RULES.shipping_estimate_usd


def test_local_offer_has_no_import_tax() -> None:
    lc = compute_landed(offer("1000", ship="0", local=True, cur="ILS"), RULES, FX)
    assert lc.vat == 0 and lc.total_ils == Decimal("1000")


def test_currency_conversion_and_qty() -> None:
    lc = compute_landed(offer("10", ship="2"), RULES, FX, qty=3)
    assert lc.item == 30 and lc.total_ils == Decimal("128") and lc.total_usd == Decimal("32")


def test_cif_basis_counts_shipping_toward_threshold() -> None:
    rules = RULES.model_copy(update={"threshold_basis": "cif"})
    assert compute_landed(offer("72", ship="5"), rules, FX).vat > 0
    assert compute_landed(offer("72", ship="5"), RULES, FX).vat == 0


def test_staleness_warning() -> None:
    assert RULES.staleness_warning(date(2026, 10, 10)) is not None  # secondary-source warning
    assert "older than" in (RULES.staleness_warning(date(2027, 6, 1)) or "")
    assert "NOT computed" in (load_rules("DE").staleness_warning() or "")
