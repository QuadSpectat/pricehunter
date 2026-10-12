from __future__ import annotations

from pathlib import Path

from ..errors import ResolverError
from ..llm import Llm
from ..models import Product
from .text_resolver import SYSTEM, product_from_json

IMAGE_EXTRA = (
    " The input is a product photo or a screenshot of a shop listing: read visible brand/model text; "
    "if unsure, set model null. Put the variant that is SELECTED (colour, size, ...) in variants. "
    "If it is a shop listing screenshot, also add a key `reference` with: store (seller/shop name), "
    "price (number, the price shown for the selected variant), original_price (struck-through price, "
    "number or null), shipping (number; 0 if shipping is free; null if no shipping price is visible), "
    "currency (ISO code of the displayed prices), delivery_text (e.g. 'Oct 21 - 28'). "
    "Use null for anything not visible. Omit `reference` for plain product photos."
)


async def resolve_image(path: Path, llm: Llm | None) -> Product:
    if llm is None:
        raise ResolverError("Image input needs ANTHROPIC_API_KEY (vision model)")
    data = await llm.complete_json(
        SYSTEM + IMAGE_EXTRA,
        "Identify the product in this image.",
        image=path,
    )
    return product_from_json(data, path.stem)
