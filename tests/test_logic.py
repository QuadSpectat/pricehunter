from decimal import Decimal
from pathlib import Path

from pricehunter.landed_cost.engine import compute_landed, load_rules
from pricehunter.landed_cost.fx import StaticFx
from pricehunter.matching.matcher import score_offer
from pricehunter.models import MatchLevel, Offer, Product, Severity, ShippingOption
from pricehunter.ranking import add_warnings, rank
from pricehunter.resolver import detect_kind
from pricehunter.resolver.url_resolver import extract_page_facts, title_from_slug
from pricehunter.restrictions.checker import RestrictionChecker

P = Product(title="Anker 737 Power Bank", brand="Anker", model="A1289", variants={"color": "black"})


def o(title: str, price: str = "50") -> Offer:
    return Offer(provider="t", title=title, url="u", price=Decimal(price))


def test_match_levels() -> None:
    assert score_offer(P, o("Anker A1289 power bank 24000mAh black")).match is MatchLevel.EXACT
    likely = score_offer(P, o("Anker 737 Power Bank charger")).match
    assert likely in (MatchLevel.LIKELY, MatchLevel.EXACT)
    assert score_offer(P, o("Garden hose 10m")).match is MatchLevel.REJECTED


def test_variant_conflict_rejected() -> None:
    r = score_offer(P, o("Anker 737 Power Bank white"))
    assert r.match is MatchLevel.REJECTED and "color" in r.match_reason


def test_restrictions_keywords_and_word_boundary() -> None:
    c = RestrictionChecker()
    codes = {r.code for r in c.check(o("Anker power bank 24000mAh bluetooth"), P)}
    assert {"lithium_battery", "radio_wireless"} <= codes
    assert c.check(o("Anker power bank"), P, dest="US") == []
    # 'gun' must not match inside 'gunmetal'
    assert "weapons" not in {r.code for r in c.check(o("gunmetal case"), Product(title="case"))}
    blocked = c.check(o("vape pen"), Product(title="vape pen"))
    assert any(r.severity is Severity.BLOCKED for r in blocked)


def _ranked(prices: list[tuple[str, str, int | None]]) -> list[Offer]:
    fx = StaticFx({"USD": Decimal(4)})
    rules = load_rules("IL")
    out = []
    for title, price, eta in prices:
        x = o(title, price)
        x.match, x.confidence = MatchLevel.EXACT, 0.9
        x.shipping = ShippingOption(price=Decimal(0), eta_days_max=eta)
        x.landed = compute_landed(x, rules, fx)
        out.append(x)
    return out


def test_rank_picks_and_suspicious_price() -> None:
    offers = _ranked([("a", "100", 30), ("b", "120", 5), ("c", "110", 10), ("d", "20", 20)])
    add_warnings(offers)
    ranked, cheapest, fastest, best = rank(offers)
    assert cheapest and cheapest.title == "d" and fastest and fastest.title == "b" and best
    assert any("suspiciously" in w for w in offers[3].warnings)
    assert ranked[0].title == "d"


def test_rank_empty() -> None:
    assert rank([]) == ([], None, None, None)


def test_detect_kind(tmp_path: Path) -> None:
    img = tmp_path / "x.jpg"
    img.write_bytes(b"x")
    assert detect_kind("https://a.com/p") == "url"
    assert detect_kind(str(img)) == "image"
    assert detect_kind("anker power bank") == "text"


def test_url_page_facts_and_slug() -> None:
    html = (
        '<html><title>Foo &amp; Bar</title><meta property="og:title" content="OG Foo">'
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"N","brand":{"name":"B"},"mpn":"M1"}</script></html>'
    )
    f = extract_page_facts(html)
    assert f["title"] == "Foo & Bar" and f["og:title"] == "OG Foo"
    assert f["ld_brand"] == "B" and f["ld_model"] == "M1"
    assert title_from_slug("https://x.com/item/anker-737-power-bank.html") == "anker 737 power bank"


def test_accessory_rejected_unless_requested() -> None:
    power_bank = Product(title="Anker power bank", brand="Anker")
    case = score_offer(power_bank, o("Silicone Case for Anker 10000mAh Power Bank"))
    assert case.match is MatchLevel.REJECTED and "accessory" in case.match_reason
    real = score_offer(power_bank, o("Anker PowerCore 10000 Power Bank"))
    assert real.match is not MatchLevel.REJECTED
    wanted = Product(title="Anker power bank case", brand="Anker")
    assert (
        score_offer(wanted, o("Silicone Case for Anker Power Bank")).match
        is not MatchLevel.REJECTED
    )


def test_dedupe_and_balanced_display() -> None:
    from pricehunter.ranking import dedupe, select_display

    a = o("Anker Nano Power Bank", "30")
    assert len(dedupe([a, a.model_copy(), o("Other", "30")])) == 2
    offers = _ranked([(f"ali{i}", str(10 + i), 20) for i in range(10)] + [("shop", "200", 5)])
    for x in offers[:10]:
        x.provider = "aliexpress"
    offers[10].provider = "israeli_stores"
    shown = select_display(offers, 6)
    assert len(shown) == 6 and any(x.provider == "israeli_stores" for x in shown)
