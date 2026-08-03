from pathlib import Path


def test_dashboard_markup_has_all_required_sections() -> None:
    html = Path("static/index.html").read_text(encoding="utf-8")

    for element_id in [
        "signal-band",
        "qqq-core",
        "macro-grid",
        "event-list",
        "sector-grid",
        "signal-reasons",
        "backtest-summary",
        "data-status",
    ]:
        assert f'id="{element_id}"' in html
