"""S1a: MA200 趋势状态机与快速熔断检测（体系 §3）。

- 多头环境：QQQ 收盘价 ≥ MA200，收复即算（进场积极）
- 空头环境：收盘价连续 3 日低于 MA200 且低于幅度 ≥ 1%（出场要确认，防锯齿）
- 快速熔断：最近 21 个交易日（约一个月）回撤 ≥ 8% 时，无论 MA200 状态立即触发
"""

from dataclasses import dataclass
from typing import Sequence

from app.providers.yahoo import PriceBar

_BEAR_DAYS = 3
_BEAR_BAND_PCT = 1.0
_CIRCUIT_BREAKER_DRAWDOWN = 8.0
_MONTH_WINDOW = 21
_MA_WINDOW = 200


@dataclass(frozen=True)
class TrendState:
    available: bool
    regime: str | None = None  # "bull" | "bear"
    deviation_pct: float | None = None  # 收盘价相对 MA200 偏离（%）
    consecutive_below: int = 0  # 连续低于 MA200 的交易日数
    circuit_breaker: bool = False  # 单月回撤 ≥ 8%
    month_drawdown_pct: float | None = None
    note: str | None = None


def evaluate_trend(
    bars: Sequence[PriceBar], previous_regime: str | None = None
) -> TrendState:
    """基于日线收盘价评估 MA200 趋势状态与快速熔断。"""
    closes = [bar.close for bar in bars]
    if len(closes) < _MA_WINDOW:
        return TrendState(available=False, note="历史数据不足 200 日")

    price = closes[-1]
    ma200 = sum(closes[-_MA_WINDOW:]) / _MA_WINDOW
    deviation_pct = round((price / ma200 - 1.0) * 100, 2)

    consecutive_below = 0
    for close in reversed(closes):
        if close < ma200:
            consecutive_below += 1
        else:
            break

    window_peak = max(closes[-_MONTH_WINDOW:])
    month_drawdown_pct = round((price / window_peak - 1.0) * 100, 2)
    circuit_breaker = month_drawdown_pct <= -_CIRCUIT_BREAKER_DRAWDOWN

    if price >= ma200:
        regime = "bull"
    elif consecutive_below >= _BEAR_DAYS and price <= ma200 * (1 - _BEAR_BAND_PCT / 100):
        regime = "bear"
    elif previous_regime == "bear":
        regime = "bear"  # 尚未收复 MA200，维持防守
    else:
        regime = "bull"  # 多头环境内的小幅回调

    return TrendState(
        available=True,
        regime=regime,
        deviation_pct=deviation_pct,
        consecutive_below=consecutive_below,
        circuit_breaker=circuit_breaker,
        month_drawdown_pct=month_drawdown_pct,
    )
