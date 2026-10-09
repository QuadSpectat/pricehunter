"""Restrictions checker: YAML keyword rules + optional one-shot LLM product classification."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel

from ..llm import Llm
from ..models import Offer, Product, Restriction, Severity

RULES_PATH = Path(__file__).parent / "rules" / "israel.yaml"


class Rule(BaseModel):
    code: str
    severity: Severity
    keywords: list[str]
    reason: str
    source: str | None = None


def load_rules(path: Path = RULES_PATH) -> list[Rule]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Rule.model_validate(r) for r in data["rules"]]


def _has_keyword(text: str, kw: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(kw.lower())}(?!\w)", text) is not None


class RestrictionChecker:
    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules = rules if rules is not None else load_rules()
        self._llm_codes: set[str] = set()

    async def classify_product(self, product: Product, llm: Llm) -> None:
        """Ask the LLM which rule codes apply to the product (once per run, not per offer)."""
        codes = [r.code for r in self.rules]
        try:
            result = await llm.complete_json(
                "You classify products for import-restriction screening. "
                f"Choose ALL applicable codes from: {codes}. Return a JSON list; [] if none.",
                f"Product: {product.title}; brand={product.brand}; model={product.model}; "
                f"category={product.category}; specs={product.specs}",
            )
        except Exception:
            return  # keyword rules still apply
        if isinstance(result, list):
            self._llm_codes = {c for c in result if c in codes}

    def check(self, offer: Offer, product: Product, dest: str = "IL") -> list[Restriction]:
        if dest.upper() != "IL":
            return []
        text = f"{offer.title} {product.title} {product.category or ''}".lower()
        found: list[Restriction] = []
        for r in self.rules:
            kw = next((k for k in r.keywords if _has_keyword(text, k)), None)
            if kw is not None:
                found.append(
                    Restriction(
                        severity=r.severity,
                        code=r.code,
                        reason=f"{r.reason} (matched '{kw}')",
                        source=r.source,
                    )
                )
            elif r.code in self._llm_codes:
                found.append(
                    Restriction(
                        severity=r.severity,
                        code=r.code,
                        reason=f"{r.reason} (AI classification, lower certainty)",
                        source=r.source,
                    )
                )
        return found
