"""Core data models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from .costs import RunCost


class MatchLevel(StrEnum):
    EXACT = "exact"
    LIKELY = "likely"
    SIMILAR = "similar"
    REJECTED = "rejected"


class Severity(StrEnum):
    INFO = "info"
    WARN = "warn"
    BLOCKED = "blocked"


class ReferenceListing(BaseModel):
    """The listing the user showed us (e.g. read from a screenshot): their baseline to beat."""

    store: str | None = None
    price: Decimal | None = None
    original_price: Decimal | None = None
    shipping: Decimal | None = None  # 0 = free shipping, None = not visible
    currency: str = "USD"
    delivery_text: str | None = None
    source: str = "screenshot"


class Product(BaseModel):
    title: str
    brand: str | None = None
    model: str | None = None
    specs: dict[str, str] = Field(default_factory=dict)
    variants: dict[str, str] = Field(default_factory=dict)  # color, size, voltage, plug...
    quantity: int = 1
    category: str | None = None
    source_url: str | None = None
    search_query: str = ""
    reference: ReferenceListing | None = None

    def query(self) -> str:
        if self.search_query:
            return self.search_query
        return " ".join(p for p in (self.brand, self.model, self.title) if p)


class ShippingOption(BaseModel):
    price: Decimal | None = None  # None => unknown
    currency: str = "USD"
    carrier: str | None = None
    eta_days_min: int | None = None
    eta_days_max: int | None = None
    tracking: bool | None = None
    estimated: bool = False  # True when not provided by the source


class Restriction(BaseModel):
    severity: Severity
    code: str
    reason: str
    source: str | None = None


class LandedCost(BaseModel):
    item: Decimal
    shipping: Decimal
    vat: Decimal
    duty: Decimal
    fees: Decimal
    total: Decimal  # in the offer's currency
    total_usd: Decimal
    total_ils: Decimal
    currency_note: str = ""
    estimated: bool = False
    notes: list[str] = Field(default_factory=list)


class Offer(BaseModel):
    provider: str
    title: str
    url: str
    seller: str | None = None
    price: Decimal
    currency: str = "USD"
    qty: int = 1  # units included in `price`
    ship_from: str | None = None  # ISO country code if known
    local: bool = False  # sold from within the destination country
    shipping: ShippingOption | None = None
    rating: float | None = None  # 0..5
    orders: int | None = None
    official_store: bool | None = None
    image_url: str | None = None
    match: MatchLevel = MatchLevel.SIMILAR
    confidence: float = 0.0
    match_reason: str = ""
    landed: LandedCost | None = None
    restrictions: list[Restriction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    condition: str = "new"  # new | used | refurbished (assumed new when the source says nothing)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Report(BaseModel):
    query: str
    product: Product
    destination: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    offers: list[Offer] = Field(default_factory=list)
    cheapest: Offer | None = None
    fastest: Offer | None = None
    best_value: Offer | None = None
    fx_note: str = ""
    rules_note: str = ""
    provider_status: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    cost: RunCost | None = None
    reference: Offer | None = None  # the user's own listing, with landed cost
