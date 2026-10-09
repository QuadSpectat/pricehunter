from __future__ import annotations

from pathlib import Path

from ..errors import ResolverError
from ..llm import Llm
from ..models import Product
from .text_resolver import SYSTEM, product_from_json


async def resolve_image(path: Path, llm: Llm | None) -> Product:
    if llm is None:
        raise ResolverError("Image input needs ANTHROPIC_API_KEY (vision model)")
    data = await llm.complete_json(
        SYSTEM
        + " The input is a product photo: read visible brand/model text; if unsure, set model null.",
        "Identify the product in this image.",
        image=path,
    )
    return product_from_json(data, path.stem)
