"""Smoke test: the GUI page renders without errors (no search is run, so no network or cost)."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

GUI = str(Path(__file__).resolve().parent.parent / "pricehunter" / "gui.py")


def test_gui_loads_without_exceptions() -> None:
    at = AppTest.from_file(GUI, default_timeout=30).run()
    assert not at.exception
    assert any("PriceHunter" in t.value for t in at.title)
    assert len(at.tabs) == 3
