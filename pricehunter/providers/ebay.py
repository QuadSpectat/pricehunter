"""eBay Browse API provider (official, free tier 5,000 calls/day)."""

from __future__ import annotations

import base64
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ..http import RateLimiter, request_json
from ..models import Offer, Product, ShippingOption
from .base import Provider, detect_condition

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


def _dec(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


class EbayProvider(Provider):
    name = "ebay"
    note = "eBay Browse API (official; needs client id/secret)"

    def __init__(
        self, client_id: str, client_secret: str, client: httpx.AsyncClient | None = None
    ) -> None:
        super().__init__(client)
        self._id = client_id
        self._secret = client_secret
        self._token: str | None = None
        self._limiter = RateLimiter(4)

    def configured(self) -> bool:
        return bool(self._id and self._secret)

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        basic = base64.b64encode(f"{self._id}:{self._secret}".encode()).decode()
        data = await request_json(
            self.client,
            self.name,
            "POST",
            TOKEN_URL,
            headers={"Authorization": f"Basic {basic}"},
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
        )
        self._token = str(data["access_token"])
        return self._token

    async def search(self, product: Product, *, dest: str, limit: int) -> list[Offer]:
        token = await self._get_token()
        data = await request_json(
            self.client,
            self.name,
            "GET",
            SEARCH_URL,
            params={
                "q": product.query(),
                "limit": str(min(limit, 50)),
                "filter": f"deliveryCountry:{dest}",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            },
            limiter=self._limiter,
        )
        return self.parse(data, limit)

    def parse(self, data: dict[str, Any], limit: int) -> list[Offer]:
        offers: list[Offer] = []
        for it in data.get("itemSummaries", []):
            price = _dec(it.get("price", {}).get("value"))
            if price is None or not it.get("itemWebUrl"):
                continue
            cur = it["price"].get("currency", "USD")
            shipping = None
            opts = it.get("shippingOptions") or []
            if opts and opts[0].get("shippingCost"):
                cost = _dec(opts[0]["shippingCost"].get("value"))
                if cost is not None:
                    shipping = ShippingOption(
                        price=cost, currency=opts[0]["shippingCost"].get("currency", cur)
                    )
            seller = it.get("seller", {})
            fb = seller.get("feedbackPercentage")
            offers.append(
                Offer(
                    provider=self.name,
                    title=it.get("title", ""),
                    url=it["itemWebUrl"],
                    seller=seller.get("username"),
                    condition=detect_condition(it.get("title", ""), str(it.get("condition") or "")),
                    price=price,
                    currency=cur,
                    ship_from=(it.get("itemLocation") or {}).get("country"),
                    shipping=shipping,
                    rating=round(float(fb) / 20, 2) if fb else None,
                    image_url=(it.get("image") or {}).get("imageUrl"),
                )
            )
            if len(offers) >= limit:
                break
        return offers
