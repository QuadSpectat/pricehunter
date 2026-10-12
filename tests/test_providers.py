from decimal import Decimal

import httpx

from pricehunter.models import Product
from pricehunter.providers.aliexpress_affiliate import AliExpressAffiliate, sign
from pricehunter.providers.base import parse_price
from pricehunter.providers.ebay import EbayProvider
from pricehunter.providers.serpapi_shopping import IsraeliStores, SerpApiShopping

from .fixtures import ALI, EBAY, SERP_IL, SERP_US


def test_parse_price_formats() -> None:
    assert parse_price("$12.99") == (Decimal("12.99"), "USD")
    assert parse_price("₪1,299.00") == (Decimal("1299.00"), "ILS")
    assert parse_price("1.299,00 €") == (Decimal("1299.00"), "EUR")
    assert parse_price("no digits") is None
    assert parse_price(None) is None


def test_serpapi_il_parse() -> None:
    offers = IsraeliStores("k").parse(SERP_IL, 10)
    assert len(offers) == 3
    assert offers[0].currency == "ILS" and offers[0].local and offers[0].ship_from == "IL"
    assert offers[0].shipping is not None and offers[0].shipping.price == 0


def test_serpapi_global_parse_and_limit() -> None:
    assert len(SerpApiShopping("k").parse(SERP_US, 10)) == 1
    assert len(IsraeliStores("k").parse(SERP_IL, 1)) == 1


def test_aliexpress_parse_and_sign() -> None:
    offers = AliExpressAffiliate("a", "b").parse(ALI, 10)
    assert len(offers) == 1
    assert offers[0].price == Decimal("62.10") and offers[0].rating == 4.8
    assert offers[0].orders == 532
    assert sign({"b": "2", "a": "1"}, "s") == sign({"a": "1", "b": "2"}, "s")
    assert sign({"a": "1"}, "s") != sign({"a": "1"}, "t")


def test_ebay_parse() -> None:
    o = EbayProvider("i", "s").parse(EBAY, 5)[0]
    assert o.shipping is not None and o.shipping.price == Decimal("12.00")
    assert o.ship_from == "US" and o.rating == 4.97


async def test_safe_search_degrades_gracefully() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad key")

    p = SerpApiShopping("k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    offers, status = await p.safe_search(Product(title="x"), dest="IL", limit=5)
    assert offers == [] and status.startswith("error")
    offers, status = await SerpApiShopping("").safe_search(Product(title="x"), dest="IL", limit=5)
    assert status == "not configured"


async def test_retry_on_500_then_success() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500) if calls["n"] < 2 else httpx.Response(200, json=SERP_US)

    p = SerpApiShopping("k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    offers, _ = await p.safe_search(Product(title="anker"), dest="IL", limit=5)
    assert len(offers) == 1 and calls["n"] == 2


def test_aliexpress_offers_warn_about_lowest_variant_price() -> None:
    offers = AliExpressAffiliate("a", "b").parse(ALI, 10)
    assert any("LOWEST-variant" in w for w in offers[0].warnings)
