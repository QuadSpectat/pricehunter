"""Provider interface and helpers. Providers return Offers; they never raise out of `safe_search`."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation

import httpx

from ..errors import ProviderError
from ..models import Offer, Product

_SYMBOLS = {
    "$": "USD",
    "US$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₪": "ILS",
    "NIS": "ILS",
    "ILS": "ILS",
}


def parse_price(
    text: str | float | int | None, default_currency: str = "USD"
) -> tuple[Decimal, str] | None:
    """Parse strings like '$12.99', '₪1,299.00', '1.299,00 €' into (amount, currency)."""
    if text is None:
        return None
    if isinstance(text, int | float):
        return Decimal(str(text)), default_currency
    currency = default_currency
    for sym, cur in sorted(_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        if sym in text:
            currency = cur
            break
    m = re.search(r"\d[\d.,\s]*", text)
    if not m:
        return None
    num = m.group().strip().replace(" ", "")
    if "," in num and "." in num:
        if num.rfind(",") > num.rfind("."):  # 1.299,00
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif "," in num:
        head, _, tail = num.rpartition(",")
        num = head.replace(",", "") + "." + tail if len(tail) == 2 else num.replace(",", "")
    try:
        return Decimal(num), currency
    except InvalidOperation:
        return None


class Provider(ABC):
    name: str = "base"
    #: human-readable note shown by `pricehunter providers`
    note: str = ""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(follow_redirects=True)
        return self._client

    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    async def search(self, product: Product, *, dest: str, limit: int) -> list[Offer]: ...

    async def safe_search(
        self, product: Product, *, dest: str, limit: int
    ) -> tuple[list[Offer], str]:
        """Return (offers, status). Never raises."""
        if not self.configured():
            return [], "not configured"
        try:
            offers = await self.search(product, dest=dest, limit=limit)
        except ProviderError as e:
            return [], f"error: {e}"
        except Exception as e:  # graceful degradation: one provider never kills the run
            return [], f"error: {type(e).__name__}: {e}"
        return offers, f"ok ({len(offers)} offers)"

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
