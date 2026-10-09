"""FX rates: Bank of Israel representative rates (primary), frankfurter.app (fallback).

Everything pivots through ILS. Always exposes the rate and timestamp used.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from ..cache import FX_TTL, Cache
from ..errors import ProviderError
from ..http import UA, request_text

BOI_URL = "https://edge.boi.gov.il/FusionEdgeServer/ws/public/sdmxapi/rest/data/EXR/RER_{cur}_ILS"
FALLBACK_URL = "https://api.frankfurter.app/latest"


def parse_boi_xml(xml: str) -> tuple[Decimal, str]:
    """Return (latest rate, date) from SDMX-XML observations."""
    obs = re.findall(r'<(?:\w+:)?Obs\b[^>]*?TIME_PERIOD="([^"]+)"[^>]*?OBS_VALUE="([^"]+)"', xml)
    if not obs:
        obs = [
            (t, v)
            for v, t in re.findall(
                r'<(?:\w+:)?Obs\b[^>]*?OBS_VALUE="([^"]+)"[^>]*?TIME_PERIOD="([^"]+)"', xml
            )
        ]
    if not obs:
        raise ProviderError("fx", "no observations in Bank of Israel response")
    date, value = max(obs)
    return Decimal(value), date


class FxRates:
    def __init__(self, client: httpx.AsyncClient, cache: Cache | None = None) -> None:
        self._client = client
        self._cache = cache
        self._ils_per: dict[str, tuple[Decimal, str]] = {"ILS": (Decimal(1), "fixed")}

    async def _fetch(self, cur: str) -> tuple[Decimal, str]:
        key = f"fx:{cur}"
        if self._cache and (hit := self._cache.get(key)):
            return Decimal(hit["rate"]), hit["note"]
        end = datetime.now(UTC).date()
        start = end - timedelta(days=10)
        try:
            resp = await request_text(
                self._client,
                "fx",
                "GET",
                BOI_URL.format(cur=cur),
                params={"startPeriod": start.isoformat(), "endPeriod": end.isoformat()},
                headers={"User-Agent": UA},
            )
            rate, date = parse_boi_xml(resp.text)
            note = f"Bank of Israel representative rate {date}"
        except ProviderError:
            resp = await request_text(
                self._client, "fx", "GET", FALLBACK_URL, params={"from": cur, "to": "ILS"}
            )
            body = resp.json()
            rate = Decimal(str(body["rates"]["ILS"]))
            note = f"frankfurter.app fallback {body.get('date', '')}"
        if self._cache:
            self._cache.set(key, {"rate": str(rate), "note": note}, FX_TTL)
        return rate, note

    async def load(self, currencies: set[str]) -> None:
        for cur in currencies | {"USD"}:
            if cur not in self._ils_per:
                self._ils_per[cur] = await self._fetch(cur)

    def to_ils(self, amount: Decimal, cur: str) -> Decimal:
        return amount * self._ils_per[cur][0]

    def to_usd(self, amount: Decimal, cur: str) -> Decimal:
        return self.to_ils(amount, cur) / self._ils_per["USD"][0]

    def from_usd(self, amount_usd: Decimal, cur: str) -> Decimal:
        return amount_usd * self._ils_per["USD"][0] / self._ils_per[cur][0]

    def describe(self) -> str:
        used = [
            f"1 {c} = {r:.4f} ILS ({n})"
            for c, (r, n) in sorted(self._ils_per.items())
            if c != "ILS"
        ]
        return "; ".join(used)


class StaticFx(FxRates):
    """Fixed rates for tests / offline use."""

    def __init__(self, ils_per: dict[str, Decimal]) -> None:
        self._ils_per = {"ILS": (Decimal(1), "fixed")} | {
            c: (r, "static") for c, r in ils_per.items()
        }

    async def load(self, currencies: set[str]) -> None:
        return None
