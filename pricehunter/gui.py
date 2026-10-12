"""PriceHunter GUI (Streamlit). Start with:  streamlit run pricehunter/gui.py  (or run_gui.bat)."""

from __future__ import annotations

import asyncio
import io
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from streamlit_paste_button import paste_image_button

from pricehunter.config import load_settings
from pricehunter.costs import ledger_totals
from pricehunter.models import Offer, Report
from pricehunter.providers import build_providers
from pricehunter.report.markdown import to_markdown
from pricehunter.service import SearchOptions, execute_search

st.set_page_config(page_title="PriceHunter", page_icon="🔎", layout="wide")
settings = load_settings()


def _png_bytes(img: Any) -> bytes:
    """Encode a PIL image (from the clipboard) as PNG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def offers_table(report: Report) -> pd.DataFrame:
    rows = []
    for o in report.offers:
        la = o.landed
        if la is None:
            continue
        rows.append(
            {
                "Source": o.provider,
                "Listing": o.title,
                "Open": o.url,
                "Match": f"{o.match.value} ({o.confidence:.0%})",
                "Condition": o.condition,
                "Item": f"{float(la.item):,.2f} {o.currency}",
                "Shipping": ("~" if la.estimated else "") + f"{float(la.shipping):,.2f}",
                "Taxes": f"{float(la.vat + la.duty + la.fees):,.2f}",
                "Total ILS": round(float(la.total_ils), 2),
                "Total USD": round(float(la.total_usd), 2),
                "Flags": ", ".join(sorted({r.code for r in o.restrictions})) or "-",
                "Estimated": la.estimated,
            }
        )
    return pd.DataFrame(rows)


def pick_card(col: st.delta_generator.DeltaGenerator, label: str, o: Offer | None) -> None:
    with col:
        st.markdown(f"**{label}**")
        if o is None or o.landed is None:
            st.caption("no data")
            return
        st.metric(
            o.provider, f"₪{float(o.landed.total_ils):,.0f}", f"${float(o.landed.total_usd):,.2f}"
        )
        st.markdown(f"[{o.title[:70]}]({o.url})")
        if o.landed.estimated:
            st.caption("includes estimated shipping/tax")


def show_report(report: Report) -> None:
    c = report.cost
    if report.rules_note:
        st.warning(report.rules_note)
    for w in report.warnings:
        st.warning(w)

    if c is not None:
        box = st.success if c.worth_it else st.warning if c.worth_it is False else st.info
        box(c.verdict)
        a, b, d, e = st.columns(4)
        a.metric("This search", f"${c.total_usd:.3f}")
        b.metric("SerpAPI calls", c.serp_calls, f"${c.serpapi_usd:.3f}")
        d.metric("Claude tokens", f"{c.tokens_in + c.tokens_out:,}", f"${c.llm_usd:.3f}")
        e.metric(
            "Potential saving",
            "n/a" if c.potential_saving_usd is None else f"${c.potential_saving_usd:.2f}",
        )
        if c.saving_basis:
            st.caption(f"Saving basis: {c.saving_basis}")

    st.subheader("Best picks")
    cols = st.columns(3)
    pick_card(cols[0], "Cheapest", report.cheapest)
    pick_card(cols[1], "Fastest", report.fastest)
    pick_card(cols[2], "Best value", report.best_value)

    st.subheader(f"Offers ({len(report.offers)})")
    df = offers_table(report)
    if df.empty:
        st.info("No matching offers found.")
    else:
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Open": st.column_config.LinkColumn("Open", display_text="open ↗"),
                "Total ILS": st.column_config.NumberColumn(format="₪%.2f"),
                "Total USD": st.column_config.NumberColumn(format="$%.2f"),
            },
        )
        st.caption(
            "`~` = estimated value. Flags are import-restriction hints: verify with customs."
        )
        with st.expander("Details, warnings and restrictions per offer"):
            for o in report.offers:
                notes = (o.warnings + o.landed.notes) if o.landed else o.warnings
                if not notes and not o.restrictions:
                    continue
                st.markdown(f"**{o.title[:90]}** ({o.provider})")
                for n in notes:
                    st.markdown(f"- {n}")
                for r in o.restrictions:
                    st.markdown(f"- `{r.severity.value}` {r.reason}")

    with st.expander("Data notes"):
        st.write(f"FX: {report.fx_note or 'n/a'}")
        for k, v in report.provider_status.items():
            st.write(f"- {k}: {v}")
        st.caption("Tax and restriction information is indicative only: verify with customs.")

    d1, d2, d3 = st.columns(3)
    d1.download_button("Download report (.md)", to_markdown(report), "report.md")
    d2.download_button("Download data (.json)", report.model_dump_json(indent=2), "report.json")
    if not df.empty:
        d3.download_button("Download table (.csv)", df.to_csv(index=False), "report.csv")


# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Options")
    dest = st.text_input("Destination country", "IL", max_chars=2).upper()
    max_results = st.slider("Max results", 5, 30, 15)
    qty = st.number_input("Quantity", 1, 100, 1)
    inc_local = st.checkbox("Include Israeli stores", True)
    inc_global = st.checkbox("Include global sellers", True)
    inc_used = st.checkbox(
        "Include second-hand / refurbished",
        False,
        help="Off = new products only (default). Used listings are detected from the title and the seller's condition field.",
    )
    use_ai = st.checkbox(
        "Use Claude AI (better matching, costs a little)",
        value=bool(settings.anthropic_api_key),
        disabled=not settings.anthropic_api_key,
    )
    current = st.number_input(
        "Price I'd pay otherwise (USD, landed incl. shipping)",
        min_value=0.0,
        value=0.0,
        step=1.0,
        help="Makes the saving estimate accurate. Leave 0 to use the median offer instead.",
    )
    ship_est = st.number_input(
        "Shipping to assume when unknown (USD)",
        min_value=0.0,
        value=8.0,
        step=1.0,
        help="AliExpress does not give shipping via our API. Enter what you see on the product page.",
    )
    st.divider()
    cost, n, saving = ledger_totals(settings.ledger_path)
    st.metric("Spent on searches so far", f"${cost:.2f}", f"{n} searches")
    st.caption(
        f"SerpAPI assumed ${settings.serpapi_cost_per_search}/search · model {settings.model}"
    )
    st.divider()
    st.caption("API keys")
    for p in build_providers(settings):
        st.write(("✅ " if p.configured() else "⚪ ") + p.name)
    st.write(("✅ " if settings.anthropic_api_key else "⚪ ") + "anthropic")

# ----------------------------------------------------------------------------- main
st.title("🔎 PriceHunter")
st.caption(
    "Find the best landed price (item + shipping + import tax) for a product, in Israel or abroad."
)

tab_text, tab_link, tab_img = st.tabs(["Product name", "Product link", "Photo / screenshot"])
query: str | None = None
with tab_text:
    t = st.text_input(
        "What are you looking for?", placeholder="Anker A1289 power bank 10000mAh black"
    )
    go_text = st.button("Search", key="go_text", type="primary")
    if go_text and t.strip():
        query = t.strip()
with tab_link:
    u = st.text_input("Paste a product link", placeholder="https://www.aliexpress.com/item/…")
    go_link = st.button("Search", key="go_link", type="primary")
    if go_link and u.strip():
        query = u.strip()
with tab_img:
    st.markdown(
        "**Take a screenshot, then click the button and press Ctrl+V** (or upload a file below)."
    )
    pasted = paste_image_button(
        "📋 Paste screenshot from clipboard", key="paste_img", background_color="#ff4b4b"
    )
    if pasted.image_data is not None:
        st.session_state["pasted_png"] = _png_bytes(pasted.image_data)
    f = st.file_uploader(
        "…or upload a product photo or screenshot", type=["png", "jpg", "jpeg", "webp"]
    )
    shown: bytes | None = f.getvalue() if f is not None else st.session_state.get("pasted_png")
    if shown:
        st.image(shown, caption="Image that will be searched", width=320)
    go_img = st.button("Search", key="go_img", type="primary")
    if go_img and shown:
        name = f.name if f is not None else "pasted_screenshot.png"
        tmp = Path(tempfile.mkdtemp()) / name
        tmp.write_bytes(shown)
        query = str(tmp)
    elif go_img:
        st.error("Paste or upload an image first.")

if query:
    options = SearchOptions(
        dest=dest or "IL",
        max_results=max_results,
        include_local=inc_local,
        include_global=inc_global,
        include_used=inc_used,
        qty=int(qty),
        no_ai=not use_ai,
        current_price_usd=current or None,
        ship_estimate_usd=ship_est,
    )
    with st.status("Searching…", expanded=True) as status:
        try:
            report = asyncio.run(
                execute_search(
                    query,
                    settings,
                    options,
                    progress=lambda m: status.write(m),
                    on_product=lambda p: status.write(f"Product: **{p.title}**"),
                )
            )
            status.update(label="Done", state="complete", expanded=False)
            st.session_state["report"] = report
        except Exception as e:  # show the error instead of a stack trace
            status.update(label="Search failed", state="error")
            st.error(f"{type(e).__name__}: {e}")

if "report" in st.session_state:
    st.divider()
    st.header(st.session_state["report"].product.title)
    show_report(st.session_state["report"])
