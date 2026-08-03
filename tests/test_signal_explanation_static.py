from pathlib import Path


def test_dashboard_displays_rule_values_and_inline_sector_cards() -> None:
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    styles = Path("static/assets/style.css").read_text(encoding="utf-8")

    assert "formatSignalBreakdown" in script
    assert "VIX（恐慌指数）" in script
    assert "当前处于中性状态" in script
    assert "RSI(2)" in script and "超卖阈值 15 / 30" in script
    assert "sector-name" in script and "sector-price" in script
    assert ".sector{display:flex" in styles
    assert ".sectors{grid-template-columns:repeat(2,minmax(0,1fr))" in styles