from __future__ import annotations

import httpx

from ..config import Settings
from .aliexpress_affiliate import AliExpressAffiliate
from .base import Provider
from .ebay import EbayProvider
from .serpapi_shopping import IsraeliStores, SerpApiShopping


def build_providers(s: Settings, client: httpx.AsyncClient | None = None) -> list[Provider]:
    return [
        IsraeliStores(s.serpapi_key, client),
        SerpApiShopping(s.serpapi_key, client),
        AliExpressAffiliate(s.aliexpress_app_key, s.aliexpress_app_secret, client),
        EbayProvider(s.ebay_client_id, s.ebay_client_secret, client),
    ]
