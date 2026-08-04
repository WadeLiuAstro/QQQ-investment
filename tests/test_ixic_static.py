from pathlib import Path


def test_static_page_has_nasdaq_composite_chart_contract() -> None:
    html = Path("static/index.html").read_text(encoding="utf-8")
    script = Path("static/assets/app.js").read_text(encoding="utf-8")

    assert 'id="nasdaq-composite"' in html
    assert 'id="ixic-chart"' in html
    assert 'data-range="3m"' in html
    assert "renderNasdaqComposite" in script
    assert "upColor:'#3DDC97'" in script
    assert "downColor:'#F0656B'" in script
    assert "change.className=ixic?.daily_change_points>=0?'positive':'negative'" in script
    assert "setOhlc(ixicCandles.at(-1))" in script
    assert "p.sources?.yahoo_ixic?.available?p.market?.ixic:null" in script


def test_ixic_granularity_is_explicit_daily() -> None:
    html = Path("static/index.html").read_text(encoding="utf-8")

    assert 'id="ixic-granularity"' in html
    assert "日K" in html
    assert "每根=1 交易日" in html


def test_ixic_stale_lag_annotation_contract() -> None:
    script = Path("static/assets/app.js").read_text(encoding="utf-8")

    assert "stale_lag" in script
    assert "数据滞后" in script
    assert "个交易日" in script
