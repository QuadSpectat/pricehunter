"""Thin wrapper around the Anthropic API. Model name is configurable via env."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from .costs import CostTracker
from .errors import ResolverError


class Llm:
    def __init__(self, api_key: str, model: str, tracker: CostTracker | None = None) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.tracker = tracker

    async def complete(
        self, system: str, user: str, *, image: Path | None = None, max_tokens: int = 1500
    ) -> str:
        content: list[dict[str, Any]] = []
        if image is not None:
            media = {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(
                image.suffix.lower(), "image/jpeg"
            )
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media,
                        "data": base64.b64encode(image.read_bytes()).decode(),
                    },
                }
            )
        content.append({"type": "text", "text": user})
        msg = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],  # type: ignore[typeddict-item]
        )
        if self.tracker is not None:
            u = msg.usage  # cached tokens count as input (conservative)
            tokens_in = u.input_tokens + (u.cache_creation_input_tokens or 0)
            tokens_in += u.cache_read_input_tokens or 0
            self.tracker.add_llm(tokens_in, u.output_tokens)
        return "".join(b.text for b in msg.content if isinstance(b, TextBlock))

    async def complete_json(self, system: str, user: str, *, image: Path | None = None) -> Any:
        text = await self.complete(
            system + "\nRespond with a single JSON value and nothing else.", user, image=image
        )
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        if not m:
            raise ResolverError("LLM returned no JSON")
        try:
            return json.loads(m.group())
        except json.JSONDecodeError as e:
            raise ResolverError(f"LLM returned invalid JSON: {e}") from e
