"""AliExpress Affiliate/Open Platform provider.

VERIFY against https://openservice.aliexpress.com before relying on live calls:
gateway URL, signing method, and whether shipping.get is available to your app.
Response parsing is covered by fixtures; the live shape is unconfirmed.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ..http import RateLimiter, request_json
from ..models import Offer, Product
from .base import Provider, detect_condition

GATEWAY = "https://api-sg.aliexpress.com/sync"
METHOD = "aliexpress.affiliate.product.query"
FROM_PRICE_WARNING = (
    "AliExpress API gives the LOWEST-variant price: the colour/size you want may cost more "
    "(check the listing)"
)


def sign(params: dict[str, str], secret: str) -> str:
    """HMAC-SHA256 over sorted key+value pairs (sign_method=sha256)."""
    concat = "".join(f"{k}{params[k]}" for k in sorted(params))
    return hmac.new(secret.encode(), concat.encode(), hashlib.sha256).hexdigest().upper()


def _dec(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


class AliExpressAffiliate(Provider):
    name = "aliexpress"
    note = "AliExpress Affiliate API (official; needs app key/secret)"

    def __init__(
        self, app_key: str, app_secret: str, client: httpx.AsyncClient | None = None
    ) -> None:
        super().__init__(client)
        self._key = app_key
        self._secret = app_secret
        self._limiter = RateLimiter(2)

    def configured(self) -> bool:
        return bool(self._key and self._secret)

    async def search(self, product: Product, *, dest: str, limit: int) -> list[Offer]:
        params = {
            "app_key": self._key,
            "method": METHOD,
            "sign_method": "sha256",
            "timestamp": str(int(time.time() * 1000)),
            "keywords": product.query(),
            "page_size": str(min(limit, 50)),
            "ship_to_country": dest,
            "target_currency": "USD",
            "target_language": "EN",
        }
        params["sign"] = sign(params, self._secret)
        data = await request_json(
            self.client, self.name, "GET", GATEWAY, params=params, limiter=self._limiter
        )
        return self.parse(data, limit, dest)

    def parse(self, data: dict[str, Any], limit: int, dest: str = "IL") -> list[Offer]:
        root = data.get("aliexpress_affiliate_product_query_response", data)
        products = (
            root.get("resp_result", {}).get("result", {}).get("products", {}).get("product", [])
        )
        offers: list[Offer] = []
        for p in products:
            price = _dec(p.get("target_sale_price") or p.get("target_original_price"))
            url = p.get("promotion_link") or p.get("product_detail_url")
            if price is None or not url:
                continue
            rating: float | None = None
            rate = str(p.get("evaluate_rate", "")).rstrip("%")
            if rate:
                try:
                    rating = round(float(rate) / 20, 2)  # 0-100% -> 0-5
                except ValueError:
                    rating = None
            offers.append(
                Offer(
                    provider=self.name,
                    title=p.get("product_title", ""),
                    condition=detect_condition(p.get("product_title", "")),
                    url=url,
                    seller=p.get("shop_url"),
                    price=price,
                    currency=p.get("target_sale_price_currency", "USD"),
                    ship_from="CN",
                    shipping=None,  # unknown until shipping.get is wired; engine will estimate
                    rating=rating,
                    orders=int(p["lastest_volume"])
                    if str(p.get("lastest_volume", "")).isdigit()
                    else None,
                    image_url=p.get("product_main_image_url"),
                    warnings=[FROM_PRICE_WARNING],
                )
            )
            if len(offers) >= limit:
                break
        return offers
