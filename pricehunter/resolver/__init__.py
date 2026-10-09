"""Input resolvers: URL, image or text -> Product."""

from __future__ import annotations

from pathlib import Path

import httpx

from ..llm import Llm
from ..models import Product
from .image_resolver import resolve_image
from .text_resolver import resolve_text
from .url_resolver import resolve_url

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def detect_kind(raw: str) -> str:
    if raw.lower().startswith(("http://", "https://")):
        return "url"
    if Path(raw).suffix.lower() in IMAGE_EXT and Path(raw).is_file():
        return "image"
    return "text"


async def resolve(raw: str, client: httpx.AsyncClient, llm: Llm | None) -> Product:
    kind = detect_kind(raw)
    if kind == "url":
        return await resolve_url(raw, client, llm)
    if kind == "image":
        return await resolve_image(Path(raw), llm)
    return await resolve_text(raw, llm)
