"""SerpAPI Google Shopping provider (global, and Israel via gl=il)."""

from __future__ import annotations

from decimal import Decimal

import httpx

from ..http import RateLimiter, request_json
from ..models import Offer, Product, ShippingOption
from .base import Provider, detect_condition, parse_price

ENDPOINT = "https://serpapi.com/search.json"

# Sellers that Google lists under gl=il but which are NOT Israeli shops: they ship from abroad, so
# they must pay import tax and need a shipping estimate (observed in real results, 2026-10-12).
FOREIGN_SELLERS = (
    "desertcart", "made-in-china", "aliexpress", "alibaba", "temu", "shein", "ebay", "amazon.com",
    "amazon.ae", "walmart", "banggood", "dhgate", "etsy", "wish",
)  # fmt: skip


def is_foreign_seller(name: str | None) -> bool:
    n = (name or "").lower()
    return any(f in n for f in FOREIGN_SELLERS)


class SerpApiShopping(Provider):
    name = "serpapi_shopping"
    note = "Google Shopping via SerpAPI (global results, gl=us)"
    gl = "us"
    local = False

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(client)
        self._key = api_key
        self._limiter = RateLimiter(5)

    def configured(self) -> bool:
        return bool(self._key)

    async def search(self, product: Product, *, dest: str, limit: int) -> list[Offer]:
        params = {
            "engine": "google_shopping",
            "q": product.query(),
            "gl": self.gl,
            "api_key": self._key,
        }
        data = await request_json(
            self.client, self.name, "GET", ENDPOINT, params=params, limiter=self._limiter
        )
        self.paid_calls += 1
        return self.parse(data, limit)

    def parse(self, data: dict, limit: int) -> list[Offer]:  # type: ignore[type-arg]
        default_cur = "ILS" if self.gl == "il" else "USD"
        offers: list[Offer] = []
        for item in data.get("shopping_results", []):
            parsed = parse_price(item.get("extracted_price") or item.get("price"), default_cur)
            if parsed is None:
                continue
            amount, cur = parsed
            if isinstance(item.get("price"), str):  # symbol in the display string wins
                p2 = parse_price(item["price"], default_cur)
                cur = p2[1] if p2 else cur
            url = item.get("link") or item.get("product_link")
            if not url:
                continue
            local = self.local and not is_foreign_seller(item.get("source"))
            shipping = None
            delivery = str(item.get("delivery") or "")
            # "Free delivery" from the gl=us search means free to a US address, NOT to Israel,
            # so only trust it for genuinely local (Israeli) shops.
            if local and "free" in delivery.lower():
                shipping = ShippingOption(price=Decimal(0), currency=cur)
            offers.append(
                Offer(
                    provider=self.name,
                    title=item.get("title", ""),
                    condition=detect_condition(
                        item.get("title", ""), str(item.get("second_hand_condition") or "")
                    ),
                    url=url,
                    seller=item.get("source"),
                    price=amount,
                    currency=cur,
                    local=local,
                    ship_from="IL" if local else None,
                    shipping=shipping,
                    rating=item.get("rating"),
                    orders=item.get("reviews"),
                    image_url=item.get("thumbnail"),
                )
            )
            if len(offers) >= limit:
                break
        return offers


class IsraeliStores(SerpApiShopping):
    """Israeli shops (KSP, Ivory, Zap, Amazon.il ...) via Google Shopping with gl=il.

    Direct per-store adapters are intentionally NOT implemented: they would need page
    scraping, which must respect each site's robots.txt and terms. Add them here only
    where an official API/feed exists.
    """

    name = "israeli_stores"
    note = "Israeli stores via Google Shopping gl=il (KSP/Ivory/Zap/Amazon.il direct = stubs)"
    gl = "il"
    local = True
