from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import SourceStatus
from app.providers.cnn_fear_greed import FearGreedReading
from app.providers.yahoo import PriceBar, Quote
from app.scheduler import collect_dashboard_payload
from app.services.session import NY_TZ

RULE_KEYS = {
    "rsi2_oversold",
    "rsi6_oversold",
    "drawdown_risk",
    "vix_high",
    "volume_ratio_high",
}


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


def install_mocks(monkeypatch: pytest.MonkeyPatch, vix_available: bool = True) -> None:
    qqq_bars = bars([100.0 + index * 0.5 for index in range(210)])
    vix_bars = bars([16.0 + index * 0.1 for index in range(30)])
    others = bars([50.0 + index for index in range(30)])

    def fake_bars(symbol: str, period: str):
        if symbol == "QQQ":
            return qqq_bars, status("yahoo")
        if symbol == "^VIX":
            return (vix_bars if vix_available else None), status(
                "yahoo", available=vix_available
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


def test_payload_contains_threshold_matrix_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mocks(monkeypatch)

    payload = collect_dashboard_payload(None)

    matrix = payload.market["qqq"]["threshold_matrix"]
    assert len(matrix) == 5
    assert {row["rule"] for row in matrix} == RULE_KEYS


def test_vix_source_failure_marks_vix_row_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mocks(monkeypatch, vix_available=False)

    payload = collect_dashboard_payload(None)

    matrix = {row["rule"]: row for row in payload.market["qqq"]["threshold_matrix"]}
    assert matrix["vix_high"]["available"] is False
    assert matrix["vix_high"]["note"] == "未参与本次判断"
    assert matrix["vix_high"]["current"] is None
    assert all(
        matrix[key]["available"]
        for key in ("rsi2_oversold", "rsi6_oversold", "drawdown_risk", "volume_ratio_high")
    )


def test_decision_fields_unchanged_by_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    from app.config import load_rule_config
    from app.services.decision import evaluate_decision
    from app.services.indicators import calculate_indicators

    install_mocks(monkeypatch)

    payload = collect_dashboard_payload(None)

    qqq_bars = bars([100.0 + index * 0.5 for index in range(210)])
    indicators = replace(
        calculate_indicators(qqq_bars, intraday_price=205.0),
        vix=18.9,
        fear_greed=50.0,
    )
    expected = evaluate_decision(indicators, load_rule_config())

    assert payload.decision.state == expected.state
    assert payload.decision.allocation_min == expected.allocation_min
    assert payload.decision.allocation_max == expected.allocation_max
    assert payload.decision.target_allocation == expected.target_allocation
    assert payload.decision.dca_multiplier == expected.dca_multiplier


def _patch_session(monkeypatch: pytest.MonkeyPatch, market_open: bool) -> None:
    monkeypatch.setattr(
        "app.scheduler.is_regular_session_open", lambda now=None: market_open
    )
    monkeypatch.setattr(
        "app.scheduler.session_elapsed_fraction", lambda now=None: (0.5 if market_open else None)
    )


def _install_today_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    today = datetime.now(NY_TZ).date()
    qqq_bars = [
        PriceBar(day=today - timedelta(days=len(range(210)) - index), close=100.0 + index * 0.5, volume=1_000_000)
        for index in range(210)
    ]
    qqq_bars[-1] = PriceBar(day=today, close=205.0, volume=1_000_000)

    def fake_bars(symbol: str, period: str):
        if symbol == "QQQ":
            return qqq_bars, status("yahoo")
        return bars([50.0 + index for index in range(30)]), status("yahoo")

    def fake_quote(symbol: str):
        return (
            Quote(symbol=symbol, price=205.0, previous_close=200.0, is_intraday_estimate=True),
            status("yahoo_quote"),
        )

    monkeypatch.setattr("app.scheduler.fetch_daily_bars", fake_bars)
    monkeypatch.setattr("app.scheduler.fetch_quote", fake_quote)
    monkeypatch.setattr(
        "app.scheduler.fetch_fear_greed",
        lambda client: (None, status("cnn_fear_greed", available=False)),
    )
    monkeypatch.setattr(
        "app.scheduler.load_macro_events", lambda client, start, end: ([], status("macro_calendar"))
    )


def test_intraday_session_extrapolates_volume_and_marks_estimated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session(monkeypatch, market_open=True)
    _install_today_mocks(monkeypatch)

    payload = collect_dashboard_payload(None)

    indicators = payload.market["qqq"]["indicators"]
    assert indicators["volume_is_estimated"] is True
    assert indicators["volume_ratio"] == 2.0
    matrix = {row["rule"]: row for row in payload.market["qqq"]["threshold_matrix"]}
    assert matrix["volume_ratio_high"]["note"] == "盘中估算"
    assert matrix["volume_ratio_high"]["available"] is True


def test_closed_session_keeps_raw_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, market_open=False)
    _install_today_mocks(monkeypatch)

    payload = collect_dashboard_payload(None)

    indicators = payload.market["qqq"]["indicators"]
    assert indicators["volume_is_estimated"] is False
    assert indicators["volume_ratio"] == 1.0
    matrix = {row["rule"]: row for row in payload.market["qqq"]["threshold_matrix"]}
    assert matrix["volume_ratio_high"]["note"] is None
