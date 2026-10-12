from decimal import Decimal
from pathlib import Path

from pricehunter.costs import CostTracker, ledger_totals, record_run, tracker_from_settings


def test_tracker_math() -> None:
    t = CostTracker(price_in=2.0, price_out=10.0, serp_per_search=0.025)
    t.add_llm(100_000, 10_000)  # 0.20 + 0.10
    t.add_serp(2)  # 0.05
    assert abs(t.llm_usd - 0.30) < 1e-9
    assert abs(t.total_usd - 0.35) < 1e-9


def test_model_price_lookup_and_override() -> None:
    assert tracker_from_settings("claude-sonnet-5-5", None, None, 0.0).price_out == 10.0
    assert tracker_from_settings("claude-haiku-5-5", None, None, 0.0).price_in == 0.10
    assert tracker_from_settings("claude-sonnet-5-5", 1.0, 2.0, 0.0).price_in == 1.0
    assert tracker_from_settings("unknown-model", None, None, 0.0).price_in == 5.0  # pessimistic


def test_verdict_worth_it_and_not() -> None:
    t = CostTracker(serp_per_search=0.025)
    t.add_serp(2)  # $0.05
    totals = [Decimal(x) for x in ("10", "20", "30")]
    c = t.summary(totals)  # median 20 - cheapest 10 = 10 saving
    assert c.worth_it is True and c.potential_saving_usd == 10.0
    c2 = t.summary([Decimal("10.00"), Decimal("10.02")])  # saving 0.01 < cost 0.05
    assert c2.worth_it is False and "NOT worth it" in c2.verdict


def test_current_price_override_and_no_data() -> None:
    t = CostTracker()
    c = t.summary([Decimal("40")], current_price_usd=100.0)
    assert c.potential_saving_usd == 60.0 and "your stated price" in c.saving_basis
    assert t.summary([]).worth_it is None
    assert t.summary([Decimal("40")]).worth_it is None  # one offer, no reference price


def test_ledger_accumulates(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    t = CostTracker(serp_per_search=0.025)
    t.add_serp(2)
    c1 = record_run(ledger, "a", t.summary([Decimal("10"), Decimal("20"), Decimal("30")]))
    assert c1.cumulative_searches == 1
    c2 = record_run(ledger, "b", t.summary([Decimal("10"), Decimal("20"), Decimal("30")]))
    assert c2.cumulative_searches == 2 and abs(c2.cumulative_cost_usd - 0.10) < 1e-9
    cost, n, saving = ledger_totals(ledger)
    assert n == 2 and abs(cost - 0.10) < 1e-9 and saving == 20.0


def test_generic_query_marks_saving_as_rough() -> None:
    t = CostTracker()
    totals = [Decimal("10"), Decimal("20"), Decimal("30")]
    assert "ROUGH" in t.summary(totals, generic=True).saving_basis
    assert "ROUGH" not in t.summary(totals, generic=False).saving_basis
    assert "ROUGH" not in t.summary(totals, generic=True, current_price_usd=50.0).saving_basis
