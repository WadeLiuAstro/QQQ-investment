from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import SourceStatus
from app.providers.cnn_fear_greed import FearGreedReading
from app.providers.yahoo import PriceBar, Quote
from app.scheduler import collect_dashboard_payload
from app.services.breadth import build_breadth


def bars(closes: list[float]) -> list[PriceBar]:
    start = date(2025, 1, 1)
    return [
        PriceBar(day=start + timedelta(days=index), close=close, volume=1_000_000)
        for index, close in enumerate(closes)
    ]


def status(source: str, available: bool = True) -> SourceStatus:
    return SourceStatus(
        source=source, available=available, checked_at=datetime.now(UTC)
    )


def install_mocks(monkeypatch: pytest.MonkeyPatch, qqqe_available: bool = True) -> None:
    qqq_bars = bars([100.0 + index * 0.5 for index in range(210)])
    qqqe_bars = bars([100.0 + index * 0.4 for index in range(210)])
    vix_bars = bars([16.0 + index * 0.1 for index in range(30)])
    others = bars([50.0 + index for index in range(30)])

    def fake_bars(symbol: str, period: str):
        if symbol == "QQQ":
            return qqq_bars, status("yahoo")
        if symbol == "QQQE":
            return (qqqe_bars if qqqe_available else None), status(
                "yahoo", available=qqqe_available
            )
        if symbol == "^VIX":
            return vix_bars, status("yahoo")
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


def test_payload_contains_breadth_matching_independent_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mocks(monkeypatch)

    payload = collect_dashboard_payload(None)

    qqq_bars = bars([100.0 + index * 0.5 for index in range(210)])
    qqqe_bars = bars([100.0 + index * 0.4 for index in range(210)])
    expected = build_breadth(qqq_bars, qqqe_bars)

    breadth = payload.market["qqq"]["breadth"]
    assert breadth["available"] is True
    assert breadth["relative_strength_20d"] == expected.relative_strength_20d
    assert breadth["label"] == expected.label
    assert breadth["qqqe_price"] == expected.qqqe_price


def test_qqqe_failure_marks_breadth_unavailable_but_keeps_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mocks(monkeypatch, qqqe_available=False)

    payload = collect_dashboard_payload(None)

    breadth = payload.market["qqq"]["breadth"]
    assert breadth["available"] is False
    assert breadth["note"] == "等权数据缺失"
    assert payload.decision is not None
    assert payload.decision.state == "constructive"


def test_data_completeness_total_includes_qqqe(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mocks(monkeypatch)

    payload = collect_dashboard_payload(None)

    assert payload.action_card["data_completeness"]["total"] == 14
