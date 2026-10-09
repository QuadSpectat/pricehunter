"""URL -> Product. Fetches the page politely (no scraping of prices), reads title/meta/JSON-LD only."""

from __future__ import annotations

import html
import json
import re
from urllib.parse import unquote, urlparse

import httpx

from ..http import UA
from ..llm import Llm
from ..models import Product
from .text_resolver import SYSTEM, product_from_json


def extract_page_facts(page: str) -> dict[str, str]:
    """Pull title, og:title, description and JSON-LD Product name/brand/model from HTML."""
    facts: dict[str, str] = {}
    if m := re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I):
        facts["title"] = html.unescape(m.group(1)).strip()
    for prop in ("og:title", "og:description"):
        m = re.search(
            rf'<meta[^>]+property=["\']{prop}["\'][^>]+content=["\']([^"\']*)', page, re.I
        )
        if m:
            facts[prop] = html.unescape(m.group(1)).strip()
    for blob in re.findall(
        r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", page, re.S | re.I
    ):
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for node in data if isinstance(data, list) else [data]:
            if isinstance(node, dict) and node.get("@type") == "Product":
                facts["ld_name"] = str(node.get("name", ""))
                brand = node.get("brand")
                facts["ld_brand"] = str(
                    brand.get("name") if isinstance(brand, dict) else brand or ""
                )
                facts["ld_model"] = str(node.get("model", "") or node.get("mpn", ""))
    return facts


def title_from_slug(url: str) -> str:
    """Last-resort title guess from the URL path."""
    path = unquote(urlparse(url).path)
    slug = max((s for s in path.split("/") if s), key=len, default="")
    slug = re.sub(r"\.(html?|php)$", "", slug)
    return re.sub(r"[-_+]+", " ", slug).strip()


async def resolve_url(url: str, client: httpx.AsyncClient, llm: Llm | None) -> Product:
    facts: dict[str, str] = {}
    try:
        resp = await client.get(
            url, headers={"User-Agent": UA}, timeout=15.0, follow_redirects=True
        )
        if resp.status_code < 400:
            facts = extract_page_facts(resp.text[:600_000])
    except httpx.HTTPError:
        pass  # many shops block bots; fall back to the URL slug
    fallback = (
        facts.get("ld_name") or facts.get("og:title") or facts.get("title") or title_from_slug(url)
    )
    if llm is not None:
        try:
            data = await llm.complete_json(
                SYSTEM, f"URL: {url}\nPage facts: {json.dumps(facts)[:3000]}"
            )
            return product_from_json(data, fallback, url)
        except Exception:
            pass
    return Product(
        title=fallback,
        brand=facts.get("ld_brand") or None,
        model=facts.get("ld_model") or None,
        source_url=url,
        search_query=fallback,
    )
