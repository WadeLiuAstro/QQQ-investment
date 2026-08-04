from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import SourceStatus
from app.providers.cnn_fear_greed import FearGreedReading
from app.providers.yahoo import PriceBar, Quote
from app.scheduler import collect_dashboard_payload


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


def install_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    qqq_bars = bars([100.0 + index * 0.5 for index in range(210)])
    vix_bars = bars([16.0 + index * 0.1 for index in range(30)])
    others = bars([50.0 + index for index in range(30)])

    def fake_bars(symbol: str, period: str):
        if symbol == "QQQ":
            return qqq_bars, status("yahoo")
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


def test_payload_contains_action_card_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mocks(monkeypatch)

    payload = collect_dashboard_payload(None)

    assert payload.action_card is not None
    assert set(payload.action_card) == {
        "extra_top_up_ready",
        "extra_top_up_reason",
        "watch_conditions",
        "data_completeness",
    }
    assert len(payload.action_card["watch_conditions"]) == 3
    assert payload.action_card["data_completeness"]["total"] == 12


def test_action_card_consistent_with_independent_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    decision = evaluate_decision(indicators, load_rule_config())
    assert payload.decision.state == decision.state
    assert payload.action_card["extra_top_up_ready"] is False


def test_decision_fields_unchanged_by_action_card(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_action_card_none_when_qqq_data_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_bars(symbol: str, period: str):
        return None, status("yahoo", available=False)

    monkeypatch.setattr("app.scheduler.fetch_daily_bars", no_bars)
    monkeypatch.setattr(
        "app.scheduler.fetch_quote", lambda symbol: (None, status("yahoo_quote", available=False))
    )
    monkeypatch.setattr(
        "app.scheduler.fetch_fear_greed",
        lambda client: (None, status("cnn_fear_greed", available=False)),
    )
    monkeypatch.setattr(
        "app.scheduler.load_macro_events", lambda client, start, end: ([], status("macro_calendar"))
    )

    payload = collect_dashboard_payload(None)

    assert payload.decision is None
    assert payload.action_card is None
