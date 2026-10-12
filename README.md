# PriceHunter

Finds the best **landed price** (item + shipping + VAT/duty) for a product, given a URL, an image or text.
Compares Israeli stores and global sellers (AliExpress, eBay, Google Shopping), flags import restrictions,
and writes a ranked report (Markdown / JSON / CSV) to `runs/<timestamp>/`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e . pytest pytest-asyncio ruff mypy types-PyYAML
copy .env.example .env     # then fill in keys
```

## Keys (all optional; providers without keys are skipped)

| Variable | Where to get it | Cost |
|---|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com | pay per use. Enables image input, AI matching, AI restriction check |
| `SERPAPI_KEY` | serpapi.com | free tier ~250 searches/mo. Powers Israeli stores (gl=il) + global Google Shopping |
| `ALIEXPRESS_APP_KEY` / `_SECRET` | portals.aliexpress.com (affiliate) then Open Platform app | free |
| `EBAY_CLIENT_ID` / `_SECRET` | developer.ebay.com | free (5,000 calls/day) |

Bank of Israel exchange rates need no key.

## Usage

```powershell
pricehunter providers                      # which providers are configured
pricehunter rules check                    # how stale the tax rules are
pricehunter search "anker 737 power bank" --qty 1 --max-results 15
pricehunter search "https://www.aliexpress.com/item/123.html" --format md,json
pricehunter search .\photo.jpg             # needs ANTHROPIC_API_KEY
```

## What each search costs

Every report has a **Search cost** section: SerpAPI calls (each uncached call x `SERPAPI_COST_PER_SEARCH`,
default $0.025 = Starter plan; set `0` on the free tier) plus Claude tokens at list price for your
`PRICEHUNTER_MODEL`. It compares that with the **potential saving** (median offer minus cheapest offer, or
your `--current-price` minus the cheapest) and says whether the search was worth it. Cached results are
free. `pricehunter costs` shows the running total (`cost_ledger.jsonl`). `--no-ai` skips Claude calls.
A search without a model number is marked ROUGH, because the offers may be different products.

## How it works

resolver (URL/image/text → Product) → providers (parallel, cached 6h) → matcher (title/variant heuristics,
optional LLM check) → landed-cost engine (FX from Bank of Israel; rules in YAML) → restrictions → ranking
(cheapest / fastest / best value, suspicious-price warnings).

## Limitations (read these)

- **Tax rules are not verified against gov.il.** `landed_cost/rules/israel.yaml` was compiled from secondary
  sources (VAT 18%, $75 exemption, reverted June 2026). The engine warns until `verified_against: gov.il`
  is set, and again once `last_verified` is older than 90 days. Customs duty by category and courier handling
  fees are empty placeholders.
- **Restriction keywords are a screening aid, not legal advice.** Wording is always "likely - verify".
- AliExpress response parsing and request signing are built from documentation and fixtures, not from a live
  account. Expect to adjust once real keys exist (see `docs/sources.md`).
- AliExpress shipping cost is not fetched yet, so it is **estimated** (flagged `~`). Direct KSP/Ivory/Zap/Amazon.il
  adapters are intentionally not implemented (no official API); those stores come via Google Shopping `gl=il`.
- Google Lens image search is not wired in; images are identified by the vision model, then searched as text.
- Quantity > 1 assumes shipping is unchanged.
- WebSearch/FX hit live services only at runtime; tests use fixtures and never touch the network.

## Development

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy pricehunter
```
