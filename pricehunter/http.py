"""Shared async HTTP helper: timeouts, retries with backoff, simple rate limiting."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .errors import ProviderError, ProviderRateLimited

UA = "Mozilla/5.0 (compatible; PriceHunter/0.1)"


class RateLimiter:
    def __init__(self, per_second: float) -> None:
        self._interval = 1.0 / per_second
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delay = self._last + self._interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


async def request_text(
    client: httpx.AsyncClient,
    provider: str,
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 0.5,
    limiter: RateLimiter | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Perform a request with retries on transport errors, 429 and 5xx."""
    last = "unknown"
    for attempt in range(retries):
        if limiter:
            await limiter.wait()
        try:
            resp = await client.request(method, url, timeout=20.0, **kwargs)
        except httpx.TransportError as e:
            last = type(e).__name__
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                last = f"HTTP {resp.status_code}"
            elif resp.status_code >= 400:
                raise ProviderError(provider, f"HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                return resp
        await asyncio.sleep(backoff * (2**attempt))
    if last == "HTTP 429":
        raise ProviderRateLimited(provider, "rate limited (HTTP 429)")
    raise ProviderError(provider, f"failed after {retries} attempts: {last}")


async def request_json(
    client: httpx.AsyncClient, provider: str, method: str, url: str, **kwargs: Any
) -> Any:
    resp = await request_text(client, provider, method, url, **kwargs)
    try:
        return resp.json()
    except ValueError as e:
        raise ProviderError(provider, f"invalid JSON: {e}") from e
