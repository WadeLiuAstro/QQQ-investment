"""S1a: MA200 趋势状态机与快速熔断检测测试（体系 §3）。"""

from datetime import date, timedelta

from app.providers.yahoo import PriceBar
from app.services.trend import evaluate_trend


def _bars(close_values: list[float]) -> list[PriceBar]:
    start = date(2020, 1, 1)
    return [
        PriceBar(start + timedelta(days=i), close, 1_000_000, close, close, close)
        for i, close in enumerate(close_values)
    ]


def _series(*tail: float) -> list[PriceBar]:
    """200 根 100.0 基准 + 尾部序列。"""
    return _bars([100.0] * 200 + list(tail))


def test_bull_when_price_above_ma200() -> None:
    state = evaluate_trend(_series(101.0))
    assert state.available
    assert state.regime == "bull"
    assert state.circuit_breaker is False


def test_bear_requires_three_consecutive_days_below_ma200() -> None:
    state = evaluate_trend(_series(97.0, 96.0, 95.0))
    assert state.regime == "bear"
    assert state.consecutive_below >= 3


def test_one_day_dip_below_ma200_is_not_bear() -> None:
    state = evaluate_trend(_series(95.0))
    assert state.regime == "bull"


def test_bear_requires_1pct_deviation_band() -> None:
    # 连续 3 日低于 MA200，但偏离不足 1%：仍在多头环境
    state = evaluate_trend(_series(99.6, 99.5, 99.4))
    assert state.regime == "bull"


def test_bear_holds_until_price_reclaims_ma200() -> None:
    # 已进入 bear 后，反弹但未收复（偏离 < 1% 且低于天数 < 3）应维持 bear
    state = evaluate_trend(_series(95.0, 96.0, 95.0, 99.5), previous_regime="bear")
    assert state.regime == "bear"
    # 收复 MA200 立即回到 bull（进场积极）
    state = evaluate_trend(_series(95.0, 96.0, 95.0, 99.5, 101.0), previous_regime="bear")
    assert state.regime == "bull"


def test_bear_requires_previous_regime_to_hold() -> None:
    # 同样的小幅回调，但此前是 bull：仍在多头环境
    state = evaluate_trend(_series(95.0, 96.0, 95.0, 99.5), previous_regime="bull")
    assert state.regime == "bull"


def test_circuit_breaker_triggered_on_8pct_month_drawdown() -> None:
    # 最近 21 个交易日窗口回撤 -10% ≥ 8%：触发熔断
    state = evaluate_trend(_series(*([100.0] * 20), 90.0))
    assert state.circuit_breaker is True
    assert state.month_drawdown_pct is not None
    assert state.month_drawdown_pct <= -8.0


def test_circuit_breaker_not_triggered_below_8pct() -> None:
    state = evaluate_trend(_series(*([100.0] * 20), 95.0))
    assert state.circuit_breaker is False


def test_circuit_breaker_independent_of_regime() -> None:
    # 多头环境内也可能触发熔断（体系 §3：无论 MA200 状态）
    state = evaluate_trend(_series(101.0, 100.5, *([100.0] * 20), 90.0))
    assert state.regime == "bull"
    assert state.circuit_breaker is True


def test_insufficient_data_returns_unavailable() -> None:
    state = evaluate_trend(_bars([100.0] * 100))
    assert state.available is False
    assert state.regime is None
