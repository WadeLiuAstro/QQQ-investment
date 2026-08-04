"""S1d: payload 接线测试——trend 与 structural_risk 进入 market.qqq。"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import SourceStatus
from app.providers.cnn_fear_greed import FearGreedReading
from app.providers.yahoo import PriceBar, Quote
from app.scheduler import collect_dashboard_payload
from app.services.structural import compute_structural_score
from app.services.trend import evaluate_trend


def bars(closes: list[float]) -> list[PriceBar]:
    start = date(2025, 1, 1)
    return [
        PriceBar(day=start + timedelta(days=index), close=close, volume=1_000_000)
        for index, close in enumerate(closes)
    ]


def status(source: str, available: bool = True) -> SourceStatus:
    return SourceStatus(source=source, available=available, checked_at=datetime.now(UTC))


def install_mocks(
    monkeypatch: pytest.MonkeyPatch,
    vix3m_available: bool = True,
    qqq_closes: list[float] | None = None,
) -> None:
    qqq_bars = (
        bars(qqq_closes) if qqq_closes is not None else bars([100.0 + index * 0.5 for index in range(260)])
    )
    qqqe_bars = bars([100.0 + index * 0.4 for index in range(260)])
    vix_bars = bars([16.0 + index * 0.1 for index in range(30)])
    vix3m_bars = bars([15.0 + index * 0.05 for index in range(30)])
    others = bars([50.0 + index for index in range(30)])

    def fake_bars(symbol: str, period: str):
        if symbol == "QQQ":
            return qqq_bars, status("yahoo")
        if symbol == "QQQE":
            return qqqe_bars, status("yahoo")
        if symbol == "^VIX":
            return vix_bars, status("yahoo")
        if symbol == "^VIX3M":
            return (vix3m_bars if vix3m_available else None), status(
                "yahoo", available=vix3m_available
            )
        return others, status("yahoo")

    def fake_quote(symbol: str):
        return (
            Quote(symbol=symbol, price=205.0, previous_close=200.0, is_intraday_estimate=True),
            status("yahoo_quote"),
        )

    def fake_fear_greed(client):
        return (
            FearGreedReading(score=50, rating="Neutral", observed_at=datetime.now(UTC)),
            status("cnn_fear_greed"),
        )

    def fake_macro(client, start, end):
        return [], status("macro_calendar")

    monkeypatch.setattr("app.scheduler.fetch_daily_bars", fake_bars)
    monkeypatch.setattr("app.scheduler.fetch_quote", fake_quote)
    monkeypatch.setattr("app.scheduler.fetch_fear_greed", fake_fear_greed)
    monkeypatch.setattr("app.scheduler.load_macro_events", fake_macro)


def test_payload_contains_trend_matching_independent_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mocks(monkeypatch)

    payload = collect_dashboard_payload(None)

    qqq_bars = bars([100.0 + index * 0.5 for index in range(260)])
    expected = evaluate_trend(qqq_bars, previous_regime=None)

    trend = payload.market["qqq"]["trend"]
    assert trend["available"] is True
    assert trend["regime"] == expected.regime == "bull"
    assert trend["circuit_breaker"] == expected.circuit_breaker is False


def test_payload_contains_structural_risk_matching_independent_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mocks(monkeypatch)

    payload = collect_dashboard_payload(None)

    qqq_bars = bars([100.0 + index * 0.5 for index in range(260)])
    qqqe_bars = bars([100.0 + index * 0.4 for index in range(260)])
    vix_bars = bars([16.0 + index * 0.1 for index in range(30)])
    vix3m_bars = bars([15.0 + index * 0.05 for index in range(30)])
    expected = compute_structural_score(qqq_bars, qqqe_bars, vix_bars, vix3m_bars)

    structural = payload.market["qqq"]["structural_risk"]
    assert structural["available"] is True
    assert structural["score"] == expected.score
    assert structural["band"] == expected.band == "normal"


def test_trend_bear_holds_across_refresh_cycles(monkeypatch: pytest.MonkeyPatch) -> None:
    # 第一轮：QQQ 温和下跌后小幅反弹（未收复 MA200）→ 首次进入 bear
    bear_closes = [100.0] * 230 + [92.0, 91.0, 90.0, 89.0]
    install_mocks(monkeypatch, qqq_closes=bear_closes)
    first = collect_dashboard_payload(None)
    assert first.market["qqq"]["trend"]["regime"] == "bear"

    # 第二轮：反弹但未收复 MA200（仅 1 日低于，偏离 < 1%）→ 维持 bear
    install_mocks(
        monkeypatch,
        qqq_closes=[100.0] * 230 + [92.0, 91.0, 90.0, 89.0, 89.5],
    )
    second = collect_dashboard_payload(first)
    assert second.market["qqq"]["trend"]["regime"] == "bear"


def test_vix3m_failure_keeps_structural_score_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mocks(monkeypatch, vix3m_available=False)

    payload = collect_dashboard_payload(None)

    structural = payload.market["qqq"]["structural_risk"]
    # VIX3M 缺失时仅失去期限倒挂分，评分仍可用
    assert structural["available"] is True
    assert structural["vol_score"] >= 0.0
    assert "yahoo_vix3m" in payload.sources
    assert payload.sources["yahoo_vix3m"].available is False
