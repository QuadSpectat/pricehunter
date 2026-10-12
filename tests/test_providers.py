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


def test_detect_condition() -> None:
    from pricehunter.providers.base import detect_condition

    assert detect_condition("Anker Power Bank 10000mAh") == "new"
    assert detect_condition("Anker Power Bank - Used") == "used"
    assert detect_condition("Anker Power Bank unused sealed") == "new"  # 'unused' is not 'used'
    assert detect_condition("iPhone 13", "Certified Refurbished") == "refurbished"
    assert detect_condition("Sony camera Open Box") == "used"
    assert detect_condition("סוללת גיבוי משומש") == "used"
    assert detect_condition("Phone", "second_hand") == "used"
    assert detect_condition("Phone", "New") == "new"


def test_condition_parsed_by_providers() -> None:
    serp = {
        "shopping_results": [
            {
                "title": "Anker Power Bank",
                "link": "https://a",
                "price": "$10",
                "extracted_price": 10,
            },
            {
                "title": "Anker Power Bank",
                "link": "https://b",
                "price": "$5",
                "extracted_price": 5,
                "second_hand_condition": "used",
            },
        ]
    }
    got = [o.condition for o in SerpApiShopping("k").parse(serp, 10)]
    assert got == ["new", "used"]
    ebay = {
        "itemSummaries": [
            {
                "title": "Camera",
                "price": {"value": "50", "currency": "USD"},
                "itemWebUrl": "u",
                "condition": "Used",
            },
        ]
    }
    assert EbayProvider("i", "s").parse(ebay, 5)[0].condition == "used"


def test_store_names_are_captured() -> None:
    assert AliExpressAffiliate("a", "b").parse(ALI, 10)[0].seller == "Anker Official Store"
    assert IsraeliStores("k").parse(SERP_IL, 10)[0].seller == "KSP"
    assert EbayProvider("i", "s").parse(EBAY, 5)[0].seller == "shop1"


def test_free_delivery_in_us_search_is_not_free_to_israel() -> None:
    offers = SerpApiShopping("k").parse(
        {
            "shopping_results": [
                {
                    "title": "Toy",
                    "link": "https://a",
                    "price": "$10",
                    "extracted_price": 10,
                    "delivery": "Free delivery",
                }
            ]
        },
        5,
    )
    assert offers[0].shipping is None  # unknown -> engine estimates, instead of assuming 0


def test_foreign_sellers_under_gl_il_are_not_treated_as_local() -> None:
    data = {
        "shopping_results": [
            {
                "title": "Toy",
                "link": "https://a",
                "source": "Desertcart.ae",
                "price": "₪100",
                "extracted_price": 100,
            },
            {
                "title": "Toy",
                "link": "https://b",
                "source": "eBay - someone",
                "price": "₪50",
                "extracted_price": 50,
            },
            {
                "title": "Toy",
                "link": "https://c",
                "source": "KSP",
                "price": "₪120",
                "extracted_price": 120,
            },
        ]
    }
    a, b, c = IsraeliStores("k").parse(data, 10)
    assert not a.local and not b.local and a.ship_from is None
    assert c.local and c.ship_from == "IL"
