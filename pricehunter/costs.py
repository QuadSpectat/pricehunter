"""Tracks what each search costs (SerpAPI calls + Claude tokens) and keeps a running ledger.

All figures are ESTIMATES from list prices; see README. Free lookups (AliExpress affiliate API,
Bank of Israel FX, eBay free tier) count as zero.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median

from pydantic import BaseModel

# USD per 1M tokens (input, output). Source: Anthropic model table, cached 2026-10-06.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5-1": (10.0, 50.0),
}


class RunCost(BaseModel):
    serp_calls: int = 0
    serpapi_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    llm_usd: float = 0.0
    total_usd: float = 0.0
    ils_per_usd: float = 0.0
    potential_saving_usd: float | None = None
    saving_basis: str = ""
    worth_it: bool | None = None
    verdict: str = ""
    cumulative_cost_usd: float = 0.0
    cumulative_searches: int = 0


@dataclass
class CostTracker:
    price_in: float = 2.0  # USD per 1M input tokens
    price_out: float = 10.0
    serp_per_search: float = 0.025
    tokens_in: int = 0
    tokens_out: int = 0
    serp_calls: int = 0

    def add_llm(self, tokens_in: int, tokens_out: int) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out

    def add_serp(self, calls: int) -> None:
        self.serp_calls += calls

    @property
    def llm_usd(self) -> float:
        return (self.tokens_in * self.price_in + self.tokens_out * self.price_out) / 1_000_000

    @property
    def serpapi_usd(self) -> float:
        return self.serp_calls * self.serp_per_search

    @property
    def total_usd(self) -> float:
        return self.llm_usd + self.serpapi_usd

    def summary(
        self,
        totals_usd: list[Decimal],
        *,
        current_price_usd: float | None = None,
        ils_per_usd: float = 0.0,
        generic: bool = False,
        cheapest_estimated: bool = False,
    ) -> RunCost:
        """Build the run summary. `totals_usd` are landed totals of the acceptable offers."""
        saving: float | None = None
        basis = ""
        if totals_usd:
            cheapest = float(min(totals_usd))
            if current_price_usd is not None:
                saving = current_price_usd - cheapest
                basis = "your stated price minus the cheapest offer"
            elif len(totals_usd) >= 2:
                saving = float(median(totals_usd)) - cheapest
                basis = "median offer minus cheapest offer"
        worth: bool | None = None
        if saving is None:
            verdict = "No saving can be estimated (too few matching offers)."
        else:
            saving = max(saving, 0.0)
            worth = saving > self.total_usd
            if cheapest_estimated:
                basis += " - ROUGH: the cheapest offer's shipping/tax is estimated, not quoted"
            if generic and current_price_usd is None:
                basis += (
                    " - ROUGH: the query has no model number, so offers may be different products"
                )
            verdict = f"Search cost ${self.total_usd:.3f} vs. potential saving ${saving:.2f}: " + (
                "worth it." if worth else "NOT worth it (cost >= saving)."
            )
        return RunCost(
            serp_calls=self.serp_calls,
            serpapi_usd=round(self.serpapi_usd, 4),
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            llm_usd=round(self.llm_usd, 4),
            total_usd=round(self.total_usd, 4),
            ils_per_usd=ils_per_usd,
            potential_saving_usd=None if saving is None else round(saving, 2),
            saving_basis=basis,
            worth_it=worth,
            verdict=verdict,
        )


def tracker_from_settings(
    model: str, price_in: float | None, price_out: float | None, serp: float
) -> CostTracker:
    default_in, default_out = MODEL_PRICES.get(model, (5.0, 25.0))  # unknown model: assume pricey
    return CostTracker(
        price_in=default_in if price_in is None else price_in,
        price_out=default_out if price_out is None else price_out,
        serp_per_search=serp,
    )


def ledger_totals(path: Path) -> tuple[float, int, float]:
    """(total cost USD, number of searches, total potential saving USD) over all logged runs."""
    cost = saving = 0.0
    n = 0
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            n += 1
            cost += float(row.get("total_usd", 0))
            saving += float(row.get("potential_saving_usd") or 0)
    return cost, n, saving


def record_run(path: Path, query: str, cost: RunCost) -> RunCost:
    """Append this run to the ledger and fill in the cumulative figures."""
    prev_cost, prev_n, _ = ledger_totals(path)
    row = {"time": datetime.now(UTC).isoformat(timespec="seconds"), "query": query}
    row |= cost.model_dump(exclude={"cumulative_cost_usd", "cumulative_searches"})
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    cost.cumulative_cost_usd = round(prev_cost + cost.total_usd, 4)
    cost.cumulative_searches = prev_n + 1
    return cost
