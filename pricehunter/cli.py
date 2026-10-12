"""PriceHunter CLI."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown

from .config import load_settings
from .costs import ledger_totals
from .landed_cost.engine import load_rules
from .providers import build_providers
from .report.export import save_report
from .report.markdown import to_markdown
from .service import SearchOptions, execute_search

app = typer.Typer(help="Find the best landed price for a product.", no_args_is_help=True)
rules_app = typer.Typer(help="Tax-rule tools.")
app.add_typer(rules_app, name="rules")
console = Console()


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
    options = SearchOptions(
        dest=dest,
        max_results=max_results,
        include_local=include_local,
        include_global=include_global,
        qty=qty,
        no_ai=no_ai,
        current_price_usd=current_price,
    )
    if not s.anthropic_api_key and not no_ai:
        console.print(
            "[yellow]No ANTHROPIC_API_KEY: AI matching, image input and AI restriction checks are off.[/]"
        )

    async def go() -> None:
        with console.status("working...") as st:
            report = await execute_search(
                query,
                s,
                options,
                progress=lambda m: st.update(m),
                on_product=lambda p: console.print(
                    f"Product: [bold]{p.title}[/] (query: {p.query()})"
                ),
            )
        console.print(Markdown(to_markdown(report)))
        out = save_report(report, {f.strip() for f in fmt.split(",")})
        console.print(f"Saved to [bold]{out}[/]")

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
