"""End-to-end with fixtures: every provider mocked at the HTTP layer, no live network."""

from decimal import Decimal
from pathlib import Path

import httpx

from pricehunter.cache import Cache
from pricehunter.landed_cost.fx import StaticFx
from pricehunter.models import Product
from pricehunter.pipeline import run_search
from pricehunter.providers.aliexpress_affiliate import AliExpressAffiliate
from pricehunter.providers.ebay import EbayProvider
from pricehunter.providers.serpapi_shopping import IsraeliStores, SerpApiShopping
from pricehunter.report.export import save_report
from pricehunter.report.markdown import to_markdown

from .fixtures import ALI, EBAY, SERP_IL, SERP_US


def handler(req: httpx.Request) -> httpx.Response:
    url = str(req.url)
    if "serpapi.com" in url:
        return httpx.Response(200, json=SERP_IL if "gl=il" in url else SERP_US)
    if "aliexpress.com" in url:
        return httpx.Response(200, json=ALI)
    if "oauth2/token" in url:
        return httpx.Response(200, json={"access_token": "t"})
    if "ebay.com" in url:
        return httpx.Response(200, json=EBAY)
    return httpx.Response(404)


async def test_full_run(tmp_path: Path) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    providers = [
        IsraeliStores("k", client),
        SerpApiShopping("k", client),
        AliExpressAffiliate("a", "b", client),
        EbayProvider("i", "s", client),
        SerpApiShopping("", client),  # unconfigured provider must degrade, not crash
    ]
    product = Product(
        title="Anker 737 Power Bank", brand="Anker", model="A1289", variants={"color": "black"}
    )
    fx = StaticFx({"USD": Decimal("3.7")})
    cache = Cache(tmp_path / "c.sqlite")
    report = await run_search(product, providers, fx=fx, cache=cache)
    assert report.cheapest and report.cheapest.landed
    titles = [o.title.lower() for o in report.offers]
    assert not any("white" in t or "phone case" in t for t in titles)
    assert any(o.restrictions for o in report.offers)  # power bank -> lithium warning
    assert report.provider_status["aliexpress"].startswith("ok")
    md = to_markdown(report)
    assert "Cheapest" in md and "verify" in md
    out = save_report(report, {"md", "json", "csv"}, base=tmp_path / "runs")
    assert {p.name for p in out.iterdir()} == {"report.md", "report.json", "report.csv"}
    again = await run_search(product, providers, fx=fx, cache=cache)
    assert any("cached" in v for v in again.provider_status.values())
