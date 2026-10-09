from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from ..models import Report
from .markdown import to_markdown

CSV_FIELDS = [
    "provider", "title", "url", "seller", "match", "confidence", "price", "currency",
    "shipping", "vat", "duty", "fees", "total_usd", "total_ils", "estimated", "restrictions", "warnings",
]  # fmt: skip


def save_report(report: Report, formats: set[str], base: Path = Path("runs")) -> Path:
    out = base / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    if "md" in formats:
        (out / "report.md").write_text(to_markdown(report), encoding="utf-8")
    if "json" in formats:
        (out / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    if "csv" in formats:
        with (out / "report.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            w.writeheader()
            for o in report.offers:
                la = o.landed
                w.writerow(
                    {
                        "provider": o.provider, "title": o.title, "url": o.url, "seller": o.seller,
                        "match": o.match.value, "confidence": o.confidence,
                        "price": o.price, "currency": o.currency,
                        "shipping": la.shipping if la else "", "vat": la.vat if la else "",
                        "duty": la.duty if la else "", "fees": la.fees if la else "",
                        "total_usd": f"{la.total_usd:.2f}" if la else "",
                        "total_ils": f"{la.total_ils:.2f}" if la else "",
                        "estimated": la.estimated if la else "",
                        "restrictions": ";".join(f"{r.severity.value}:{r.code}" for r in o.restrictions),
                        "warnings": ";".join(o.warnings),
                    }
                )  # fmt: skip
    return out
