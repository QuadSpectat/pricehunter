"""PriceHunter CLI."""

from __future__ import annotations

import asyncio
from typing import Annotated

import httpx
import typer
from rich.console import Console
from rich.markdown import Markdown

from .cache import Cache
from .config import Settings, load_settings
from .costs import CostTracker, ledger_totals, record_run, tracker_from_settings
from .landed_cost.engine import load_rules
from .landed_cost.fx import FxRates
from .llm import Llm
from .pipeline import run_search
from .providers import build_providers
from .report.export import save_report
from .report.markdown import to_markdown
from .resolver import resolve

app = typer.Typer(help="Find the best landed price for a product.", no_args_is_help=True)
rules_app = typer.Typer(help="Tax-rule tools.")
app.add_typer(rules_app, name="rules")
console = Console()


def _llm(s: Settings, tracker: CostTracker | None = None) -> Llm | None:
    return Llm(s.anthropic_api_key, s.model, tracker) if s.anthropic_api_key else None


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Product URL, image path, or text")],
    dest: str = "IL",
    max_results: int = 15,
    include_local: bool = True,
    include_global: bool = True,
    qty: int = 1,
    no_ai: Annotated[
        bool, typer.Option("--no-ai", help="Skip Claude calls (cheaper, less accurate)")
    ] = False,
    current_price: Annotated[
        float | None,
        typer.Option(
            "--current-price",
            help="What you would pay otherwise (USD, landed): used to estimate the saving",
        ),
    ] = None,
    fmt: Annotated[str, typer.Option("--format", help="md,json,csv")] = "md,json,csv",
) -> None:
    """Search providers and print a ranked report."""
    s = load_settings()

    async def go() -> None:
        cache = Cache(s.cache_path)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            tracker = tracker_from_settings(
                s.model, s.price_in_per_mtok, s.price_out_per_mtok, s.serpapi_cost_per_search
            )
            llm = None if no_ai else _llm(s, tracker)
            with console.status("resolving product..."):
                product = await resolve(query, client, llm)
            console.print(f"Product: [bold]{product.title}[/] (query: {product.query()})")
            if llm is None:
                console.print(
                    "[yellow]No ANTHROPIC_API_KEY: AI matching, image input and AI restriction checks are off.[/]"
                )
            providers = build_providers(s, client)
            with console.status("working...") as st:
                report = await run_search(
                    product, providers, fx=FxRates(client, cache), dest=dest.upper(), qty=qty,
                    limit=max_results, include_local=include_local, include_global=include_global,
                    llm=llm, cache=cache, progress=lambda m: st.update(m), query=query,
                    tracker=tracker, current_price_usd=current_price,
                )  # fmt: skip
        if report.cost is not None:
            record_run(s.ledger_path, query, report.cost)
        console.print(Markdown(to_markdown(report)))
        out = save_report(report, {f.strip() for f in fmt.split(",")})
        console.print(f"Saved to [bold]{out}[/]")
        cache.close()

    asyncio.run(go())


@app.command()
def providers() -> None:
    """Show which providers are configured."""
    s = load_settings()
    for p in build_providers(s):
        state = "[green]configured[/]" if p.configured() else "[red]missing keys[/]"
        console.print(f"{p.name:18} {state}  {p.note}")
    console.print(
        f"{'anthropic (LLM)':18} {'[green]configured[/]' if s.anthropic_api_key else '[red]missing key[/]'}"
    )


@app.command()
def costs() -> None:
    """Show the running total spent on searches."""
    s = load_settings()
    cost, n, saving = ledger_totals(s.ledger_path)
    console.print(
        f"{n} search(es) logged: total cost ${cost:.2f}, "
        f"sum of per-search potential savings ${saving:.2f}"
    )
    console.print(f"Assumed: SerpAPI ${s.serpapi_cost_per_search}/search, model {s.model}")


@rules_app.command("check")
def rules_check(dest: str = "IL") -> None:
    """Show how stale the tax rules are."""
    r = load_rules(dest.upper())
    console.print(
        f"{r.country}: VAT {r.vat_rate:.0%}, exemption {r.de_minimis_usd} USD ({r.threshold_basis}), "
        f"last verified {r.last_verified} against '{r.verified_against}'"
    )
    for src in r.sources:
        console.print(f"  source: {src}")
    warn = r.staleness_warning()
    console.print(f"[yellow]{warn}[/]" if warn else "[green]rules look current[/]")


def main() -> None:
    app(prog_name="pricehunter")


if __name__ == "__main__":
    main()
