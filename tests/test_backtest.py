from datetime import date, timedelta

from app.config import load_rule_config
from app.providers.yahoo import PriceBar
from app.services.backtest import run_backtest


def sample_bars(count: int) -> list[PriceBar]:
    start = date(2025, 1, 1)
    return [
        PriceBar(
            day=start + timedelta(days=index),
            close=400.0 + index * 0.4 + (index % 7 - 3) * 0.6,
            volume=1_000_000 + (index % 5) * 10_000,
        )
        for index in range(count)
    ]


def test_backtest_does_not_change_past_decisions_when_future_bars_change() -> None:
    bars = sample_bars(260)
    altered_bars = bars[:-1] + [
        PriceBar(day=bars[-1].day, close=100.0, volume=10_000_000)
    ]

    original = run_backtest(bars, load_rule_config())
    altered = run_backtest(altered_bars, load_rule_config())

    assert original.daily_states[:-1] == altered.daily_states[:-1]


def test_backtest_reports_benchmark_and_max_drawdown() -> None:
    result = run_backtest(sample_bars(260), load_rule_config())

    assert result.benchmark_return is not None
    assert result.max_drawdown <= 0
    assert sum(result.state_counts.values()) == len(result.daily_states)
