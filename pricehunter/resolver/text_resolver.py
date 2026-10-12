from __future__ import annotations

from ..llm import Llm
from ..models import Product

SYSTEM = (
    "Extract a product from the user's description. Return JSON with keys: title, brand, model, "
    "specs (object), variants (object: color/size/capacity/voltage/plug), quantity (int), category, "
    "search_query (a concise shop search query). Use null when unknown; never invent a model number."
)


_EMPTY = {"", "none", "null", "n/a", "unknown", "-"}


def _clean(d: object) -> dict[str, str]:
    """Stringify a dict from the model, dropping empty placeholders such as "None"."""
    if not isinstance(d, dict):
        return {}
    return {
        str(k): str(v)
        for k, v in d.items()
        if v is not None and str(v).strip().lower() not in _EMPTY
    }


def product_from_json(data: dict, fallback_title: str, source_url: str | None = None) -> Product:  # type: ignore[type-arg]
    return Product(
        title=data.get("title") or fallback_title,
        brand=data.get("brand"),
        model=data.get("model"),
        specs=_clean(data.get("specs")),
        variants=_clean(data.get("variants")),
        quantity=int(data.get("quantity") or 1),
        category=data.get("category"),
        search_query=data.get("search_query") or "",
        source_url=source_url,
    )


async def resolve_text(text: str, llm: Llm | None) -> Product:
    if llm is None:
        return Product(title=text.strip(), search_query=text.strip())
    try:
        data = await llm.complete_json(SYSTEM, text)
        return product_from_json(data, text.strip())
    except Exception:
        return Product(title=text.strip(), search_query=text.strip())
